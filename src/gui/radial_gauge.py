# Gauge radiale (anello/donut) per la velocita' istantanea come frazione del
# picco di sessione. La matematica della frazione e' estratta in
# gauge_fraction() per restare testabile senza Qt; il widget si limita a
# bufferizzare lo stato e disegnare.
from __future__ import annotations

import math

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from src.gui import style as _style

_PEN_WIDTH = 9.0
_FULL_TURN_16THS = 360 * 16


def gauge_fraction(current: float, peak: float) -> float:
    """Frazione `current/peak` clampata in [0, 1].

    `peak <= 0` o valori non finiti -> 0.0 (niente fondo scala su cui
    calcolare una percentuale sensata).
    """
    if not math.isfinite(current) or not math.isfinite(peak) or peak <= 0:
        return 0.0
    return max(0.0, min(1.0, current / peak))


class RadialGauge(QWidget):
    def __init__(self, color_key: str = "accent_info") -> None:
        super().__init__()
        self._color_key = color_key
        self._fraction: float = 0.0
        self._value_text: str = "—"
        self._unit_text: str = ""
        self.setFixedSize(84, 84)

    def set_value(self, fraction: float, value_text: str, unit_text: str) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._value_text = value_text
        self._unit_text = unit_text
        self.update()

    def reset(self) -> None:
        self._fraction = 0.0
        self._value_text = "—"
        self._unit_text = ""
        self.update()

    def refresh_theme(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = _style.CURRENT_PALETTE
        w = float(self.width())
        h = float(self.height())
        margin = _PEN_WIDTH / 2
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Traccia di sfondo (cerchio intero).
        track_pen = QPen(QColor(p["border"]), _PEN_WIDTH)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, _FULL_TURN_16THS)

        # Arco di valore: parte dall'alto (ore 12), va in senso orario.
        if self._fraction > 0:
            value_pen = QPen(QColor(p[self._color_key]), _PEN_WIDTH)
            value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(value_pen)
            span = -int(self._fraction * _FULL_TURN_16THS)
            painter.drawArc(rect, 90 * 16, span)

        # Testo al centro: valore + unita'.
        painter.setPen(QColor(p["text"]))
        value_font = QFont("Consolas", 16)
        value_font.setWeight(QFont.Weight.Medium)
        painter.setFont(value_font)
        value_rect = QRectF(0, h / 2 - 16, w, 18)
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, self._value_text)

        if self._unit_text:
            painter.setPen(QColor(p["text_dim"]))
            unit_font = QFont("Segoe UI", 8)
            painter.setFont(unit_font)
            unit_rect = QRectF(0, h / 2 + 2, w, 14)
            painter.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, self._unit_text)

        painter.end()
