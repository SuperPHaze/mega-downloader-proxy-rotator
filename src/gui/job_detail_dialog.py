# Dialog non modale di dettaglio per un singolo job: URL completo,
# cronologia IP, log dei tentativi. Si aggiorna in real-time agganciandosi
# al segnale job_updated del JobsModel.
#
# i18n: e' l'UNICO dialogo persistente del progetto — resta aperto mentre il
# download prosegue, quindi ha bisogno di `retranslate()` come i pannelli, non
# solo dei testi letti alla costruzione. `MainWindow._on_language_changed` lo
# richiama su tutti i dettagli aperti.
#
# Attenzione al `force`: `_refresh()` ricostruisce log e tabella IP solo se il
# NUMERO di voci e' cambiato (e' cio' che evita di ridisegnare mille righe a
# ogni tick). Al cambio lingua il numero non cambia ma il testo si': senza
# `force=True` il log resterebbe nella lingua vecchia finche' non arriva un
# nuovo tentativo. E' lo stesso difetto gia' corretto in `StatsPanel`.
from __future__ import annotations

import time

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QApplication,
)

from src.gui.error_render import render_error
from src.gui.i18n import TR, t, tn
from src.gui.jobs_model import JobsModel, STATUS_ABANDONED


def _ts(moment: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(moment))


def _render_log(key: str, params: dict) -> str:
    """Una riga di cronologia: chiave `job_log.*` + parametri dal modello.

    Il parametro `error`, quando c'e', e' il PAYLOAD dell'errore (codice +
    parametri): va reso prima, altrimenti a video finirebbe un dict.

    Si passa da `tn()` quando la VOCE ha forme plurali, non quando i parametri
    contengono una `n`: e' il dizionario a sapere se il testo cambia col
    conteggio, e un domani un parametro chiamato `n` in una voce qualsiasi non
    deve dirottare la resa.
    """
    values = dict(params)
    payload = values.get("error")
    if isinstance(payload, dict) and "code" in payload:
        values["error"] = render_error(payload["code"], payload.get("params"))
    if isinstance(TR.entry(key), dict):
        return tn(key, int(values.pop("n", 0)), **values)
    return t(key, **values)


class JobDetailDialog(QDialog):
    def __init__(self, model: JobsModel, file_id: int, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self.file_id = file_id
        self.setWindowTitle(t("job_detail.title", file=file_id + 1))
        self.setModal(False)
        self.resize(720, 540)
        self._build_ui()
        self._refresh()
        # Subscribe agli aggiornamenti del modello: refresh solo per il
        # nostro file_id (no overhead per altri job).
        self.model.job_updated.connect(self._on_job_updated)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Riquadro evidenziato per i job abbandonati: l'utente DEVE vedere
        # subito URL completo + motivo per poter riprovare a mano.
        # Nascosto di default; mostrato in _refresh() se status == abbandonato.
        self.abandoned_box = QFrame()
        self.abandoned_box.setFrameShape(QFrame.Shape.StyledPanel)
        self.abandoned_box.setStyleSheet(
            "QFrame { background-color: #fee2e2; border: 1px solid #dc2626;"
            " border-radius: 6px; padding: 6px; }"
            "QLabel { color: #7f1d1d; }"
        )
        ab_layout = QVBoxLayout(self.abandoned_box)
        ab_layout.setContentsMargins(8, 6, 8, 6)
        self.abandoned_title = QLabel(t("job_detail.abandoned_title"))
        self.abandoned_title.setStyleSheet("color: #991b1b; font-weight: bold;")
        ab_layout.addWidget(self.abandoned_title)
        ab_url_row = QHBoxLayout()
        self.abandoned_url = QTextEdit()
        self.abandoned_url.setReadOnly(True)
        self.abandoned_url.setMaximumHeight(50)
        ab_url_row.addWidget(self.abandoned_url, 1)
        self.abandoned_copy_btn = QPushButton(t("job_detail.copy"))
        self.abandoned_copy_btn.clicked.connect(self._copy_url)
        ab_url_row.addWidget(self.abandoned_copy_btn)
        ab_layout.addLayout(ab_url_row)
        self.abandoned_info = QLabel()
        self.abandoned_info.setWordWrap(True)
        ab_layout.addWidget(self.abandoned_info)
        self.abandoned_box.setVisible(False)
        layout.addWidget(self.abandoned_box)

        # Header: URL + bottone copia.
        head = QHBoxLayout()
        self.url_label = QLabel(t("job_detail.url_label"))
        head.addWidget(self.url_label)
        self.url_edit = QTextEdit()
        self.url_edit.setReadOnly(True)
        self.url_edit.setMaximumHeight(50)
        head.addWidget(self.url_edit, 1)
        self.copy_btn = QPushButton(t("job_detail.copy"))
        self.copy_btn.clicked.connect(self._copy_url)
        head.addWidget(self.copy_btn)
        layout.addLayout(head)

        # KPI summary line.
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("color: #4b5563; padding: 4px 0;")
        layout.addWidget(self.summary_label)

        # Cronologia IP.
        self.ip_history_label = QLabel(t("job_detail.ip_history"))
        layout.addWidget(self.ip_history_label)
        self.ip_table = QTableWidget(0, 2)
        self.ip_table.setHorizontalHeaderLabels(
            [t("job_detail.col_timestamp"), t("job_detail.col_ip")]
        )
        self.ip_table.verticalHeader().setVisible(False)
        self.ip_table.horizontalHeader().setStretchLastSection(True)
        self.ip_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.ip_table.setMaximumHeight(180)
        layout.addWidget(self.ip_table)

        # Divider.
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #d7dbe0;")
        layout.addWidget(line)

        # Log dettagliato.
        self.log_label = QLabel(t("job_detail.attempts_log"))
        layout.addWidget(self.log_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        layout.addWidget(self.log_view, 1)

        # Close button in fondo.
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.close_btn = QPushButton(t("job_detail.close"))
        self.close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _copy_url(self) -> None:
        job = self.model.get_job(self.file_id)
        if job:
            QApplication.clipboard().setText(job.url)

    def _on_job_updated(self, file_id: int) -> None:
        if file_id == self.file_id:
            self._refresh()

    def _refresh(self, force: bool = False) -> None:
        """Ridisegna dal modello. `force=True` ricostruisce ANCHE le parti che
        di norma si saltano quando il numero di voci non cambia (log e tabella
        IP): serve al cambio lingua, dove cambia il testo e non il conteggio."""
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        # L'errore arriva dal modello come payload (codice + parametri) e si
        # rende adesso: e' cio' che lo rende bilingue senza toccare il modello.
        last_error = render_error(*job.last_error) if job.last_error else ""
        # Riquadro abbandono.
        is_abandoned = job.status == STATUS_ABANDONED
        self.abandoned_box.setVisible(is_abandoned)
        if is_abandoned:
            if self.abandoned_url.toPlainText() != job.url:
                self.abandoned_url.setPlainText(job.url)
            self.abandoned_info.setText(
                t(
                    "job_detail.abandoned_info",
                    attempts=job.attempts,
                    error=last_error or t("job_detail.not_available"),
                )
            )
        # URL.
        if self.url_edit.toPlainText() != job.url:
            self.url_edit.setPlainText(job.url)
        # Summary. Lo STATO resta il valore grezzo del modello ("in_corso"):
        # tradurlo qui cambierebbe anche il testo italiano di oggi, quindi va
        # con la passata sui badge di stato, rimandata a F3.
        dur = int(job.duration_s())
        self.summary_label.setText(
            t(
                "job_detail.summary",
                status=job.status,
                progress=job.progress,
                attempts=job.attempts,
                errors=job.errors_count,
                duration=f"{dur // 60:02d}:{dur % 60:02d}",
            )
            + (
                t("job_detail.summary_last_error", error=last_error)
                if job.last_error else ""
            )
        )
        # IP history.
        if force or self.ip_table.rowCount() != len(job.ips_history):
            self.ip_table.setRowCount(len(job.ips_history))
            for i, (ts, ip) in enumerate(job.ips_history):
                self.ip_table.setItem(i, 0, QTableWidgetItem(_ts(ts)))
                self.ip_table.setItem(i, 1, QTableWidgetItem(ip))
        # Log: ricostruisco solo se cambia il numero di entries (o se me lo
        # chiedono: vedi il commento sul `force` in testa al modulo).
        n_log = len(job.all_attempts_log)
        if force or n_log != self.log_view.blockCount() - 1:
            self.log_view.clear()
            for ts, level, key, params in job.all_attempts_log:
                self.log_view.appendPlainText(
                    f"[{_ts(ts)}] {level:5s} {_render_log(key, params)}"
                )

    # ---- i18n ---------------------------------------------------------------

    def retranslate(self) -> None:
        """Ritraduce il cromo E ricostruisce le parti che dipendono dal
        modello. Il `force=True` non e' un di piu': senza, il log resterebbe
        nella lingua vecchia perche' il numero di righe non e' cambiato."""
        self.setWindowTitle(t("job_detail.title", file=self.file_id + 1))
        self.abandoned_title.setText(t("job_detail.abandoned_title"))
        self.abandoned_copy_btn.setText(t("job_detail.copy"))
        self.url_label.setText(t("job_detail.url_label"))
        self.copy_btn.setText(t("job_detail.copy"))
        self.ip_history_label.setText(t("job_detail.ip_history"))
        self.ip_table.setHorizontalHeaderLabels(
            [t("job_detail.col_timestamp"), t("job_detail.col_ip")]
        )
        self.log_label.setText(t("job_detail.attempts_log"))
        self.close_btn.setText(t("job_detail.close"))
        self._refresh(force=True)
