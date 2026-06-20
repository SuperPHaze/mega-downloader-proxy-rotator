# Pool rotante thread-safe di proxy con punteggio reputazionale.
# Ogni proxy ha uno score: successi lo incrementano, fallimenti lo decrementano.
# Sotto POOL_SCORE_DEAD_THRESHOLD il proxy è escluso dal round-robin, ma può
# rientrare al refill successivo se ricompare nelle liste fonti.
# Supporta refill bloccante quando si svuota: i worker chiamano refill_blocking()
# e un'unica fase di scrape+validate (serializzata da _refill_lock) ripopola il pool.
from __future__ import annotations

import logging
import threading
from typing import Callable

from src.core.config import (
    POOL_LATENCY_TIEBREAKER,
    POOL_SCORE_DEAD_THRESHOLD,
    POOL_SCORE_INITIAL,
    POOL_SCORE_MAX,
    POOL_SCORE_ON_FAILURE,
    POOL_SCORE_ON_SUCCESS,
)

log = logging.getLogger(__name__)


class ProxyPool:
    def __init__(self, refill_fn: Callable[[], list[dict]] | None = None) -> None:
        self._proxies: list[dict] = []
        # Punteggio reputazionale per ogni proxy (host, port).
        # Default POOL_SCORE_INITIAL all'inserimento.
        self._score: dict[tuple[str, str], int] = {}
        # Latency in ms misurata da Stage 1 del validator (o fornita upstream
        # da fonti come Databay). Assente nel dict = ignota.
        self._latency: dict[tuple[str, str], int | None] = {}
        self._index = 0
        self._lock = threading.Lock()
        self._refill_fn = refill_fn
        self._refill_lock = threading.Lock()

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
            total = self._count_alive_unlocked()
        log.info("Pool: aggiunti %d proxy (vivi totali: %d)", len(proxies), total)

    def _count_alive_unlocked(self) -> int:
        # Conta proxy con score > soglia dead. Caller deve tenere _lock.
        # Conta entry uniche (host,port) per evitare doppi conteggi se
        # add_many viene chiamato con un proxy gia' presente.
        seen: set[tuple[str, str]] = set()
        n = 0
        for p in self._proxies:
            key = (p["host"], p["port"])
            if key in seen:
                continue
            seen.add(key)
            if self._score.get(key, POOL_SCORE_INITIAL) > POOL_SCORE_DEAD_THRESHOLD:
                n += 1
        return n

    def get_next(self) -> dict | None:
        with self._lock:
            if not self._proxies:
                return None
            # Filtra per score sopra soglia dead, dedup su (host,port).
            seen: set[tuple[str, str]] = set()
            eligible: list[dict] = []
            for p in self._proxies:
                key = (p["host"], p["port"])
                if key in seen:
                    continue
                seen.add(key)
                if self._score.get(key, POOL_SCORE_INITIAL) > POOL_SCORE_DEAD_THRESHOLD:
                    eligible.append(p)
            if not eligible:
                return None
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
            remaining = self._count_alive_unlocked()
        log.debug("Pool: failure %s:%s score %d -> %d (vivi: %d)",
                  proxy["host"], proxy["port"], cur, new, remaining)

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
                log.info("Pool: refill saltato, %d gia' disponibili", self.size())
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
                    self._proxies.append(p)
                    added += 1
                alive_now = self._count_alive_unlocked()
            log.info("Pool: refill completato, %d nuovi (vivi totali: %d)", added, alive_now)
            return added
