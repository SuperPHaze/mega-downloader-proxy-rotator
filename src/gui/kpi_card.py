# Card KPI riutilizzabile: etichetta sopra, valore grande sotto.
# Condivisa da StatsBar e ProxyBar.
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from src.gui import style as _style


class KpiCard(QFrame):
    """Piccola card metrica: etichetta sopra, numero grande sotto."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        p = _style.CURRENT_PALETTE
        self.setStyleSheet(
            f"QFrame {{ background-color: {p['panel_alt']}; "
            f"border: 1px solid {p['border']}; border-radius: 6px; }}"
        )
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 4, 10, 4)
        v.setSpacing(0)

        self._lbl = QLabel(label.upper())
        self._lbl.setStyleSheet(
            f"color: {p['text_dim']}; font-size: 8pt; letter-spacing: 1px; border: none;"
        )
        f = QFont("Segoe UI", 8)
        self._lbl.setFont(f)

        self._val = QLabel("—")
        fv = QFont("Consolas", 13)
        fv.setBold(True)
        self._val.setFont(fv)
        self._val.setStyleSheet(f"color: {p['text']}; border: none;")

        v.addWidget(self._lbl)
        v.addWidget(self._val)

    def set_value(self, v: str) -> None:
        if self._val.text() != v:
            self._val.setText(v)

    def set_color(self, color: str) -> None:
        self._val.setStyleSheet(f"color: {color}; border: none;")

    def refresh_theme(self) -> None:
        p = _style.CURRENT_PALETTE
        self.setStyleSheet(
            f"QFrame {{ background-color: {p['panel_alt']}; "
            f"border: 1px solid {p['border']}; border-radius: 6px; }}"
        )
        self._lbl.setStyleSheet(
            f"color: {p['text_dim']}; font-size: 8pt; letter-spacing: 1px; border: none;"
        )
