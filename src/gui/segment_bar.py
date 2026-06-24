# Barra orizzontale divisa in segmenti proporzionali (es. stato dei job).
# La matematica delle larghezze e' estratta in segment_widths() per restare
# testabile senza Qt; il widget si limita a disegnare i rettangoli.
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src.gui import style as _style


def segment_widths(values: list[int], total_width: float) -> list[float]:
    """Larghezza di ciascun segmento proporzionale a `values`, in modo che
    la somma sia esattamente `total_width` (il resto di arrotondamento va al
    segmento piu' grande). `sum(values) <= 0` -> tutte le larghezze a 0.0."""
    total = sum(values)
    n = len(values)
    if total <= 0:
        return [0.0] * n
    widths = [v / total * total_width for v in values]
    diff = total_width - sum(widths)
    idx_max = max(range(n), key=lambda i: widths[i])
    widths[idx_max] += diff
    return widths


class SegmentBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._segments: list[tuple[int, str]] = []
        self.setMinimumSize(72, 14)
        self.setMaximumHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_segments(self, segments: list[tuple[int, str]]) -> None:
        self._segments = list(segments)
        self.update()

    def refresh_theme(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = _style.CURRENT_PALETTE
        w = float(self.width())
        h = float(self.height())
        radius = 4.0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Traccia di sfondo (visibile anche a total=0).
        painter.setBrush(QColor(p["border"]))
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.setClipPath(clip)

        values = [v for v, _ in self._segments]
        widths = segment_widths(values, w)
        x = 0.0
        for (value, color_key), seg_w in zip(self._segments, widths):
            if value > 0 and seg_w > 0:
                painter.setBrush(QColor(p[color_key]))
                painter.drawRect(QRectF(x, 0, seg_w, h))
            x += seg_w
        painter.end()
