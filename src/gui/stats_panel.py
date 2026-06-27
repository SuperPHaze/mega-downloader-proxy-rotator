# Cruscotto "Statistiche" di sessione: volume totale, throughput effettivo,
# media aritmetica per-download, picco/minima, tempo attivo con auto-freeze,
# dettaglio per-job, pulsante "Copia riepilogo". Header sempre visibile con
# riassunto 1 Hz; body collassabile. Aggiornamento event-driven + tick 1 Hz.
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.gui import style as _style
from src.gui.format_helpers import (
    build_header_summary,
    fmt_bytes,
    fmt_hhmmss,
    fmt_mmss,
    fmt_speed,
)
from src.gui.jobs_model import (
    JobsModel,
    STATUS_RUNNING,
)
from src.gui.preferences import load_stats_panel_expanded, save_stats_panel_expanded
from src.gui.session_clock import SessionClock
from src.gui.session_speed import SessionSpeedStats, is_plausible_bps

_TERMINAL_STATUS_LABEL = {
    "completato": "ok",
    "fallito": "fallito",
    "annullato": "annullato",
    "abbandonato": "abbandonato",
    "in_corso": "in corso",
    "in_coda": "in coda",
}


def _short_url(url: str, max_len: int = 40) -> str:
    try:
        part = url.split("/")[-1]
        if "#" in part:
            handle = part.split("#")[0]
            s = f"mega://{handle}" if handle else url
        else:
            s = part
        return s[:max_len] if len(s) > max_len else s
    except Exception:
        return url[:max_len]


class StatsPanel(QWidget):
    def __init__(self, model: JobsModel) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.model = model
        self._clock = SessionClock()
        self._speed_stats = SessionSpeedStats()

        self._build_ui()

        # Imposta stato iniziale da preferenze prima di connettere il segnale toggle
        expanded = load_stats_panel_expanded()
        self._body.setVisible(expanded)
        self._update_toggle_icon(expanded)
        self._toggle_btn.setChecked(not expanded)

        # Connetti dopo l'impostazione iniziale per evitare salvataggio spurio
        self._toggle_btn.toggled.connect(self._on_toggle)

        model.aggregates_changed.connect(self.refresh)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    # ---- costruzione UI --------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 0)
        outer.setSpacing(0)

        self._box = QGroupBox()
        self._box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        outer.addWidget(self._box)

        vl = QVBoxLayout(self._box)
        vl.setSpacing(3)
        vl.setContentsMargins(8, 6, 8, 6)

        # Header sempre visibile: toggle ▾/▸ + "Statistiche" + riassunto + Copia
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header_row.setContentsMargins(0, 0, 0, 0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setFixedSize(20, 20)
        header_row.addWidget(self._toggle_btn)

        title_lbl = QLabel("Statistiche")
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        header_row.addWidget(title_lbl)

        self._summary_lbl = QLabel("—")
        self._summary_lbl.setFont(QFont("Segoe UI", 9))
        header_row.addWidget(self._summary_lbl, 1)

        self._copy_btn = QPushButton("Copia riepilogo")
        self._copy_btn.setFixedHeight(24)
        self._copy_btn.clicked.connect(self._on_copy)
        header_row.addWidget(self._copy_btn)

        vl.addLayout(header_row)

        # Body collassabile: tutto il contenuto dettagliato
        self._body = QWidget()
        body_vl = QVBoxLayout(self._body)
        body_vl.setSpacing(3)
        body_vl.setContentsMargins(0, 4, 0, 0)

        self._session_lbl = QLabel("Sessione: —")
        self._session_lbl.setFont(QFont("Segoe UI", 10))
        body_vl.addWidget(self._session_lbl)

        self._volume_lbl = QLabel("Volume scaricato:  —")
        body_vl.addWidget(self._volume_lbl)

        speed_hdr = QLabel("Velocità di sessione")
        speed_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        body_vl.addWidget(speed_hdr)

        speed_cols = QHBoxLayout()
        speed_cols.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(1)
        self._throughput_lbl = QLabel("  Throughput effettivo : —")
        self._throughput_lbl.setFont(QFont("Consolas", 9))
        left.addWidget(self._throughput_lbl)
        self._avg_dl_lbl = QLabel("  Media per-download   : —")
        self._avg_dl_lbl.setFont(QFont("Consolas", 9))
        left.addWidget(self._avg_dl_lbl)
        speed_cols.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(1)
        self._peak_lbl = QLabel("  Picco  : —")
        self._peak_lbl.setFont(QFont("Consolas", 9))
        right.addWidget(self._peak_lbl)
        self._min_lbl = QLabel("  Minima : —")
        self._min_lbl.setFont(QFont("Consolas", 9))
        right.addWidget(self._min_lbl)
        speed_cols.addLayout(right, 1)

        body_vl.addLayout(speed_cols)

        self._counts_lbl = QLabel("Job: —")
        body_vl.addWidget(self._counts_lbl)
        self._rate_lbl = QLabel("Tasso completati: —")
        body_vl.addWidget(self._rate_lbl)

        detail_hdr = QLabel("Dettaglio per-download:")
        detail_hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        body_vl.addWidget(detail_hdr)

        self._detail_text = QPlainTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setFont(QFont("Consolas", 9))
        self._detail_text.setMaximumHeight(120)
        self._detail_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        body_vl.addWidget(self._detail_text)

        vl.addWidget(self._body)

    # ---- toggle collassa/espandi -----------------------------------------

    def _on_toggle(self, checked: bool) -> None:
        expanded = not checked
        self._body.setVisible(expanded)
        self._update_toggle_icon(expanded)
        save_stats_panel_expanded(expanded)

    def _update_toggle_icon(self, expanded: bool) -> None:
        self._toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    # ---- ciclo di vita sessione ------------------------------------------

    def start_clock(self) -> None:
        """Resetta clock e statistiche e avvia la sessione. Chiamato da MainWindow su 'Avvia'."""
        self._clock.reset()
        self._clock.start(time.time())
        self._speed_stats.reset()
        self.refresh()

    # ---- tick 1 Hz -------------------------------------------------------

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
        p = _style.CURRENT_PALETTE
        elapsed = self._clock.elapsed(now)
        all_term = bool(agg.get("all_terminated", False))
        total_bytes = int(agg.get("total_downloaded_bytes", 0))
        total = int(agg.get("total", 0))
        ok = int(agg.get("completed", 0))
        failed = int(agg.get("failed", 0))
        abandoned = int(agg.get("abandoned", 0))
        cancelled = int(agg.get("cancelled", 0))
        fallen = failed + cancelled + abandoned

        eff_bps = total_bytes / elapsed if elapsed > 0 and total_bytes > 0 else 0.0

        # Header summary: sempre aggiornato anche con body nascosto
        self._summary_lbl.setText(build_header_summary(
            elapsed_s=elapsed,
            total_bytes=total_bytes,
            throughput_eff_bps=eff_bps,
            totals_dict={"total": total, "ok": ok, "fallen": fallen},
            all_terminated=all_term,
        ))

        if not self._body.isVisible():
            return

        # Body labels
        status_str = "completata" if all_term else "in corso"
        self._session_lbl.setText(f"Sessione: {fmt_hhmmss(elapsed)}  ({status_str})")
        self._session_lbl.setStyleSheet(f"color: {p['text']};")

        self._volume_lbl.setText(f"Volume scaricato:  {fmt_bytes(total_bytes)}")
        self._volume_lbl.setStyleSheet(f"color: {p['text']};")

        eff_str = fmt_speed(eff_bps) if eff_bps > 0 else "—"
        self._throughput_lbl.setText(f"  Throughput effettivo : {eff_str}")
        self._throughput_lbl.setStyleSheet(f"color: {p['text_dim']};")

        arith = agg.get("arithmetic_avg_bps")
        self._avg_dl_lbl.setText(
            f"  Media per-download   : {fmt_speed(arith) if arith is not None else '—'}"
        )
        self._avg_dl_lbl.setStyleSheet(f"color: {p['text_dim']};")

        peak = self._speed_stats.peak
        minimum = self._speed_stats.minimum
        self._peak_lbl.setText(
            f"  Picco  : {fmt_speed(peak) if peak is not None else '—'}"
        )
        self._peak_lbl.setStyleSheet(f"color: {p['text_dim']};")
        self._min_lbl.setText(
            f"  Minima : {fmt_speed(minimum) if minimum is not None else '—'}"
        )
        self._min_lbl.setStyleSheet(f"color: {p['text_dim']};")

        running = int(agg.get("running", 0))
        queued = int(agg.get("queued", 0))
        self._counts_lbl.setText(
            f"Job: {total} totali · {ok} ok · {failed} fall. · "
            f"{abandoned} abb. · {cancelled} ann. · {running} in corso · {queued} coda"
        )
        self._counts_lbl.setStyleSheet(f"color: {p['text']};")

        tasso_str = f"{round(ok / total * 100)}%" if total > 0 else "—"
        self._rate_lbl.setText(f"Tasso completati: {tasso_str}")
        self._rate_lbl.setStyleSheet(f"color: {p['text_dim']};")

        lines = []
        for job in self.model.jobs_iter():
            name = job.file_name if job.file_name else _short_url(job.url, 40)
            vol_str = fmt_bytes(job.downloaded_bytes) if job.downloaded_bytes else "—"
            dur_str = fmt_mmss(job.duration_s()) if job.started_at else "—"
            if job.average_bps_final is not None:
                spd_str = fmt_speed(job.average_bps_final)
            elif job.status == STATUS_RUNNING and job.speed > 0:
                spd_str = fmt_speed(job.speed)
            else:
                spd_str = "—"
            status_short = _TERMINAL_STATUS_LABEL.get(job.status, job.status)
            lines.append(
                f"#{job.file_id + 1:<3} {name:<40}  {vol_str:>9}  {dur_str}"
                f"  {spd_str:>12}  {status_short}"
            )
        self._detail_text.setPlainText("\n".join(lines))

    # ---- copia riepilogo -------------------------------------------------

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

        lines = [
            "=== Sessione MDPR ===",
            f"Tempo:    {fmt_hhmmss(elapsed)}  ({'completata' if all_term else 'in corso'})",
            f"Volume:   {fmt_bytes(total_bytes)}",
            "Velocita':",
            f"  - Throughput effettivo: {eff_str}",
            f"  - Media per-download:   {fmt_speed(arith) if arith is not None else '—'}",
            f"  - Picco / Minima:       "
            f"{fmt_speed(peak) if peak is not None else '—'} / "
            f"{fmt_speed(minimum) if minimum is not None else '—'}",
            f"Job: {total} totali  ok={ok}  fall={failed}  abb={abandoned}"
            f"  ann={cancelled}  in_corso={running}  in_coda={queued}",
            f"Tasso completati: {tasso_str}",
            "",
            "Dettaglio:",
        ]
        for job in self.model.jobs_iter():
            name = job.file_name if job.file_name else _short_url(job.url, 40)
            vol_str = fmt_bytes(job.downloaded_bytes) if job.downloaded_bytes else "—"
            dur_str = fmt_mmss(job.duration_s()) if job.started_at else "—"
            if job.average_bps_final is not None:
                spd_str = fmt_speed(job.average_bps_final)
            elif job.status == STATUS_RUNNING and job.speed > 0:
                spd_str = fmt_speed(job.speed)
            else:
                spd_str = "—"
            status_short = _TERMINAL_STATUS_LABEL.get(job.status, job.status)
            lines.append(
                f"#{job.file_id + 1}  {name}  {vol_str}  {dur_str}  {spd_str}  {status_short}"
            )

        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Copiato", "Riepilogo copiato negli appunti.")

    # ---- tema -----------------------------------------------------------

    def refresh_theme(self) -> None:
        self.refresh()
