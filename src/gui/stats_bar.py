# Cruscotto KPI: velocita' (istantanea/media/picco/minima di sessione),
# ETA, tempo a sinistra; contatori job a destra.
# Aggiornamento event-driven dal modello + tick 1s per tempo/ETA/campionamento.
from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.gui import style as _style
from src.gui.jobs_model import JobsModel
from src.gui.kpi_card import KpiCard
from src.gui.session_speed import SessionSpeedStats


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


class StatsBar(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.model = model
        self._t0: float | None = None
        self._speed_stats = SessionSpeedStats()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Sinistra: velocita'/tempo.
        self.k_speed = KpiCard("Velocità")
        self.k_avg = KpiCard("Media")
        self.k_peak = KpiCard("Picco")
        self.k_min = KpiCard("Minima")
        self.k_eta = KpiCard("ETA")
        self.k_time = KpiCard("Tempo")

        # Destra: contatori job.
        self.k_total = KpiCard("Totali")
        self.k_run = KpiCard("In corso")
        self.k_queue = KpiCard("In coda")
        self.k_fail = KpiCard("Falliti")

        for w in (
            self.k_speed, self.k_avg, self.k_peak, self.k_min, self.k_eta, self.k_time,
        ):
            layout.addWidget(w)

        layout.addStretch(1)

        for w in (self.k_total, self.k_run, self.k_queue, self.k_fail):
            layout.addWidget(w)

        self.model.aggregates_changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    def start_clock(self) -> None:
        self._t0 = time.time()
        self._speed_stats.reset()
        self._update_time()

    def refresh(self) -> None:
        p = _style.CURRENT_PALETTE
        agg = self.model.aggregates()
        total = agg["total"]

        # Velocita' istantanea ed ETA.
        bps = float(agg.get("total_speed", 0.0))
        rem = int(agg.get("total_remaining_bytes", 0))
        self.k_speed.set_value(_fmt_speed(bps))
        self.k_speed.set_color(p["accent_info"] if bps > 0 else p["text_dim"])
        self.k_eta.set_value(_fmt_eta(rem, bps))
        self.k_eta.set_color(p["text"] if bps > 0 else p["text_dim"])

        # Statistiche di sessione (media/picco/minima).
        self._refresh_speed_stats()

        # Contatori job.
        self.k_total.set_value(str(total))
        self.k_run.set_value(str(agg["running"]))
        self.k_queue.set_value(str(agg["queued"]))
        fail = agg["failed"] + agg["cancelled"] + agg["abandoned"]
        self.k_fail.set_value(str(fail))
        if fail > 0:
            self.k_fail.set_color(p["accent_fail"])
        else:
            self.k_fail.set_color(p["text_dim"])

    def _refresh_speed_stats(self) -> None:
        p = _style.CURRENT_PALETTE
        avg = self._speed_stats.average
        peak = self._speed_stats.peak
        minimum = self._speed_stats.minimum
        self.k_avg.set_value(_fmt_speed(avg))
        self.k_avg.set_color(p["accent_info"] if avg > 0 else p["text_dim"])
        self.k_peak.set_value(_fmt_speed(peak) if peak is not None else "—")
        self.k_peak.set_color(p["accent_info"] if peak else p["text_dim"])
        self.k_min.set_value(_fmt_speed(minimum) if minimum is not None else "—")
        self.k_min.set_color(p["accent_info"] if minimum else p["text_dim"])

    def refresh_theme(self) -> None:
        for w in (
            self.k_speed, self.k_avg, self.k_peak, self.k_min, self.k_eta, self.k_time,
            self.k_total, self.k_run, self.k_queue, self.k_fail,
        ):
            w.refresh_theme()
        self.refresh()

    def _on_tick(self) -> None:
        bps = float(self.model.aggregates().get("total_speed", 0.0))
        self._speed_stats.sample(bps)
        self._refresh_speed_stats()
        self._update_time()

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
