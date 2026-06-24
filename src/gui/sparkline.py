# Micro-grafico a linea di una serie temporale (sparkline). La matematica di
# normalizzazione e' estratta in sparkline_points() per restare testabile
# senza Qt; il widget si limita a bufferizzare i campioni e disegnare.
from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.gui import style as _style


def sparkline_points(values: list[float], w: float, h: float) -> list[tuple[float, float]]:
    """Coordinate (x, y) della polilinea per `values` in un'area w x h.

    Normalizzazione: minimo fisso a 0 (in basso), massimo = max(values)
    (in alto), con un margine di 2px sopra e sotto. Meno di 2 punti -> [].
    """
    n = len(values)
    if n < 2:
        return []
    margin = 2.0
    usable_h = max(0.0, h - 2 * margin)
    hi = max(values)
    points: list[tuple[float, float]] = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * w
        frac = (v / hi) if hi > 0 else 0.0
        y = margin + (1.0 - frac) * usable_h
        points.append((x, y))
    return points


class Sparkline(QWidget):
    def __init__(self, max_points: int = 60, color_key: str = "accent_info") -> None:
        super().__init__()
        self._buffer: deque[float] = deque(maxlen=max_points)
        self._color_key = color_key
        self.setMinimumSize(72, 24)
        self.setMaximumHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add_sample(self, value: float) -> None:
        self._buffer.append(value)
        self.update()

    def reset(self) -> None:
        self._buffer.clear()
        self.update()

    def refresh_theme(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if len(self._buffer) < 2:
            return
        w = float(self.width())
        h = float(self.height())
        points = sparkline_points(list(self._buffer), w, h)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(_style.CURRENT_PALETTE[self._color_key])
        painter.setPen(QPen(color, 1.5))
        painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
        painter.end()
