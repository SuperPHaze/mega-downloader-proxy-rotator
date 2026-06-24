# Cruscotto "spinta", versione compatta: zona velocita' (valore guida +
# sparkline + sub-info media/picco/minima/ETA/tempo) e zona download
# (totale + barra segmentata + conteggi), separate da una linea verticale
# interna. Aggiornamento event-driven dal modello + tick 1s per
# tempo/ETA/campionamento.
from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.gui import style as _style
from src.gui.jobs_model import JobsModel
from src.gui.segment_bar import SegmentBar
from src.gui.session_speed import SessionSpeedStats, is_plausible_bps
from src.gui.sparkline import Sparkline


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


def _micro_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setFont(QFont("Segoe UI", 8))
    return lbl


def _sub_label() -> QLabel:
    lbl = QLabel()
    lbl.setFont(QFont("Consolas", 8))
    return lbl


class StatsBar(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.model = model
        self._t0: float | None = None
        self._speed_stats = SessionSpeedStats()
        self._eta_text = "—"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(6)

        layout.addWidget(self._build_speed_zone(), 2)
        self._inner_separator = QFrame()
        self._inner_separator.setFixedWidth(1)
        layout.addWidget(self._inner_separator, 0)
        layout.addWidget(self._build_job_zone(), 1)

        self._restyle_separator()
        self._restyle_micro_labels()

        self.model.aggregates_changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    # ---- costruzione zone ---------------------------------------------------

    def _build_speed_zone(self) -> QWidget:
        zone = QWidget()
        v = QVBoxLayout(zone)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self._speed_micro = _micro_label("Velocità")
        v.addWidget(self._speed_micro)

        self._speed_value = QLabel("—")
        fv = QFont("Consolas", 16)
        fv.setWeight(QFont.Weight.Medium)
        self._speed_value.setFont(fv)
        v.addWidget(self._speed_value)

        self._speed_spark = Sparkline(color_key="accent_info")
        self._speed_spark.setMinimumSize(56, 22)
        v.addWidget(self._speed_spark)

        self._speed_substats = _sub_label()
        v.addWidget(self._speed_substats)

        self._speed_eta_time = _sub_label()
        v.addWidget(self._speed_eta_time)

        return zone

    def _build_job_zone(self) -> QWidget:
        zone = QWidget()
        v = QVBoxLayout(zone)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self._job_micro = _micro_label("Download")
        v.addWidget(self._job_micro)

        self._job_total = QLabel("—")
        v.addWidget(self._job_total)

        self._job_segment = SegmentBar()
        v.addWidget(self._job_segment)

        self._job_counts = _sub_label()
        v.addWidget(self._job_counts)

        return zone

    # ---- ciclo di vita sessione ---------------------------------------------

    def start_clock(self) -> None:
        self._t0 = time.time()
        self._speed_stats.reset()
        self._speed_spark.reset()
        self._update_eta_time_line()

    # ---- refresh dati --------------------------------------------------------

    def refresh(self) -> None:
        p = _style.CURRENT_PALETTE
        agg = self.model.aggregates()
        total = agg["total"]

        bps = float(agg.get("total_speed", 0.0))
        rem = int(agg.get("total_remaining_bytes", 0))
        self._speed_value.setText(_fmt_speed(bps))
        self._speed_value.setStyleSheet(
            f"color: {p['accent_info'] if bps > 0 else p['text_dim']};"
        )
        self._refresh_speed_substats()
        self._eta_text = _fmt_eta(rem, bps)
        self._update_eta_time_line()

        running = agg["running"]
        queued = agg["queued"]
        completed = agg["completed"]
        failed_tot = agg["failed"] + agg["cancelled"] + agg["abandoned"]

        self._job_total.setText(
            f"<span style='font-size:13pt;font-weight:500;color:{p['text']};'>{total}</span>"
            f" <span style='font-size:8pt;color:{p['text_dim']};'>totali</span>"
        )
        self._job_segment.set_segments([
            (running, "accent_info"),
            (queued, "text_dim"),
            (completed, "accent_ok"),
            (failed_tot, "accent_fail"),
        ])
        fail_color = p["accent_fail"] if failed_tot > 0 else p["text_dim"]
        self._job_counts.setText(
            f"{running} corso · {queued} coda · {completed} ok · "
            f"<span style='color:{fail_color};'>{failed_tot} fall.</span>"
        )
        self._job_counts.setStyleSheet(f"color: {p['text_dim']};")

    def _refresh_speed_substats(self) -> None:
        p = _style.CURRENT_PALETTE
        avg = self._speed_stats.average
        peak = self._speed_stats.peak
        minimum = self._speed_stats.minimum
        self._speed_substats.setText(
            f"med {_fmt_speed(avg)} · pic "
            f"{_fmt_speed(peak) if peak is not None else '—'} · min "
            f"{_fmt_speed(minimum) if minimum is not None else '—'}"
        )
        self._speed_substats.setStyleSheet(f"color: {p['text_dim']};")

    def _update_eta_time_line(self) -> None:
        p = _style.CURRENT_PALETTE
        if self._t0 is None:
            clock = "—"
        else:
            sec = int(time.time() - self._t0)
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            clock = f"{h:02d}:{m:02d}:{s:02d}"
        self._speed_eta_time.setText(f"ETA {self._eta_text} · {clock}")
        self._speed_eta_time.setStyleSheet(f"color: {p['text_dim']};")

    def _on_tick(self) -> None:
        bps = float(self.model.aggregates().get("total_speed", 0.0))
        # Stessa guardia anti-spike di SessionSpeedStats: un campione assurdo
        # non deve finire ne' nelle statistiche ne' nel grafico sparkline.
        if is_plausible_bps(bps):
            self._speed_stats.sample(bps)
            self._speed_spark.add_sample(bps)
        self._refresh_speed_substats()
        self._update_eta_time_line()

    # ---- tema -----------------------------------------------------------------

    def _restyle_separator(self) -> None:
        p = _style.CURRENT_PALETTE
        self._inner_separator.setStyleSheet(
            f"QFrame {{ background-color: {p['border']}; border: none; }}"
        )

    def _restyle_micro_labels(self) -> None:
        p = _style.CURRENT_PALETTE
        for lbl in (self._speed_micro, self._job_micro):
            lbl.setStyleSheet(
                f"color: {p['text_dim']}; letter-spacing: 1px; border: none;"
            )

    def refresh_theme(self) -> None:
        self._restyle_separator()
        self._restyle_micro_labels()
        self._speed_spark.refresh_theme()
        self._job_segment.refresh_theme()
        self.refresh()
