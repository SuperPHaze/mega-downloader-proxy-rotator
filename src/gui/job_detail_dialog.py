# Dialog non modale di dettaglio per un singolo job: URL completo,
# cronologia IP, log dei tentativi. Si aggiorna in real-time agganciandosi
# al segnale job_updated del JobsModel.
from __future__ import annotations

import time

from PyQt6.QtCore import Qt
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

from src.gui.jobs_model import JobsModel, STATUS_ABANDONED


def _ts(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


class JobDetailDialog(QDialog):
    def __init__(self, model: JobsModel, file_id: int, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self.file_id = file_id
        self.setWindowTitle(f"Dettaglio job #{file_id + 1}")
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
        self.abandoned_title = QLabel("Link abbandonato")
        self.abandoned_title.setStyleSheet("color: #991b1b; font-weight: bold;")
        ab_layout.addWidget(self.abandoned_title)
        ab_url_row = QHBoxLayout()
        self.abandoned_url = QTextEdit()
        self.abandoned_url.setReadOnly(True)
        self.abandoned_url.setMaximumHeight(50)
        ab_url_row.addWidget(self.abandoned_url, 1)
        self.abandoned_copy_btn = QPushButton("Copia")
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
        head.addWidget(QLabel("URL:"))
        self.url_edit = QTextEdit()
        self.url_edit.setReadOnly(True)
        self.url_edit.setMaximumHeight(50)
        head.addWidget(self.url_edit, 1)
        self.copy_btn = QPushButton("Copia")
        self.copy_btn.clicked.connect(self._copy_url)
        head.addWidget(self.copy_btn)
        layout.addLayout(head)

        # KPI summary line.
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("color: #4b5563; padding: 4px 0;")
        layout.addWidget(self.summary_label)

        # Cronologia IP.
        layout.addWidget(QLabel("Cronologia IP usati:"))
        self.ip_table = QTableWidget(0, 2)
        self.ip_table.setHorizontalHeaderLabels(["Timestamp", "IP"])
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
        layout.addWidget(QLabel("Log dei tentativi:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        layout.addWidget(self.log_view, 1)

        # Close button in fondo.
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy_url(self) -> None:
        job = self.model.get_job(self.file_id)
        if job:
            QApplication.clipboard().setText(job.url)

    def _on_job_updated(self, file_id: int) -> None:
        if file_id == self.file_id:
            self._refresh()

    def _refresh(self) -> None:
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        # Riquadro abbandono.
        is_abandoned = job.status == STATUS_ABANDONED
        self.abandoned_box.setVisible(is_abandoned)
        if is_abandoned:
            if self.abandoned_url.toPlainText() != job.url:
                self.abandoned_url.setPlainText(job.url)
            self.abandoned_info.setText(
                f"Tentativi falliti: {job.attempts}  •  "
                f"Ultimo errore: {job.last_error or 'n/d'}"
            )
        # URL.
        if self.url_edit.toPlainText() != job.url:
            self.url_edit.setPlainText(job.url)
        # Summary.
        dur = int(job.duration_s())
        self.summary_label.setText(
            f"Stato: <b>{job.status}</b>  •  Avanzamento: {job.progress}%  •  "
            f"Tentativi: {job.attempts}  •  Errori: {job.errors_count}  •  "
            f"Durata: {dur // 60:02d}:{dur % 60:02d}"
            + (f"  •  Ultimo errore: {job.last_error}" if job.last_error else "")
        )
        # IP history.
        if self.ip_table.rowCount() != len(job.ips_history):
            self.ip_table.setRowCount(len(job.ips_history))
            for i, (ts, ip) in enumerate(job.ips_history):
                self.ip_table.setItem(i, 0, QTableWidgetItem(_ts(ts)))
                self.ip_table.setItem(i, 1, QTableWidgetItem(ip))
        # Log: ricostruisco solo se cambia il numero di entries.
        n_log = len(job.all_attempts_log)
        if n_log != self.log_view.blockCount() - 1:
            self.log_view.clear()
            for ts, level, msg in job.all_attempts_log:
                self.log_view.appendPlainText(f"[{_ts(ts)}] {level:5s} {msg}")
