# Background pool refresher: thread daemon che monitora il numero di proxy
# vivi nel pool e, quando scende sotto soglia, lancia uno scrape+validate
# in background SENZA bloccare i worker che intanto continuano a scaricare.
#
# Convive con `ProxyPool.refill_blocking()` (che invece e' chiamato dai worker
# come reazione al pool vuoto): il refresher usa `force=True` per aggiungere
# proxy freschi anche se il pool non e' a zero, mantenendolo sopra soglia.
#
# Isteresi armato/disarmato: senza isteresi, un pool che oscilla intorno a
# una soglia singola scatena refill ripetuti a raffica (osservato: 66 refill
# in una sessione, picchi di ~200 thread -> access violation nei thread di
# validazione). Con l'isteresi il refresher si "disarma" subito dopo un
# refill e si riarma solo quando il pool torna sano (>= HIGH); in piu' un
# intervallo minimo (MIN_INTERVAL_S) impedisce due refill troppo vicini anche
# nel caso limite di un riarmo immediato.
from __future__ import annotations

import logging
import threading
import time

from src.core.config import (
    POOL_REFRESH_INTERVAL,
    POOL_REFRESH_MAX_INTERVAL_S,
    POOL_REFRESH_MIN_INTERVAL_S,
    POOL_REFRESH_THRESHOLD_HIGH,
    POOL_REFRESH_THRESHOLD_LOW,
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
        threshold_low: int = POOL_REFRESH_THRESHOLD_LOW,
        threshold_high: int = POOL_REFRESH_THRESHOLD_HIGH,
        min_interval_s: float = POOL_REFRESH_MIN_INTERVAL_S,
        max_interval_s: float = POOL_REFRESH_MAX_INTERVAL_S,
    ) -> None:
        self.pool = pool
        self.session_state = session_state
        self.interval = interval_s
        self.threshold_low = threshold_low
        self.threshold_high = threshold_high
        self.min_interval = min_interval_s
        self.max_interval = max_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Timestamp dell'ultimo refill completato (incluso il setup iniziale
        # che popola il pool prima di start()). Inizializzato a `start()`.
        self._last_refill_ts: float = 0.0
        self._initial_force: bool = False
        # Stato dell'isteresi: armato = puo' scattare un refill quando i vivi
        # scendono sotto threshold_low. Dopo un refill si disarma; si riarma
        # solo quando i vivi tornano >= threshold_high.
        self._armed: bool = True

    def start(self, initial_force: bool = False) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._initial_force = initial_force
        self._armed = True
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
            "Refresher avviato: interval=%.1fs low=%d high=%d min_interval=%.0fs "
            "max_interval=%.0fs initial_force=%s",
            self.interval, self.threshold_low, self.threshold_high,
            self.min_interval, self.max_interval, initial_force,
        )

    def update_thresholds(self, low: int, high: int) -> None:
        """Aggiorna le soglie di refill in base al carico attuale.

        Chiamato dall'orchestrator quando cambia il numero di download attivi.
        Thread-safe: in CPython l'assegnamento di int e' atomico (GIL), le
        soglie vengono lette da _tick() sul thread daemon al prossimo ciclo.
        """
        self.threshold_low = low
        self.threshold_high = high
        log.info("Refresher: soglie aggiornate low=%d high=%d", low, high)

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

            self._tick()

    def _tick(self) -> None:
        """Un singolo check (+ eventuale refill). Isolato da `_run` per
        permettere ai test di pilotare l'isteresi senza thread/sleep reali."""
        alive = self.pool.size()
        elapsed_since_refill = time.monotonic() - self._last_refill_ts

        # Riarmo: una volta che il pool e' tornato sano, riabilita il
        # trigger sotto-soglia (altrimenti resterebbe disarmato per il
        # resto della sessione dopo il primo refill).
        if not self._armed and alive >= self.threshold_high:
            log.debug("Refresher: pool tornato sano (vivi=%d >= %d), riarmo",
                      alive, self.threshold_high)
            self._armed = True

        below_threshold = self._armed and alive < self.threshold_low
        timed_out = elapsed_since_refill > self.max_interval
        past_min_interval = elapsed_since_refill >= self.min_interval

        if not (below_threshold or timed_out) or not past_min_interval:
            log.debug(
                "Refresher: skip (vivi=%d armato=%s %ds dall'ultimo refill)",
                alive, self._armed, int(elapsed_since_refill),
            )
            return

        if below_threshold:
            log.info(
                "Refresher: pool sotto soglia (vivi=%d < %d), refill in corso",
                alive, self.threshold_low,
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
            self._armed = False
            log.info("Refresher: refill completato (+%d proxy)", added)
        except Exception as exc:
            log.exception("Refresher: errore durante refill: %s", exc)
