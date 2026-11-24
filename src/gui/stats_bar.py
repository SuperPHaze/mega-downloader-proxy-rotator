"""Riepilogo della coda con le tre misure utili durante un trasferimento."""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.gui.format_helpers import fmt_bytes, fmt_speed
from src.gui.i18n import t
from src.gui.jobs_model import JobsModel


def _fmt_eta(remaining_bytes: int, bps: float) -> str:
    if bps < 1 or remaining_bytes <= 0:
        return "—"
    secs = int(remaining_bytes / bps)
    if secs > 99 * 60:
        return ">99m"
    m = secs // 60
    s = secs % 60
    return f"~{m}:{s:02d}"


class StatsBar(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.model = model
        self._captions: dict[str, QLabel] = {}
        self._values: list[QLabel] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        for key in ("workspace.speed", "workspace.volume", "workspace.remaining"):
            column = QVBoxLayout()
            column.setSpacing(3)
            caption = QLabel()
            caption.setObjectName("secondaryText")
            value = QLabel("—")
            value.setObjectName("metricValue")
            self._captions[key] = caption
            self._values.append(value)
            column.addWidget(caption)
            column.addWidget(value)
            row.addLayout(column, 1)
        self.model.aggregates_changed.connect(self.refresh)
        self.retranslate()
        self.refresh()

    def refresh(self) -> None:
        agg = self.model.aggregates()
        speed = agg["total_speed"]
        values = (fmt_speed(speed), fmt_bytes(agg["total_downloaded_bytes"]),
                  _fmt_eta(agg["total_remaining_bytes"], speed))
        for label, value in zip(self._values, values):
            label.setText(value)

    def retranslate(self) -> None:
        for key, caption in self._captions.items():
            caption.setText(t(key))
