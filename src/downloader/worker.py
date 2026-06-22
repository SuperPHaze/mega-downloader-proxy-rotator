# DownloadWorker: per ogni link esegue DOWNLOAD_CYCLES cicli.
# Ogni ciclo viene RIPROVATO con un proxy diverso finche' non riesce
# (o finche' la sessione viene annullata o l'utente preme Cancel).
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import (
    DOWNLOAD_CYCLES,
    MAX_ATTEMPTS_PER_FILE,
    OUTPUT_DIR,
    PARALLEL_CONNECTIONS_PER_FILE,
)
from src.core.state import SessionState
from src.downloader.mega_client import MegaClient, MegaCryptoDependencyError
from src.downloader.parallel_client import ParallelMegaDownloader
from src.proxy.pool import ProxyPool

log = logging.getLogger(__name__)


def job_output_dir(mega_url: str, file_id: int) -> Path:
    # Stessa formula usata dentro run(): centralizzata qui per consentire
    # alla GUI/orchestrator di sapere dove cancellare i file di un job.
    file_hash = hashlib.sha1(mega_url.encode("utf-8")).hexdigest()[:12]
    return OUTPUT_DIR / f"{file_hash}_{file_id}"


class _EffectiveSessionState:
    # Wrapper che combina lo stato globale (pausa/annullo sessione) con un
    # flag locale di cancellazione per il singolo worker. Permette di
    # annullare un singolo job senza toccare la sessione globale.
    # Controlla anche il deadline wall-clock per-file (se impostato).
    def __init__(self, global_state: SessionState, worker: "DownloadWorker") -> None:
        self._g = global_state
        self._w = worker

    def is_cancelled(self) -> bool:
        if self._w._local_cancelled or self._g.is_cancelled():
            return True
        # Deadline wall-clock per-file: il parallel client vede questa cancellazione
        # e interrompe il download senza modifiche al client stesso.
        if (self._w._file_deadline is not None
                and time.monotonic() > self._w._file_deadline):
            return True
        return False

    def wait_if_paused(self) -> None:
        if self._w._local_cancelled:
            return
        self._g.wait_if_paused()


class DownloadWorker(QThread):
    progress = pyqtSignal(int, int, int)
    ip_logged = pyqtSignal(int, int, str)
    cycle_completed = pyqtSignal(int, int)
    failed = pyqtSignal(int, int, str)     # tentativo fallito, NON ciclo abbandonato
    fatal_error = pyqtSignal(int, str)     # errore permanente: worker termina
    all_done = pyqtSignal(int)
    # Metadati del download completato, emesso UNA volta subito prima di
    # all_done: (file_id, url, file_name, file_size, path). file_size passa
    # come `object` per non troncare file > 2 GB (int dei signal Qt = 32 bit).
    # L'orchestrator lo usa per persistere lo storico download.
    completed_info = pyqtSignal(int, str, str, object, str)
    cancelled = pyqtSignal(int)            # cancellazione richiesta dall'utente per QUESTO job
    abandoned = pyqtSignal(int, str, int, str)  # (file_id, url, attempts, last_error)
    # Throughput in tempo reale: (file_id, bytes_per_sec, downloaded_bytes, total_bytes).
    # downloaded/total come object per file > 2 GB.
    throughput = pyqtSignal(int, float, object, object)
    # Nome file risolto appena noto (prima risoluzione per ciclo): (file_id, file_name, file_size, path).
    # file_size come object per file > 2 GB.
    file_resolved = pyqtSignal(int, str, object, str)

    def __init__(
        self,
        file_id: int,
        mega_url: str,
        proxy_pool: ProxyPool,
        session_state: SessionState,
        file_time_limit_s: int | None = None,
        chunk_size_bytes: int | None = None,
        connections_per_file: int | None = None,
    ) -> None:
        super().__init__()
        self.file_id = file_id
        self.mega_url = mega_url
        self.proxy_pool = proxy_pool
        self.session_state = session_state
        self._local_cancelled = False
        self._effective_state = _EffectiveSessionState(session_state, self)
        # Ultimo errore osservato fra i tentativi: serve a dare un motivo
        # significativo al segnale `abandoned` quando il cap viene raggiunto.
        # Cumulativo per worker, NON resettato fra cicli (cosi' il cap su
        # MAX_ATTEMPTS_PER_FILE e' globale al link).
        self._last_error_msg: str = ""
        self._total_attempts: int = 0
        # Path del file prodotto dall'ultimo ciclo riuscito: alimenta il
        # segnale completed_info (storico download).
        self._last_final_path: Path | None = None
        # Limite di durata wall-clock per-file. Se impostato, viene trasformato
        # in un deadline assoluto (time.monotonic) all'avvio di run().
        self._file_time_limit_s: int | None = file_time_limit_s
        self._file_deadline: float | None = None
        # Dimensione chunk per ParallelMegaDownloader (byte). None = usa default.
        self._chunk_size_bytes: int | None = chunk_size_bytes
        # Connessioni parallele per file (Leva A, scheda Funzioni Sperimentali).
        # None = usa il default di config (comportamento storico).
        self._connections_per_file: int = (
            connections_per_file if connections_per_file is not None
            else PARALLEL_CONNECTIONS_PER_FILE
        )

    def _is_deadline_expired(self) -> bool:
        """True solo se il deadline per-file è scaduto E non c'è una cancellazione
        locale/globale: permette di distinguere timeout da cancel esplicito."""
        if self._file_deadline is None:
            return False
        if self._local_cancelled:
            return False
        if self.session_state.is_cancelled():
            return False
        return time.monotonic() > self._file_deadline

    def request_cancel(self) -> None:
        # Chiamato dall'orchestrator quando l'utente cancella SOLO questo job.
        # Imposta il flag locale; il worker uscira' al prossimo checkpoint.
        log.info("[file %d] cancellazione locale richiesta", self.file_id)
        self._local_cancelled = True

    def is_local_cancelled(self) -> bool:
        return self._local_cancelled

    def run(self) -> None:
        # Includo file_id nel path per consentire download duplicati dello
        # stesso URL in cartelle distinte (utile per copie ridondanti / test
        # di rotazione IP / verifica integrita'). Senza file_id, due worker
        # con lo stesso URL condividerebbero il sidecar di resume e il
        # secondo skippa tutto.
        base_dir = job_output_dir(self.mega_url, self.file_id)
        # Calcola deadline wall-clock per-file (se limite configurato).
        if self._file_time_limit_s is not None:
            self._file_deadline = time.monotonic() + self._file_time_limit_s
            log.info("[file %d] deadline: %d s", self.file_id, self._file_time_limit_s)
        log.info("[file %d] start url=%s base_dir=%s", self.file_id, self.mega_url, base_dir)

        try:
            try:
                for cycle in range(1, DOWNLOAD_CYCLES + 1):
                    ok = self._run_cycle_until_success(cycle, base_dir)
                    if not ok:
                        # Uscita anticipata: cancellazione globale o locale.
                        log.info("[file %d] interrotto al ciclo %d", self.file_id, cycle)
                        return

                log.info(
                    "[file %d] tutti i %d cicli completati. Output: %s",
                    self.file_id, DOWNLOAD_CYCLES, base_dir.resolve(),
                )
                self._emit_completed_info()
                self.all_done.emit(self.file_id)
            finally:
                # Se l'uscita e' avvenuta per cancellazione locale (non globale),
                # notifica l'orchestrator cosi' libera lo slot ed eventualmente
                # cancella la cartella di lavoro.
                if self._local_cancelled and not self.session_state.is_cancelled():
                    self.cancelled.emit(self.file_id)
        except Exception:
            # Rete di sicurezza diagnostica: qualunque eccezione non gia'
            # gestita dentro _run_cycle_until_success non deve sparire senza
            # traccia quando il thread termina. Rilancia dopo il log: nessun
            # cambio di comportamento, solo visibilita'.
            log.exception(
                "[file %d] eccezione non gestita nel worker, il thread termina",
                self.file_id,
            )
            raise

    def _run_cycle_until_success(self, cycle: int, base_dir) -> bool:
        attempt = 0
        cycle_dir = base_dir / f"ciclo_{cycle}"
        # Flag per evitare re-emissioni di file_resolved a ogni retry/re-resolve.
        _name_emitted = [False]

        def _resolved_cb(fn: str, fs: object, fp) -> None:
            if not _name_emitted[0]:
                _name_emitted[0] = True
                self.file_resolved.emit(self.file_id, fn, fs, str(fp))

        # Resume: se il ciclo era gia' completato (run precedente / crash recovery)
        # salta e segnala completato. Un ciclo e' completato SOLO se esiste il
        # file finale prodotto dal rename atomico: non un temporaneo `megapy_*`,
        # non un `.part` (download interrotto, serve al resume del parallel
        # client), non un sidecar `.progress.json*`. Un file con un sidecar
        # accanto e' un residuo del vecchio schema pre-.part: incompleto
        # (la migrazione la fa ParallelMegaDownloader al prossimo download).
        if cycle_dir.is_dir():
            def _is_final(p: Path) -> bool:
                if not p.is_file():
                    return False
                if p.name.startswith("megapy_") or p.name.endswith(".part"):
                    return False
                if ".progress.json" in p.name:
                    return False
                if p.with_name(p.name + ".progress.json").exists():
                    return False
                return p.stat().st_size > 0

            done = [p for p in cycle_dir.iterdir() if _is_final(p)]
            if done:
                log.info("[file %d] ciclo %d gia' completato (resume): %s",
                         self.file_id, cycle, done[0].name)
                self._last_final_path = done[0].resolve()
                self.progress.emit(self.file_id, cycle, 100)
                self.cycle_completed.emit(self.file_id, cycle)
                return True
            # Cartella sporca con temp file di una run interrotta: ripulisci i
            # `megapy_*` per evitare che il poller scambi vecchi byte per
            # progresso nuovo. I `.part` e i sidecar NON si toccano: servono
            # al resume del parallel client.
            for p in cycle_dir.iterdir():
                if p.is_file() and p.name.startswith("megapy_"):
                    try:
                        p.unlink()
                        log.info("[file %d] ciclo %d: rimosso temp orfano %s",
                                 self.file_id, cycle, p.name)
                    except OSError as exc:
                        log.warning("[file %d] ciclo %d: impossibile rimuovere %s: %s",
                                    self.file_id, cycle, p.name, exc)

        while True:
            if self._effective_state.is_cancelled():
                if self._is_deadline_expired():
                    limit_min = (self._file_time_limit_s or 0) // 60
                    self.abandoned.emit(
                        self.file_id, self.mega_url, self._total_attempts,
                        f"superato il limite di {limit_min} minuti",
                    )
                return False
            self._effective_state.wait_if_paused()
            attempt += 1
            self._total_attempts += 1
            if self._total_attempts > MAX_ATTEMPTS_PER_FILE:
                last_err = self._last_error_msg or "motivo sconosciuto"
                # WARNING, non ERROR: esaurire i tentativi e' un esito atteso
                # con i proxy gratuiti (mortalita' alta), non un bug. Vedi
                # rules/logging.md.
                log.warning(
                    "[file %d] ciclo %d: %d tentativi falliti, abbandono link",
                    self.file_id, cycle, MAX_ATTEMPTS_PER_FILE,
                )
                self.abandoned.emit(
                    self.file_id, self.mega_url, self._total_attempts - 1, last_err,
                )
                return False
            log.info("[file %d] ciclo %d tentativo %d: preleva proxy", self.file_id, cycle, attempt)

            proxy = self._get_proxy_blocking()
            if proxy is None:
                # Pool esausto e refill fallito: aspetta un po' e riprova,
                # a meno che non sia stato cancellato.
                log.warning("[file %d] ciclo %d: nessun proxy disponibile, riprovo fra 5s",
                            self.file_id, cycle)
                self._last_error_msg = "pool proxy vuoto, refill in attesa"
                self.failed.emit(self.file_id, cycle, f"Tentativo {attempt}: pool vuoto, attendo refill")
                if self._sleep_interruptible(5):
                    return False
                continue

            log.info("[file %d] ciclo %d tentativo %d: proxy %s:%s",
                     self.file_id, cycle, attempt, proxy["host"], proxy["port"])

            # IP check.
            try:
                client = MegaClient(proxy)
                ip = client.get_egress_ip()
                log.info("[file %d] ciclo %d: IP uscente %s", self.file_id, cycle, ip)
                # IP check riuscito: premia il proxy nel pool a punteggio.
                self.proxy_pool.record_success(proxy)
                self.ip_logged.emit(self.file_id, cycle, ip)
            except Exception as exc:
                log.warning("[file %d] ciclo %d tentativo %d: IP check fallito: %s",
                            self.file_id, cycle, attempt, exc)
                # Fallimento transitorio (endpoint IP irraggiungibile via
                # proxy): penalita' soft, non pena di morte.
                self.proxy_pool.penalize(proxy, hard=False)
                self._last_error_msg = f"IP check fallito: {exc}"
                self.failed.emit(self.file_id, cycle, f"Tentativo {attempt}: IP check fallito ({exc})")
                continue

            # Download vero (parallelo se PARALLEL_CONNECTIONS_PER_FILE > 1).
            try:
                self.progress.emit(self.file_id, cycle, 0)
                if self._effective_state.is_cancelled():
                    if self._is_deadline_expired():
                        limit_min = (self._file_time_limit_s or 0) // 60
                        self.abandoned.emit(
                            self.file_id, self.mega_url, self._total_attempts,
                            f"superato il limite di {limit_min} minuti",
                        )
                    return False
                self._effective_state.wait_if_paused()
                log.info(
                    "[file %d] ciclo %d tentativo %d: inizio download in %s (parallel=%d)",
                    self.file_id, cycle, attempt, cycle_dir, self._connections_per_file,
                )
                if self._connections_per_file > 1:
                    pd = ParallelMegaDownloader(
                        proxy_pool=self.proxy_pool,
                        n_connections=self._connections_per_file,
                        session_state=self._effective_state,
                        chunk_size=self._chunk_size_bytes,
                    )
                    final_path = pd.download(
                        self.mega_url,
                        cycle_dir,
                        resolver_proxy=proxy,
                        progress_callback=lambda p, c=cycle: self.progress.emit(self.file_id, c, p),
                        ip_callback=lambda ip, _seg, c=cycle: self.ip_logged.emit(self.file_id, c, ip),
                        speed_callback=lambda bps, dl, tot: self.throughput.emit(
                            self.file_id, float(bps), dl, tot
                        ),
                        resolved_callback=_resolved_cb,
                    )
                else:
                    final_path = client.download(
                        self.mega_url,
                        cycle_dir,
                        progress_callback=lambda p, c=cycle: self.progress.emit(self.file_id, c, p),
                        speed_callback=lambda bps, dl, tot: self.throughput.emit(
                            self.file_id, float(bps), dl, tot
                        ),
                        resolved_callback=_resolved_cb,
                    )
                abs_path = final_path.resolve() if final_path is not None else cycle_dir.resolve()
                if final_path is not None:
                    self._last_final_path = final_path.resolve()
                log.info(
                    "[file %d] ciclo %d completato al tentativo %d -> %s",
                    self.file_id, cycle, attempt, abs_path,
                )
                self.cycle_completed.emit(self.file_id, cycle)
                return True
            except (MegaCryptoDependencyError, ImportError) as exc:
                # Errore permanente d'ambiente: il proxy e' innocente.
                # Non marcare morto, non ciclare: terminare il worker.
                log.error("[file %d] ciclo %d tentativo %d: errore di configurazione: %s",
                          self.file_id, cycle, attempt, exc)
                msg = f"Errore di configurazione: {exc}"
                self.failed.emit(self.file_id, cycle, msg)
                self.fatal_error.emit(self.file_id, msg)
                return False
            except Exception as exc:
                log.warning("[file %d] ciclo %d tentativo %d: download fallito: %s",
                            self.file_id, cycle, attempt, exc)
                # Errore generico di download: per il proxy resolver e' una
                # colpa solo indiretta (i segmenti usano proxy propri, gia'
                # penalizzati dal parallel client): penalita' soft.
                self.proxy_pool.penalize(proxy, hard=False)
                self._last_error_msg = f"download fallito: {exc}"
                self.failed.emit(self.file_id, cycle, f"Tentativo {attempt}: download fallito ({exc})")
                # loop -> nuovo tentativo con nuovo proxy

    def _emit_completed_info(self) -> None:
        # Metadati per lo storico download. Best-effort: se il path non e'
        # noto o non leggibile, all_done resta comunque valido da solo.
        p = self._last_final_path
        if p is None:
            return
        try:
            size = p.stat().st_size
        except OSError:
            size = -1
        self.completed_info.emit(self.file_id, self.mega_url, p.name, size, str(p))

    def _get_proxy_blocking(self) -> dict | None:
        # Tenta get_next; se vuoto chiede refill al pool (serializzato fra worker).
        proxy = self.proxy_pool.get_next()
        if proxy is not None:
            return proxy
        log.info("[file %d] pool vuoto, richiedo refill", self.file_id)
        self.proxy_pool.refill_blocking()
        return self.proxy_pool.get_next()

    def _sleep_interruptible(self, seconds: float) -> bool:
        # Ritorna True se nel frattempo la sessione e' stata cancellata.
        step = 0.5
        elapsed = 0.0
        while elapsed < seconds:
            if self._effective_state.is_cancelled():
                return True
            time.sleep(step)
            elapsed += step
        return False
