# Statistiche di velocita' di sessione (media/picco/minima) per StatsBar.
# Puro: nessun I/O, nessun riferimento a Qt. Campionato una volta al secondo
# dal tick di StatsBar, solo sui campioni con velocita' > 0 (sessioni ferme
# non abbassano la minima a zero).
from __future__ import annotations

import math

from src.core.config import SPEED_SAMPLE_CEILING_BPS


def is_plausible_bps(bps: float) -> bool:
    """Guardia anti-spike condivisa: scarta campioni non finiti, negativi o
    sopra il tetto di sicurezza (impossibile per questo downloader). Lo zero
    e' ammesso (sessione ferma): chi vuole escludere anche lo zero (vedi
    SessionSpeedStats.sample) lo fa con un controllo separato. Usata sia da
    SessionSpeedStats che dalla sparkline di StatsBar, cosi' un eventuale
    spike spurio non avvelena ne' il picco ne' il grafico."""
    return math.isfinite(bps) and 0 <= bps <= SPEED_SAMPLE_CEILING_BPS


class SessionSpeedStats:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._sum_bps: float = 0.0
        self._count: int = 0
        self._peak: float | None = None
        self._minimum: float | None = None

    def sample(self, bps: float) -> None:
        if not is_plausible_bps(bps) or bps <= 0:
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
