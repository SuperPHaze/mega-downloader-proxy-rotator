# Cruscotto KPI: velocita', ETA, pool proxy, completati, tempo.
# Aggiornamento event-driven dal modello + tick 1s per tempo/ETA.
from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.gui import style as _style
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


def _fmt_speed(bps: float) -> str:
    if bps < 1:
        return "—"
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


class _KpiCard(QFrame):
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


class StatsBar(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.model = model
        self._t0: float | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.k_speed = _KpiCard("Velocità")
        self.k_eta = _KpiCard("ETA")
        self.k_pool = _KpiCard("Pool proxy")
        self.k_done = _KpiCard("Completati")
        self.k_time = _KpiCard("Tempo")

        # KPI secondari compatti (senza card, inline).
        self.k_total = _KpiCard("Totali")
        self.k_queue = _KpiCard("In coda")
        self.k_run = _KpiCard("In corso")
        self.k_fail = _KpiCard("Falliti")
        self.k_validation = _KpiCard("Validazione")
        self.k_validation.set_value("—")

        for w in (
            self.k_speed, self.k_eta, self.k_pool, self.k_done, self.k_time,
        ):
            layout.addWidget(w)

        layout.addStretch(1)

        for w in (self.k_total, self.k_queue, self.k_run, self.k_fail, self.k_validation):
            layout.addWidget(w)

        self.model.aggregates_changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_time)
        self._tick.start()
        self.refresh()

    def start_clock(self) -> None:
        self._t0 = time.time()
        self._update_time()

    def refresh(self) -> None:
        p = _style.CURRENT_PALETTE
        agg = self.model.aggregates()
        total = agg["total"]

        # Velocita' e ETA.
        bps = float(agg.get("total_speed", 0.0))
        rem = int(agg.get("total_remaining_bytes", 0))
        self.k_speed.set_value(_fmt_speed(bps))
        self.k_speed.set_color(p["accent_info"] if bps > 0 else p["text_dim"])
        self.k_eta.set_value(_fmt_eta(rem, bps))
        self.k_eta.set_color(p["text"] if bps > 0 else p["text_dim"])

        # Completati X/N.
        done = agg["completed"]
        self.k_done.set_value(f"{done}/{total}" if total else "—")
        self.k_done.set_color(p["accent_ok"] if done > 0 else p["text_dim"])

        # KPI secondari.
        self.k_total.set_value(str(total))
        self.k_queue.set_value(str(agg["queued"]))
        self.k_run.set_value(str(agg["running"]))
        fail = agg["failed"] + agg["cancelled"] + agg["abandoned"]
        self.k_fail.set_value(str(fail))
        if fail > 0:
            self.k_fail.set_color(p["accent_fail"])
        else:
            self.k_fail.set_color(p["text_dim"])

    # ---- slot per pool/validazione ----------------------------------------

    def on_pool_size(self, n: int) -> None:
        p = _style.CURRENT_PALETTE
        self.k_pool.set_value(str(n))
        if n == 0:
            self.k_pool.set_color(p["accent_fail"])
        elif n < 5:
            self.k_pool.set_color(p["accent_warn"])
        else:
            self.k_pool.set_color(p["accent_ok"])

    def on_validation_progress(self, done: int, total: int, alive: int) -> None:
        p = _style.CURRENT_PALETTE
        self.k_validation.set_value(f"{done}/{total}")
        self.k_validation.set_color(p["accent_warn"])

    def on_validation_done(self) -> None:
        p = _style.CURRENT_PALETTE
        self.k_validation.set_value("OK")
        self.k_validation.set_color(p["accent_ok"])

    def reset_pool_stats(self) -> None:
        p = _style.CURRENT_PALETTE
        self.k_pool.set_value("—")
        self.k_pool.set_color(p["text_dim"])
        self.k_validation.set_value("—")
        self.k_validation.set_color(p["text_dim"])

    def refresh_theme(self) -> None:
        for w in (
            self.k_speed, self.k_eta, self.k_pool, self.k_done, self.k_time,
            self.k_total, self.k_queue, self.k_run, self.k_fail, self.k_validation,
        ):
            w.refresh_theme()
        self.refresh()

    def _update_time(self) -> None:
        p = _style.CURRENT_PALETTE
        if self._t0 is None:
            self.k_time.set_value("—")
            self.k_time.set_color(p["text_dim"])
            return
        sec = int(time.time() - self._t0)
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        self.k_time.set_value(f"{h:02d}:{m:02d}:{s:02d}")
        self.k_time.set_color(p["accent_info"])
