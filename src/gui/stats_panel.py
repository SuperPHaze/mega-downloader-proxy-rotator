"""Statistiche della sessione, apribili sotto la coda di download."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.i18n import t
from src.gui.format_helpers import (
    build_header_summary,
    fmt_bytes,
    fmt_hhmmss,
    fmt_mmss,
    fmt_speed,
    link_caption,
)
from src.gui.jobs_model import (
    JobsModel,
    STATUS_RUNNING,
)
from src.gui.radial_gauge import RadialGauge, gauge_fraction
from src.gui.segment_bar import SegmentBar
from src.gui.session_clock import SessionClock
from src.gui.session_speed import SessionSpeedStats, is_plausible_bps

# Stato del modello -> chiave i18n. La MAPPA e' di stats_panel, quindi il testo
# mostrato si traduce; lo stato grezzo (chiave) appartiene a jobs_model e resta
# com'e', anche nel fallback quando non e' mappato.
_TERMINAL_STATUS_KEY = {
    "completato": "stats_panel.status_completed",
    "fallito": "stats_panel.status_failed",
    "annullato": "stats_panel.status_cancelled",
    "abbandonato": "stats_panel.status_abandoned",
    "in_corso": "stats_panel.status_running",
    "in_coda": "stats_panel.status_queued",
}


def _status_label(status: str) -> str:
    key = _TERMINAL_STATUS_KEY.get(status)
    return t(key) if key else status


class StatsPanel(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.model = model
        self._clock = SessionClock()
        self._speed_stats = SessionSpeedStats()
        self._captions: dict[str, QLabel] = {}
        self._values: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("sectionTitle")
        heading.addWidget(self._title_lbl, 1)
        self._copy_btn = QPushButton()
        self._copy_btn.setObjectName("textAction")
        self._copy_btn.clicked.connect(self._on_copy)
        heading.addWidget(self._copy_btn)
        layout.addLayout(heading)

        self._empty = QLabel()
        self._empty.setObjectName("secondaryText")
        self._empty.setWordWrap(True)
        layout.addWidget(self._empty)
        self._body = QWidget()
        layout.addWidget(self._body)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(7)
        measurements = QHBoxLayout()
        measurements.setSpacing(14)
        self._gauge = RadialGauge(color_key="accent_info")
        measurements.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignVCenter)
        rows = QGridLayout()
        rows.setHorizontalSpacing(10)
        rows.setVerticalSpacing(4)
        for index, name in enumerate(("elapsed", "effective", "file_average", "sample_average", "peak", "minimum")):
            label = QLabel()
            label.setObjectName("secondaryText")
            value = QLabel()
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._captions[name] = label
            self._values[name] = value
            rows.addWidget(label, index, 0)
            rows.addWidget(value, index, 1)
        rows.setColumnStretch(0, 1)
        measurements.addLayout(rows, 1)
        body.addLayout(measurements)
        self._completion = QLabel()
        self._completion.setObjectName("secondaryText")
        body.addWidget(self._completion)
        self._segments = SegmentBar()
        self._segments.setFixedHeight(6)
        body.addWidget(self._segments)

        self.model.aggregates_changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.retranslate()

    def start_clock(self) -> None:
        """Resetta clock e statistiche e avvia la sessione. Chiamato da MainWindow su 'Avvia'."""
        self._clock.reset()
        self._clock.start(time.time())
        self._speed_stats.reset()
        self.refresh()

    # ---- tick 1 Hz -------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _on_tick(self) -> None:
        agg = self.model.aggregates()
        bps_inst = float(agg.get("total_speed", 0.0))
        if is_plausible_bps(bps_inst):
            self._speed_stats.sample(bps_inst)
        now = time.time()
        self._clock.update(now, bool(agg.get("all_terminated", False)))
        self._refresh_labels(agg, now)

    # ---- refresh dati ----------------------------------------------------

    def refresh(self) -> None:
        """Refresh senza campionare la velocita' (evita doppio sample)."""
        agg = self.model.aggregates()
        self._refresh_labels(agg, time.time())

    def _refresh_labels(self, agg: dict, now: float) -> None:
        total = agg["total"]
        self._empty.setVisible(total == 0)
        self._body.setVisible(total > 0)
        self._copy_btn.setVisible(total > 0)
        if total == 0:
            return
        elapsed = self._clock.elapsed(now)
        volume = agg["total_downloaded_bytes"]
        self._values["elapsed"].setText(fmt_hhmmss(elapsed))
        self._values["effective"].setText(fmt_speed(volume / elapsed if elapsed else 0))
        self._values["file_average"].setText(fmt_speed(agg["arithmetic_avg_bps"] or 0))
        self._values["sample_average"].setText(fmt_speed(self._speed_stats.average))
        self._values["peak"].setText(fmt_speed(self._speed_stats.peak or 0))
        self._values["minimum"].setText(fmt_speed(self._speed_stats.minimum or 0))

        speed = agg["total_speed"]
        ratio = gauge_fraction(speed, self._speed_stats.peak or 0)
        number, _, unit = fmt_speed(speed).partition(" ")
        self._gauge.set_value(ratio, number, unit)
        hint = t("stats_bar.pct_of_peak", pct=round(ratio * 100))
        self._gauge.setToolTip(hint)
        self._gauge.setAccessibleName(f"{fmt_speed(speed)} · {hint}")
        ok = agg["completed"]
        self._completion.setText(t("stats_panel.finished_of", done=ok, total=total, pct=round(ok * 100 / total)))
        failed = agg["failed"] + agg["cancelled"] + agg["abandoned"]
        self._segments.set_segments([(agg["running"], "accent_info"), (agg["queued"], "border_strong"),
                                     (ok, "accent_ok"), (failed, "accent_fail")])
        summary = build_header_summary(elapsed, volume, volume / elapsed if elapsed else 0,
                                       {"total": total, "ok": ok, "fallen": failed}, agg["all_terminated"])
        self._segments.setAccessibleName(summary)
        self._segments.setToolTip(summary)

    def _on_copy(self) -> None:
        agg = self.model.aggregates()
        now = time.time()
        elapsed = self._clock.elapsed(now)
        all_term = bool(agg.get("all_terminated", False))
        total_bytes = int(agg.get("total_downloaded_bytes", 0))

        eff_bps = total_bytes / elapsed if elapsed > 0 and total_bytes > 0 else 0.0
        eff_str = fmt_speed(eff_bps) if eff_bps > 0 else "—"

        arith = agg.get("arithmetic_avg_bps")
        peak = self._speed_stats.peak
        minimum = self._speed_stats.minimum

        total = int(agg.get("total", 0))
        ok = int(agg.get("completed", 0))
        failed = int(agg.get("failed", 0))
        abandoned = int(agg.get("abandoned", 0))
        cancelled = int(agg.get("cancelled", 0))
        running = int(agg.get("running", 0))
        queued = int(agg.get("queued", 0))
        tasso_str = f"{round(ok / total * 100)}%" if total > 0 else "—"

        status_str = t(
            "stats_panel.session_completed" if all_term
            else "stats_panel.session_running"
        )
        lines = [
            t("stats_panel.copy_header"),
            t("stats_panel.copy_time", time=fmt_hhmmss(elapsed), status=status_str),
            t("stats_panel.copy_volume", value=fmt_bytes(total_bytes)),
            t("stats_panel.copy_speed_header"),
            t("stats_panel.copy_throughput", value=eff_str),
            t(
                "stats_panel.copy_avg",
                value=fmt_speed(arith) if arith is not None else "—",
            ),
            t(
                "stats_panel.copy_peak_min",
                peak=fmt_speed(peak) if peak is not None else "—",
                min=fmt_speed(minimum) if minimum is not None else "—",
            ),
            t(
                "stats_panel.copy_counts",
                total=total, ok=ok, failed=failed, abandoned=abandoned,
                cancelled=cancelled, running=running, queued=queued,
            ),
            t("stats_panel.copy_rate", value=tasso_str),
            "",
            t("stats_panel.copy_detail_header"),
        ]
        for job in self.model.jobs_iter():
            name = job.file_name if job.file_name else link_caption(job.url)[:40]
            vol_str = fmt_bytes(job.downloaded_bytes) if job.downloaded_bytes else "—"
            dur_str = fmt_mmss(job.duration_s()) if job.started_at else "—"
            if job.average_bps_final is not None:
                spd_str = fmt_speed(job.average_bps_final)
            elif job.status == STATUS_RUNNING and job.speed > 0:
                spd_str = fmt_speed(job.speed)
            else:
                spd_str = "—"
            status_short = _status_label(job.status)
            lines.append(
                f"#{job.file_id + 1}  {name}  {vol_str}  {dur_str}  {spd_str}  {status_short}"
            )

        QApplication.clipboard().setText("\n".join(lines))
        self._copy_btn.setText(t("stats_panel.copied_title"))
        QTimer.singleShot(1500, self._restore_copy_label)

    def _restore_copy_label(self) -> None:
        self._copy_btn.setText(t("stats_panel.copy_button"))

    # ---- i18n -----------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive le etichette statiche e rigenera quelle con dati."""
        self._title_lbl.setText(t("stats_panel.title"))
        self._empty.setText(t("stats_panel.idle"))
        self._restore_copy_label()
        for name, label in self._captions.items():
            label.setText(t(f"stats_panel.metric_{name}"))
        self.refresh()

    def refresh_theme(self) -> None:
        self._gauge.refresh_theme()
        self._segments.refresh_theme()
