# Background pool refresher: thread daemon che monitora il numero di proxy
# vivi nel pool e, quando scende sotto soglia, lancia uno scrape+validate
# in background SENZA bloccare i worker che intanto continuano a scaricare.
#
# Convive con `ProxyPool.refill_blocking()` (che invece e' chiamato dai worker
# come reazione al pool vuoto): il refresher usa `force=True` per aggiungere
# proxy freschi anche se il pool non e' a zero, mantenendolo sopra soglia.
from __future__ import annotations

import logging
import threading
import time

from src.core.config import (
    POOL_REFRESH_INTERVAL,
    POOL_REFRESH_MAX_INTERVAL_S,
    POOL_REFRESH_THRESHOLD,
)
from src.core.state import SessionState
from src.proxy.pool import ProxyPool

log = logging.getLogger(__name__)


class BackgroundPoolRefresher:
    def __init__(
        self,
        pool: ProxyPool,
        session_state: SessionState,
        interval_s: float = POOL_REFRESH_INTERVAL,
        threshold: int = POOL_REFRESH_THRESHOLD,
        max_interval_s: float = POOL_REFRESH_MAX_INTERVAL_S,
    ) -> None:
        self.pool = pool
        self.session_state = session_state
        self.interval = interval_s
        self.threshold = threshold
        self.max_interval = max_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Timestamp dell'ultimo refill completato (incluso il setup iniziale
        # che popola il pool prima di start()). Inizializzato a `start()`.
        self._last_refill_ts: float = 0.0
        self._initial_force: bool = False

    def start(self, initial_force: bool = False) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._initial_force = initial_force
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="PoolRefresher",
        )
        # Considera il setup iniziale come "ultimo refill": non vogliamo che
        # max_interval scatti subito al primo tick. Se initial_force=True
        # azzeriamo il ts cosi' il primo tick (senza wait) entra subito nel
        # ramo timed_out.
        self._last_refill_ts = 0.0 if initial_force else time.monotonic()
        self._thread.start()
        log.info(
            "Refresher avviato: interval=%.1fs threshold=%d max_interval=%.0fs "
            "initial_force=%s",
            self.interval, self.threshold, self.max_interval, initial_force,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        log.info("Refresher fermato")

    def _run(self) -> None:
        # Primo check dopo `interval` (non subito: il setup iniziale ha appena
        # popolato il pool, inutile rifare uno scrape immediato).
        # Eccezione: initial_force=True salta il primo wait per forzare un
        # refill subito (usato dopo un hot-start da cache, per rinforzare il
        # pool con uno scrape completo in background).
        first_iteration = True
        while True:
            if first_iteration and self._initial_force:
                first_iteration = False
            else:
                if self._stop.wait(self.interval):
                    return
                first_iteration = False
            if self.session_state.is_cancelled():
                log.info("Refresher: sessione cancellata, esco")
                return
            alive = self.pool.size()
            elapsed_since_refill = time.monotonic() - self._last_refill_ts
            # Doppia condizione (OR): refill se sotto soglia OPPURE se l'ultimo
            # refill e' troppo vecchio. Il trigger tempo-based copre il caso in
            # cui il pool oscilla appena sopra soglia ma i proxy si degradano
            # silenziosamente (rate-limit progressivo, captive portal).
            below_threshold = alive < self.threshold
            timed_out = elapsed_since_refill > self.max_interval
            if not below_threshold and not timed_out:
                log.debug(
                    "Refresher: pool ok (vivi=%d >= %d, %ds dall'ultimo refill), skip",
                    alive, self.threshold, int(elapsed_since_refill),
                )
                continue
            if below_threshold:
                log.info(
                    "Refresher: pool sotto soglia (vivi=%d < %d), refill in corso",
                    alive, self.threshold,
                )
            else:
                log.info(
                    "Refresher: refill forzato: nessun refresh da %ds (vivi=%d)",
                    int(elapsed_since_refill), alive,
                )
            try:
                added = self.pool.refill_blocking(force=True)
                # Aggiorna timestamp solo a refill completato: se solleva,
                # il prossimo tick riprova subito invece di aspettare max_interval.
                self._last_refill_ts = time.monotonic()
                log.info("Refresher: refill completato (+%d proxy)", added)
            except Exception as exc:
                log.exception("Refresher: errore durante refill: %s", exc)
