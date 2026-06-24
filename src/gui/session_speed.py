# Statistiche di velocita' di sessione (media/picco/minima) per StatsBar.
# Puro: nessun I/O, nessun riferimento a Qt. Campionato una volta al secondo
# dal tick di StatsBar, solo sui campioni con velocita' > 0 (sessioni ferme
# non abbassano la minima a zero).
from __future__ import annotations


class SessionSpeedStats:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._sum_bps: float = 0.0
        self._count: int = 0
        self._peak: float | None = None
        self._minimum: float | None = None

    def sample(self, bps: float) -> None:
        if bps <= 0:
            return
        self._sum_bps += bps
        self._count += 1
        self._peak = bps if self._peak is None else max(self._peak, bps)
        self._minimum = bps if self._minimum is None else min(self._minimum, bps)

    @property
    def average(self) -> float:
        return self._sum_bps / self._count if self._count else 0.0

    @property
    def peak(self) -> float | None:
        return self._peak

    @property
    def minimum(self) -> float | None:
        return self._minimum
