# Filtra i proxy candidati con validazione a due stadi (o tre con speed test):
#   stage1 = pre-filtro veloce (endpoint HTTP leggero, alta concorrenza, timeout corto)
#   stage2 = validazione vera contro Mega (concorrenza moderata, timeout normale)
#   stage3 = speed test reale (solo con selezione_velocita attiva): misura il
#            throughput effettivo e scarta i proxy sotto soglia ammissione.
# Solo i proxy che passano stage1 vengono testati allo stage2.
# Atteso: ~70% dei proxy gratuiti viene scartato gia' a stage1 — e' la norma.
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import requests

from src.core.config import (
    SPEED_SELECTION_ADMISSION_BPS,
    SPEED_SELECTION_MIN_BPS,
    USER_AGENT,
    VALIDATOR_SPEED_TEST_BYTES,
    VALIDATOR_SPEED_TEST_TIMEOUT,
    VALIDATOR_SPEED_TEST_URL,
    VALIDATOR_SPEED_TEST_WORKERS,
    VALIDATOR_STAGE1_TIMEOUT,
    VALIDATOR_STAGE1_URL,
    VALIDATOR_STAGE1_WORKERS,
    VALIDATOR_STAGE2_TIMEOUT,
    VALIDATOR_STAGE2_URL,
    VALIDATOR_STAGE2_WORKERS,
    VALIDATOR_TARGET_ALIVE,
)
from src.core.proxy_url import build_proxies_dict

log = logging.getLogger(__name__)

# Una requests.Session per thread: riusa il connection pool sottostante.
# I worker del ThreadPoolExecutor sono pochi (max ~250) e long-lived per
# tutta la durata dello stage, quindi la session viene amortizzata.
_thread_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


class ProxyValidator:
    def __init__(self) -> None:
        self._headers = {"User-Agent": USER_AGENT}
        self._admission_threshold: int = SPEED_SELECTION_ADMISSION_BPS
        self._preference_threshold: int = SPEED_SELECTION_MIN_BPS

    def validate_against_mega(
        self,
        proxies: list[dict],
        *,
        stage1_workers: int = VALIDATOR_STAGE1_WORKERS,
        stage2_workers: int = VALIDATOR_STAGE2_WORKERS,
        target_alive: int | None = VALIDATOR_TARGET_ALIVE,
        progress_callback: Callable[[int, int, int], None] | None = None,
        return_stage_breakdown: bool = False,
        speed_test: bool = False,
        speed_admission_bps: int = SPEED_SELECTION_ADMISSION_BPS,
        speed_preference_bps: int = SPEED_SELECTION_MIN_BPS,
    ):
        # Se return_stage_breakdown=True, ritorna dict {stage1_alive, stage2_alive[, stage3_alive]}
        # invece della lista finale (per telemetria per-fonte). Default False
        # preserva firma e nessun chiamante esistente si rompe.
        # progress_callback(done, total, alive_so_far) viene chiamato dopo ogni
        # check, sia in stage1 sia in stage2. La GUI vede una progress bar
        # continua: il `total` cambia tra stage (passa da N candidati ai vivi
        # di stage1) ma e' attesa la transizione.
        # speed_test=True attiva lo stage3 (speed test reale su server esterno).
        # I proxy sotto speed_admission_bps vengono scartati; quelli sopra
        # ricevono proxy["throughput_bps"] per il pre-caricamento nel pool.
        self._admission_threshold = speed_admission_bps
        self._preference_threshold = speed_preference_bps

        if not proxies:
            log.warning("Nessun proxy candidato da validare")
            return {"stage1_alive": [], "stage2_alive": []} if return_stage_breakdown else []

        # --- Stage 1: pre-filtro veloce ---
        stage1_alive = self._run_stage(
            proxies,
            self._check_alive,
            stage1_workers,
            progress_callback,
            stage_name="stage1",
            target_alive=None,  # non interrompere lo stage1 in anticipo
        )
        log.info(
            "[stage1] %d/%d proxy passati il pre-filtro (scartati: %d)",
            len(stage1_alive), len(proxies), len(proxies) - len(stage1_alive),
        )

        # Fallback: se stage1 non ha lasciato NIENTE e' probabile che l'endpoint
        # leggero sia giu' (improbabile per generate_204, ma non impossibile).
        # In quel caso saltiamo stage1
        # e mandiamo tutti i candidati direttamente a stage2 (comportamento
        # single-stage = vecchio comportamento).
        if not stage1_alive:
            log.warning(
                "[stage1] 0 proxy passati: probabile downtime di %s, "
                "fallback su stage2 con tutti i candidati",
                VALIDATOR_STAGE1_URL,
            )
            stage1_alive = list(proxies)

        # --- Stage 2: validazione Mega con cortocircuito ---
        stage2_alive = self._run_stage(
            stage1_alive,
            self._check_mega,
            stage2_workers,
            progress_callback,
            stage_name="stage2",
            target_alive=target_alive,
        )
        log.info(
            "[stage2] %d/%d proxy validi contro Mega",
            len(stage2_alive), len(stage1_alive),
        )

        # --- Stage 3: speed test reale (solo se richiesto) ---
        if speed_test and stage2_alive:
            stage3_alive = self._run_stage(
                stage2_alive,
                self._check_speed,
                VALIDATOR_SPEED_TEST_WORKERS,
                progress_callback,
                stage_name="stage3",
                target_alive=None,  # nessun cortocircuito: processiamo tutti
            )
            above_pref = sum(
                1 for p in stage3_alive
                if p.get("throughput_bps", 0) >= speed_preference_bps
            )
            log.info(
                "[stage3] %d/%d proxy sopra ammissione (%d KB/s), "
                "di cui %d sopra preferenza (%d KB/s)",
                len(stage3_alive), len(stage2_alive),
                speed_admission_bps // 1024,
                above_pref,
                speed_preference_bps // 1024,
            )
            final = stage3_alive
        else:
            stage3_alive = None
            final = stage2_alive

        if return_stage_breakdown:
            result: dict = {
                "stage1_alive": stage1_alive,
                "stage2_alive": stage2_alive,
            }
            if stage3_alive is not None:
                result["stage3_alive"] = stage3_alive
            return result
        return final

    def _run_stage(
        self,
        proxies: list[dict],
        check_fn: Callable[[dict], bool],
        max_workers: int,
        progress_callback: Callable[[int, int, int], None] | None,
        *,
        stage_name: str,
        target_alive: int | None,
    ) -> list[dict]:
        if not proxies:
            return []
        log.info("[%s] inizio: %d candidati, %d worker (target=%s)",
                 stage_name, len(proxies), max_workers, target_alive)
        alive: list[dict] = []
        done = 0
        total = len(proxies)
        with ThreadPoolExecutor(max_workers=max_workers,
                                thread_name_prefix=f"Val-{stage_name}") as pool:
            futures = {pool.submit(check_fn, p): p for p in proxies}
            try:
                for fut in as_completed(futures):
                    proxy = futures[fut]
                    done += 1
                    try:
                        ok = fut.result()
                    except Exception as exc:
                        log.debug("[%s] %s:%s sollevata: %s",
                                  stage_name, proxy["host"], proxy["port"], exc)
                        ok = False
                    if ok:
                        alive.append(proxy)
                    if progress_callback:
                        progress_callback(done, total, len(alive))
                    if done % 25 == 0 or done == total:
                        log.info("[%s] %d/%d completati, %d vivi",
                                 stage_name, done, total, len(alive))
                    if target_alive is not None and len(alive) >= target_alive:
                        log.info(
                            "[%s] target %d raggiunto a %d/%d, cortocircuito",
                            stage_name, target_alive, done, total,
                        )
                        # Cancella i future ancora pending. Quelli gia' running
                        # non si possono interrompere ma uscendo dal `with`
                        # il pool fa shutdown(wait=True): aspettiamo solo i
                        # task gia' in volo (timeout breve dello stage).
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
            finally:
                pass
        return alive

    # --- Stage 1: il proxy funziona (raggiunge un host qualunque)? ---
    def _check_alive(self, proxy: dict) -> bool:
        t0 = time.monotonic()
        try:
            resp = _session().get(
                VALIDATOR_STAGE1_URL,
                headers=self._headers,
                proxies=build_proxies_dict(proxy),
                timeout=VALIDATOR_STAGE1_TIMEOUT,
                allow_redirects=False,
            )
            # generate_204 risponde 204 per design; accetta anche 2xx/3xx
            # nel caso l'endpoint cambi comportamento in futuro.
            ok = 200 <= resp.status_code < 400
        except Exception:
            ok = False
        if ok:
            # Allega la latency misurata al dict: ProxyPool.add_many la leggera'
            # tramite il campo latency_ms. Solo su successo per non sovrascrivere
            # con un valore arbitrario (timeout) un eventuale latency upstream.
            proxy["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return ok

    # --- Stage 2: il proxy raggiunge l'infrastruttura di download Mega? ---
    def _check_mega(self, proxy: dict) -> bool:
        try:
            # GET sull'host dell'API Mega (stesso host del resolve reale).
            # Niente redirect: vogliamo la risposta DIRETTA di questo host,
            # non quella di un eventuale hop successivo. Qualsiasi risposta
            # ricevuta (anche un errore applicativo Mega) conta come successo:
            # vedi commento su VALIDATOR_STAGE2_URL in config.py per il perche'.
            _session().get(
                VALIDATOR_STAGE2_URL,
                headers=self._headers,
                proxies=build_proxies_dict(proxy),
                timeout=VALIDATOR_STAGE2_TIMEOUT,
                allow_redirects=False,
            )
            return True
        except Exception:
            return False

    # --- Stage 3: speed test reale (solo con selezione_velocita attiva) ---
    def _check_speed(self, proxy: dict) -> bool:
        try:
            t0 = time.monotonic()
            resp = _session().get(
                VALIDATOR_SPEED_TEST_URL,
                headers=self._headers,
                proxies=build_proxies_dict(proxy),
                timeout=VALIDATOR_SPEED_TEST_TIMEOUT,
                stream=True,
            )
            if resp.status_code != 200:
                return False
            bytes_read = 0
            for chunk in resp.iter_content(chunk_size=8192):
                bytes_read += len(chunk)
                if bytes_read >= VALIDATOR_SPEED_TEST_BYTES:
                    break
            elapsed = max(time.monotonic() - t0, 0.001)
            throughput_bps = bytes_read / elapsed
            if throughput_bps < self._admission_threshold:
                return False
            # Annotato sul dict: ProxyPool.add_many lo legge per pre-popolare
            # self._throughput[key] cosi' il ramo top-K di get_next() ha dati
            # fin dal primo giro (senza aspettare record_throughput dal download).
            proxy["throughput_bps"] = throughput_bps
            return True
        except Exception:
            return False
