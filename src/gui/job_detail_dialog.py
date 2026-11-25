# Dialog non modale di dettaglio per un singolo job: URL completo,
# cronologia IP, log dei tentativi. Si aggiorna in real-time agganciandosi
# al segnale job_updated del JobsModel.
#
# i18n: è un dialogo persistente — resta aperto mentre il
# download prosegue, quindi ha bisogno di `retranslate()` come i pannelli, non
# solo dei testi letti alla costruzione. `MainWindow._on_language_changed` lo
# richiama su tutti i dettagli aperti.
#
# Al cambio lingua il log si ritraduce anche se non sono arrivati eventi.
from __future__ import annotations

import time

from PyQt6.QtCore import Qt

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QApplication,
)

from src.gui.error_render import render_error
from src.gui.format_helpers import fmt_hhmmss
from src.gui.i18n import TR, t, tn
from src.gui.jobs_model import JobsModel, STATUS_ABANDONED
from src.gui.jobs_panel import status_label


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
        self._last_log_entry = None
        self._build_ui()
        self._refresh()
        # Subscribe agli aggiornamenti del modello: refresh solo per il
        # nostro file_id (no overhead per altri job).
        self.model.job_updated.connect(self._on_job_updated)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Riquadro evidenziato per i job abbandonati: l'utente DEVE vedere
        # subito il motivo. Il singolo URL copiabile è comune a tutti gli stati.
        # Nascosto di default; mostrato in _refresh() se status == abbandonato.
        self.abandoned_box = QFrame()
        self.abandoned_box.setFrameShape(QFrame.Shape.StyledPanel)
        self.abandoned_box.setObjectName("failureNotice")
        ab_layout = QVBoxLayout(self.abandoned_box)
        ab_layout.setContentsMargins(8, 6, 8, 6)
        self.abandoned_title = QLabel(t("job_detail.abandoned_title"))
        self.abandoned_title.setObjectName("failureTitle")
        ab_layout.addWidget(self.abandoned_title)
        self.abandoned_info = QLabel()
        self.abandoned_info.setTextFormat(Qt.TextFormat.PlainText)
        self.abandoned_info.setWordWrap(True)
        ab_layout.addWidget(self.abandoned_info)
        self.abandoned_box.setVisible(False)

        # Header: URL + bottone copia.
        head = QHBoxLayout()
        self.url_label = QLabel(t("job_detail.url_label"))
        self.url_label.setObjectName("sectionTitle")
        layout.addWidget(self.url_label)
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("detailUrl")
        self.url_edit.setReadOnly(True)
        self.url_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.url_label.setBuddy(self.url_edit)
        self.url_edit.setAccessibleName(self.url_label.text())
        head.addWidget(self.url_edit, 1)
        self.copy_btn = QPushButton(t("job_detail.copy"))
        self.copy_btn.clicked.connect(self._copy_url)
        head.addWidget(self.copy_btn)
        layout.addLayout(head)

        metrics = QFrame()
        metrics.setObjectName("detailMetrics")
        grid = QGridLayout(metrics)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.metric_labels: dict[str, QLabel] = {}
        self.metric_values: dict[str, QLabel] = {}
        for column, key in enumerate(("status", "progress", "attempts", "errors", "duration")):
            label = QLabel(t(f"job_detail.{key}"))
            label.setObjectName("detailCaption")
            value = QLabel()
            value.setObjectName("detailValue")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setAccessibleDescription(label.text())
            grid.addWidget(label, 0, column)
            grid.addWidget(value, 1, column)
            grid.setColumnStretch(column, 1)
            self.metric_labels[key] = label
            self.metric_values[key] = value
        layout.addWidget(metrics)
        layout.addWidget(self.abandoned_box)
        self.last_error_label = QLabel()
        self.last_error_label.setWordWrap(True)
        self.last_error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.last_error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.last_error_label)

        # Cronologia IP.
        self.ip_history_label = QLabel(t("job_detail.ip_history"))
        self.ip_history_label.setObjectName("sectionTitle")
        layout.addWidget(self.ip_history_label)
        self.empty_ips = QLabel(t("job_detail.no_ips"))
        self.empty_ips.setObjectName("detailCaption")
        layout.addWidget(self.empty_ips)
        self.ip_table = QTableWidget(0, 2)
        self.ip_table.setObjectName("ipHistory")
        self.ip_table.setAccessibleName(self.ip_history_label.text())
        self.ip_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ip_table.setShowGrid(False)
        self.ip_table.setAlternatingRowColors(True)
        self.ip_table.setHorizontalHeaderLabels(
            [t("job_detail.col_timestamp"), t("job_detail.col_ip")]
        )
        self.ip_table.verticalHeader().setVisible(False)
        self.ip_table.verticalHeader().setDefaultSectionSize(28)
        self.ip_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.ip_table.horizontalHeader().setStretchLastSection(True)
        self.ip_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.ip_table)

        # Divider.
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        layout.addWidget(line)

        # Log dettagliato.
        self.log_label = QLabel(t("job_detail.attempts_log"))
        self.log_label.setObjectName("sectionTitle")
        layout.addWidget(self.log_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setAccessibleName(self.log_label.text())
        self.log_view.setPlaceholderText(t("job_detail.no_attempts"))
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
        title = (t("job_detail.named_title", name=job.file_name) if job.file_name
                 else t("job_detail.title", file=self.file_id + 1))
        if self.windowTitle() != title:
            self.setWindowTitle(title)
        # L'errore arriva dal modello come payload (codice + parametri) e si
        # rende adesso: e' cio' che lo rende bilingue senza toccare il modello.
        last_error = render_error(*job.last_error) if job.last_error else ""
        # Riquadro abbandono.
        is_abandoned = job.status == STATUS_ABANDONED
        self.abandoned_box.setVisible(is_abandoned)
        if is_abandoned:
            self.abandoned_info.setText(t("jobs_panel.last_error", error=last_error or t("job_detail.not_available")))
        # URL.
        if self.url_edit.text() != job.url:
            self.url_edit.setText(job.url)
            self.url_edit.setCursorPosition(0)
        # Summary. Lo stato si rende con la stessa mappa del badge
        # (`jobs_panel.status_label`): qui compariva il valore grezzo del
        # modello — "in_corso" — in tutte e due le lingue.
        self.metric_values["status"].setText(status_label(job.status))
        self.metric_values["progress"].setText(f"{job.progress}%")
        self.metric_values["attempts"].setText(str(job.attempts))
        self.metric_values["errors"].setText(str(job.errors_count))
        self.metric_values["duration"].setText(fmt_hhmmss(job.duration_s()))
        self.last_error_label.setText(t("jobs_panel.last_error", error=last_error) if last_error else "")
        self.last_error_label.setVisible(bool(last_error) and not is_abandoned)
        # IP history.
        self.ip_table.setVisible(bool(job.ips_history))
        self.empty_ips.setVisible(not job.ips_history)
        if force or self.ip_table.rowCount() != len(job.ips_history):
            self.ip_table.setRowCount(len(job.ips_history))
            for i, (ts, ip) in enumerate(job.ips_history):
                self.ip_table.setItem(i, 0, QTableWidgetItem(_ts(ts)))
                self.ip_table.setItem(i, 1, QTableWidgetItem(ip))
            visible_rows = min(len(job.ips_history), 4)
            self.ip_table.setMaximumHeight(
                self.ip_table.horizontalHeader().sizeHint().height()
                + visible_rows * self.ip_table.verticalHeader().defaultSectionSize()
                + 2 * self.ip_table.frameWidth()
            )
        # Log: ricostruisco solo se cambia il numero di entries (o se me lo
        # chiedono: vedi il commento sul `force` in testa al modulo).
        last_entry = job.all_attempts_log[-1] if job.all_attempts_log else None
        if force or last_entry is not self._last_log_entry:
            self._last_log_entry = last_entry
            bar = self.log_view.verticalScrollBar()
            previous = bar.value()
            at_end = previous == bar.maximum()
            self.log_view.setPlainText("\n".join(
                f"[{_ts(ts)}] {level:5s} {_render_log(key, params)}"
                for ts, level, key, params in job.all_attempts_log
            ))
            bar.setValue(bar.maximum() if at_end else previous)

    # ---- i18n ---------------------------------------------------------------

    def retranslate(self) -> None:
        """Ritraduce il cromo E ricostruisce le parti che dipendono dal
        modello. Il `force=True` non e' un di piu': senza, il log resterebbe
        nella lingua vecchia perche' il numero di righe non e' cambiato."""
        self.abandoned_title.setText(t("job_detail.abandoned_title"))
        self.url_label.setText(t("job_detail.url_label"))
        self.url_edit.setAccessibleName(self.url_label.text())
        for key, label in self.metric_labels.items():
            label.setText(t(f"job_detail.{key}"))
            self.metric_values[key].setAccessibleDescription(label.text())
        self.copy_btn.setText(t("job_detail.copy"))
        self.ip_history_label.setText(t("job_detail.ip_history"))
        self.ip_table.setAccessibleName(self.ip_history_label.text())
        self.empty_ips.setText(t("job_detail.no_ips"))
        self.ip_table.setHorizontalHeaderLabels(
            [t("job_detail.col_timestamp"), t("job_detail.col_ip")]
        )
        self.log_label.setText(t("job_detail.attempts_log"))
        self.log_view.setAccessibleName(self.log_label.text())
        self.log_view.setPlaceholderText(t("job_detail.no_attempts"))
        self.close_btn.setText(t("job_detail.close"))
        self._refresh(force=True)
