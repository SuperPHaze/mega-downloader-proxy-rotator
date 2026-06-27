# Pool rotante thread-safe di proxy con punteggio reputazionale.
# Ogni proxy ha uno score: successi lo incrementano, fallimenti lo decrementano.
# Sotto POOL_SCORE_DEAD_THRESHOLD il proxy è escluso dal round-robin, ma può
# rientrare al refill successivo se ricompare nelle liste fonti.
# Supporta refill bloccante quando si svuota: i worker chiamano refill_blocking()
# e un'unica fase di scrape+validate (serializzata da _refill_lock) ripopola il pool.
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from src.core.config import (
    PARALLEL_CONNECTIONS_PER_FILE,
    POOL_LATENCY_TIEBREAKER,
    POOL_SCORE_DEAD_THRESHOLD,
    POOL_SCORE_INITIAL,
    POOL_SCORE_MAX,
    POOL_SCORE_ON_FAILURE,
    POOL_SCORE_ON_SUCCESS,
    POOL_THROUGHPUT_EMA_ALPHA,
    POOL_THROUGHPUT_TOPK_FACTOR,
    PROXY_COOLDOWN_SECONDS,
)

log = logging.getLogger(__name__)


class ProxyPool:
    def __init__(
        self,
        refill_fn: Callable[[], list[dict]] | None = None,
        selection_mode: str = "score",
        n_connections: int = PARALLEL_CONNECTIONS_PER_FILE,
    ) -> None:
        self._proxies: list[dict] = []
        # Punteggio reputazionale per ogni proxy (host, port).
        # Default POOL_SCORE_INITIAL all'inserimento.
        self._score: dict[tuple[str, str], int] = {}
        # Latency in ms misurata da Stage 1 del validator (o fornita upstream
        # da fonti come Databay). Assente nel dict = ignota.
        self._latency: dict[tuple[str, str], int | None] = {}
        # EMA del throughput osservato (byte/s) per proxy. Assente = mai
        # misurato. Usata SOLO da get_next() quando selection_mode=="throughput";
        # in modalita' "score" (default) non influisce su nulla.
        self._throughput: dict[tuple[str, str], float] = {}
        # Timestamp monotonico (time.monotonic()) fino al quale un proxy e'
        # escluso da get_next() per rate-limit temporaneo del CDN Mega
        # (403/509). NON tocca lo score (la sua "buona reputazione" resta
        # intatta e torna selezionabile da solo a scadenza), ma MENTRE e'
        # in cooldown non conta come vivo in size()/_count_alive_unlocked():
        # e' temporaneamente inutilizzabile, e farlo contare gonfierebbe
        # size() facendo saltare refill_blocking(force=False) anche quando
        # get_next() non ha piu' nulla di selezionabile. Vedi cooldown().
        self._cooldown_until: dict[tuple[str, str], float] = {}
        self._index = 0
        self._lock = threading.Lock()
        self._refill_fn = refill_fn
        self._refill_lock = threading.Lock()
        # "score" (DEFAULT, comportamento storico) | "throughput" (Leva B
        # sperimentale). Settato dall'orchestrator all'avvio sessione, non a
        # caldo durante il download.
        self.selection_mode = selection_mode
        # Numero di connessioni correnti per file (Leva A): usato per
        # dimensionare il top-K della modalita' "throughput" (K = n * FACTOR).
        self.n_connections = max(1, n_connections)
        # Telemetria di sessione per la GUI (sezione proxy): non influisce su
        # scoring/get_next, solo contatori osservativi.
        self._discarded_session = 0
        self._refill_count = 0
        self._last_refill_monotonic: float | None = None

    def add_many(self, proxies: list[dict]) -> None:
        with self._lock:
            for p in proxies:
                key = (p["host"], p["port"])
                self._proxies.append(p)
                # Un proxy ricomparso dalle fonti viene reinizializzato a score
                # base: assumiamo che la sua disponibilità sia genuinamente
                # cambiata se è stato ripubblicato. Se è nuovo, idem.
                # Caso unico in cui conserviamo lo score: la chiave esiste già
                # E lo score corrente è sopra la soglia dead (storia "buona"
                # preservata, niente reset penalizzante).
                cur = self._score.get(key)
                if cur is None or cur < POOL_SCORE_DEAD_THRESHOLD:
                    self._score[key] = POOL_SCORE_INITIAL
                lat = p.get("latency_ms")
                if isinstance(lat, (int, float)) and lat > 0:
                    self._latency[key] = int(lat)
                bps = p.get("throughput_bps")
                if isinstance(bps, (int, float)) and bps > 0:
                    self._throughput[key] = float(bps)
            total = self._count_alive_unlocked()
        log.info("Pool: aggiunti %d proxy (vivi totali: %d)", len(proxies), total)

    def _count_alive_unlocked(self) -> int:
        # Conta proxy con score > soglia dead E non in cooldown attivo (un
        # proxy in cooldown e' temporaneamente non selezionabile da
        # get_next(), quindi non deve gonfiare il conteggio: altrimenti
        # size() resta > 0 mentre il pool e' di fatto inutilizzabile, e
        # refill_blocking(force=False) salta il refill all'infinito (vedi
        # rules/proxy.md, starvation con tutto il pool in cooldown).
        # Caller deve tenere _lock. Conta entry uniche (host,port) per
        # evitare doppi conteggi se add_many viene chiamato con un proxy
        # gia' presente.
        now = time.monotonic()
        seen: set[tuple[str, str]] = set()
        n = 0
        for p in self._proxies:
            key = (p["host"], p["port"])
            if key in seen:
                continue
            seen.add(key)
            if self._score.get(key, POOL_SCORE_INITIAL) <= POOL_SCORE_DEAD_THRESHOLD:
                continue
            if self._cooldown_until.get(key, 0.0) > now:
                continue
            n += 1
        return n

    def get_next(self) -> dict | None:
        with self._lock:
            if not self._proxies:
                return None
            # Filtra per score sopra soglia dead E non in cooldown attivo,
            # dedup su (host,port). Vale per entrambi i rami sotto (score e
            # throughput): unico punto in cui si costruisce eligible.
            now = time.monotonic()
            seen: set[tuple[str, str]] = set()
            eligible: list[dict] = []
            for p in self._proxies:
                key = (p["host"], p["port"])
                if key in seen:
                    continue
                seen.add(key)
                if self._score.get(key, POOL_SCORE_INITIAL) <= POOL_SCORE_DEAD_THRESHOLD:
                    continue
                if self._cooldown_until.get(key, 0.0) > now:
                    continue
                eligible.append(p)
            if not eligible:
                return None
            if self.selection_mode == "throughput":
                pool_subset = self._throughput_top_k_unlocked(eligible)
                n = len(pool_subset)
                proxy = pool_subset[self._index % n]
                self._index = (self._index + 1) % n
                return proxy
            # Ramo "score" (DEFAULT): IDENTICO al comportamento storico.
            # Trova top score; restringi al subset top-tier.
            top_score = max(
                self._score.get((p["host"], p["port"]), POOL_SCORE_INITIAL)
                for p in eligible
            )
            top_tier = [
                p for p in eligible
                if self._score.get((p["host"], p["port"]), POOL_SCORE_INITIAL) == top_score
            ]
            if POOL_LATENCY_TIEBREAKER and len(top_tier) > 1:
                top_tier.sort(key=lambda p: (
                    self._latency.get((p["host"], p["port"])) is None,
                    self._latency.get((p["host"], p["port"])) or 0,
                ))
            n = len(top_tier)
            proxy = top_tier[self._index % n]
            self._index = (self._index + 1) % n
            return proxy

    def _throughput_top_k_unlocked(self, eligible: list[dict]) -> list[dict]:
        """Subset su cui ruotare in modalita' 'throughput': i K proxy con EMA
        piu' alta (K = n_connections * POOL_THROUGHPUT_TOPK_FACTOR), con
        l'ultimo slot riservato all'esplorazione di un proxy mai misurato (se
        ce ne sono) cosi' accumula un dato invece di restare escluso per
        sempre. Caller deve tenere _lock."""
        measured: list[tuple[float, dict]] = []
        unmeasured: list[dict] = []
        for p in eligible:
            key = (p["host"], p["port"])
            ema = self._throughput.get(key)
            if ema is None:
                unmeasured.append(p)
            else:
                measured.append((ema, p))
        measured.sort(key=lambda t: t[0], reverse=True)
        k = max(1, self.n_connections * POOL_THROUGHPUT_TOPK_FACTOR)
        top_measured = [p for _, p in measured[:k]]
        if unmeasured:
            if len(top_measured) >= k:
                top_measured = top_measured[: max(0, k - 1)]
            top_k = top_measured + unmeasured[: max(1, k - len(top_measured))]
        else:
            top_k = top_measured
        return top_k or eligible

    def record_success(self, proxy: dict) -> None:
        """Incrementa lo score del proxy di POOL_SCORE_ON_SUCCESS,
        cappato a POOL_SCORE_MAX."""
        key = (proxy["host"], proxy["port"])
        with self._lock:
            cur = self._score.get(key, POOL_SCORE_INITIAL)
            new = min(POOL_SCORE_MAX, cur + POOL_SCORE_ON_SUCCESS)
            self._score[key] = new
        log.debug("Pool: success %s:%s score %d -> %d",
                  proxy["host"], proxy["port"], cur, new)

    def record_failure(self, proxy: dict) -> None:
        """Decrementa lo score di |POOL_SCORE_ON_FAILURE|.
        Sotto POOL_SCORE_DEAD_THRESHOLD il proxy viene escluso da get_next."""
        key = (proxy["host"], proxy["port"])
        with self._lock:
            cur = self._score.get(key, POOL_SCORE_INITIAL)
            new = cur + POOL_SCORE_ON_FAILURE
            self._score[key] = new
            # Conta la transizione vivo->morto una sola volta (non a ogni
            # fallimento successivo sotto soglia): telemetria per la GUI.
            if cur > POOL_SCORE_DEAD_THRESHOLD and new <= POOL_SCORE_DEAD_THRESHOLD:
                self._discarded_session += 1
            remaining = self._count_alive_unlocked()
        log.debug("Pool: failure %s:%s score %d -> %d (vivi: %d)",
                  proxy["host"], proxy["port"], cur, new, remaining)

    def discarded_count(self) -> int:
        """Numero di proxy transitati da vivo a morto in questa sessione."""
        with self._lock:
            return self._discarded_session

    def note_refill(self) -> None:
        """Da chiamare a refill completato (refill_blocking / refresher) per
        telemetria di sessione: incrementa il contatore e timestampa."""
        with self._lock:
            self._refill_count += 1
            self._last_refill_monotonic = time.monotonic()

    def refill_count(self) -> int:
        with self._lock:
            return self._refill_count

    def seconds_since_last_refill(self) -> float | None:
        with self._lock:
            if self._last_refill_monotonic is None:
                return None
            return time.monotonic() - self._last_refill_monotonic

    def record_throughput(self, proxy: dict, bps: float) -> None:
        """Aggiorna la EMA del throughput osservato (byte/s) per il proxy.
        Additivo: usata SOLO dal ramo 'throughput' di get_next(); non tocca
        score/latency e non influisce sulla modalita' 'score' (default).
        Chiamata accanto a record_success sul completamento di un chunk."""
        if bps <= 0:
            return
        key = (proxy["host"], proxy["port"])
        with self._lock:
            prev = self._throughput.get(key)
            new = bps if prev is None else (
                POOL_THROUGHPUT_EMA_ALPHA * bps + (1 - POOL_THROUGHPUT_EMA_ALPHA) * prev
            )
            self._throughput[key] = new
        log.debug("Pool: throughput %s:%s ema -> %.1f KB/s",
                  proxy["host"], proxy["port"], new / 1024)

    def penalize(self, proxy: dict, hard: bool = False) -> None:
        """Penalità: hard=True scende immediatamente sotto soglia
        (equivalente al vecchio mark_dead). hard=False = record_failure normale."""
        if not hard:
            self.record_failure(proxy)
            return
        key = (proxy["host"], proxy["port"])
        with self._lock:
            # Forza lo score strettamente sotto la soglia dead.
            self._score[key] = POOL_SCORE_DEAD_THRESHOLD - 1
            remaining = self._count_alive_unlocked()
        log.info("Pool: penalize hard %s:%s (vivi rimasti: %d)",
                 proxy["host"], proxy["port"], remaining)

    def cooldown(self, proxy: dict, seconds: float | None = None) -> None:
        """Mette il proxy a riposo per N secondi (default PROXY_COOLDOWN_SECONDS):
        escluso da get_next finché non scade, poi torna selezionabile. NON tocca
        lo score: il proxy resta 'vivo', è solo temporaneamente non utilizzabile."""
        key = (proxy["host"], proxy["port"])
        delay = seconds if seconds is not None else PROXY_COOLDOWN_SECONDS
        with self._lock:
            self._cooldown_until[key] = time.monotonic() + delay
        log.info("Pool: cooldown %s:%s per %.0fs (rate-limit CDN)",
                 proxy["host"], proxy["port"], delay)

    def cooldown_count(self) -> int:
        """Numero di proxy attualmente in cooldown (until > now)."""
        now = time.monotonic()
        with self._lock:
            return sum(1 for until in self._cooldown_until.values() if until > now)

    def mark_dead(self, proxy: dict) -> None:
        """DEPRECATO: alias di penalize(proxy, hard=True). Nessun call-site
        interno residuo (tutti migrati a record_success/penalize); mantenuto
        solo per eventuali script esterni. Codice nuovo: usare record_failure
        (transitorio) o penalize(hard=False/True)."""
        self.penalize(proxy, hard=True)

    def set_latency(self, proxy: dict, latency_ms: int | None) -> None:
        """Registra/aggiorna la latency misurata per un proxy.
        latency_ms=None rimuove la voce (latency ignota)."""
        key = (proxy["host"], proxy["port"])
        with self._lock:
            if latency_ms is None:
                self._latency.pop(key, None)
            else:
                self._latency[key] = int(latency_ms)

    def score_of(self, proxy: dict) -> int:
        """Score corrente del proxy (sola lettura). Per la telemetria."""
        key = (proxy["host"], proxy["port"])
        with self._lock:
            return self._score.get(key, POOL_SCORE_INITIAL)

    def size(self) -> int:
        with self._lock:
            return self._count_alive_unlocked()

    def export_for_cache(self, min_score: int = 0) -> list[dict]:
        """Snapshot serializzabile dei proxy con score >= min_score.

        Ritorna dict con `host`, `port`, `protocol`, `score`, `latency_ms`.
        Il caller arricchisce con `last_seen`. Dedup su (host, port) per non
        produrre voci duplicate quando il pool e' stato refillato piu' volte.
        Thread-safe (prende `_lock`).
        """
        with self._lock:
            seen: set[tuple[str, str]] = set()
            out: list[dict] = []
            for p in self._proxies:
                key = (p["host"], p["port"])
                if key in seen:
                    continue
                seen.add(key)
                score = self._score.get(key, POOL_SCORE_INITIAL)
                if score < min_score:
                    continue
                # Anche i proxy "morti" (score sotto soglia) sono esclusi:
                # non vale la pena conservarli per la prossima sessione.
                if score < POOL_SCORE_DEAD_THRESHOLD:
                    continue
                out.append({
                    "host": p["host"],
                    "port": p["port"],
                    "protocol": p.get("protocol", "http"),
                    "score": int(score),
                    "latency_ms": self._latency.get(key),
                })
            return out

    def refill_blocking(self, force: bool = False) -> int:
        # Serializza il refill: il primo worker che entra fa lo scrape+validate,
        # gli altri aspettano sul lock e poi vedono subito il pool gia' popolato.
        # Se force=True salta il check di "ce ne sono gia'": serve al refresher
        # background che vuole sempre aggiungere nuovi proxy quando la soglia
        # vivi scende sotto un certo livello.
        if self._refill_fn is None:
            return 0
        with self._refill_lock:
            if not force and self.size() > 0:
                log.debug("Pool: refill saltato, %d gia' disponibili", self.size())
                return 0
            log.info("Pool: refill in corso (scraping + validazione, force=%s)...", force)
            try:
                fresh = self._refill_fn()
            except Exception as exc:
                log.exception("Pool: refill fallito: %s", exc)
                return 0
            added = 0
            with self._lock:
                for p in fresh:
                    key = (p["host"], p["port"])
                    # Riabilita: se era sotto soglia dead, resetta a base.
                    cur = self._score.get(key)
                    if cur is None or cur < POOL_SCORE_DEAD_THRESHOLD:
                        self._score[key] = POOL_SCORE_INITIAL
                    lat = p.get("latency_ms")
                    if isinstance(lat, (int, float)) and lat > 0:
                        self._latency[key] = int(lat)
                    bps = p.get("throughput_bps")
                    if isinstance(bps, (int, float)) and bps > 0:
                        self._throughput[key] = float(bps)
                    self._proxies.append(p)
                    added += 1
                alive_now = self._count_alive_unlocked()
            log.info("Pool: refill completato, %d nuovi (vivi totali: %d)", added, alive_now)
            # Telemetria di sessione: copre sia il refill su richiesta worker
            # (force=False) sia quello del BackgroundPoolRefresher
            # (force=True, vedi refresher.py), che passa da questa stessa
            # funzione. Non chiamato nei rami "skip"/eccezione sopra: solo a
            # refill effettivamente completato.
            self.note_refill()
            return added
