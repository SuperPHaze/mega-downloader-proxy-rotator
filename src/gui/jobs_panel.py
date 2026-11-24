# Lista job a righe-card con barra di avanzamento integrata ed espansione
# inline. Sostituisce la precedente QTableView.
#
# Architettura: QScrollArea + un _JobCard per riga, creato e aggiornato da
# JobsPanel. Il JobsModel resta la fonte di verita'; le card si aggiornano
# tramite model.job_updated (segnale con file_id).
#
# i18n: superficie PERSISTENTE con cascata. retranslate() ricasca su _EmptyState
# e su OGNI _JobCard, come gia' fa refresh_theme(). Dal modello arrivano DATI, non
# frasi: l'ultimo errore e' un payload (codice + parametri) che la card rende con
# error_render, quindi il semplice _refresh() basta anche al cambio lingua.
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QSize,
    QUrl,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QMenu,
    QMessageBox,
    QToolButton,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.gui import style as _style
from src.gui.i18n import TR, t
from src.gui.error_render import ABANDON_ALIASES, render_error, render_queue_cause
from src.gui.format_helpers import fmt_bytes as _fmt_bytes, fmt_speed as _fmt_speed_stat, link_caption
from src.gui.jobs_model import (
    JobsModel,
    STATUS_ABANDONED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
)

FILTER_ALL = "all"
FILTER_IN_PROGRESS = "in_progress"
FILTER_COMPLETED = "completed"
FILTER_NOT_COMPLETED = "not_completed"

# Lo stato del modello -> chiave i18n. La MAPPA vive qui perche' e' qui che il
# badge la usa, ma non e' privata del pannello: `status_label()` la espone a chi
# deve rendere lo stesso stato altrove (il dialogo di dettaglio). Una seconda
# mappa vorrebbe dire due elenchi da tenere allineati a mano.
_STATUS_LABEL_KEY = {
    STATUS_QUEUED: "jobs_panel.status_queued",
    STATUS_RUNNING: "jobs_panel.status_running",
    STATUS_COMPLETED: "jobs_panel.status_completed",
    STATUS_FAILED: "jobs_panel.status_failed",
    STATUS_CANCELLED: "jobs_panel.status_cancelled",
    STATUS_ABANDONED: "jobs_panel.status_abandoned",
}


_FILTER_CATEGORIES: dict[str, set[str]] = {
    FILTER_ALL: set(_STATUS_LABEL_KEY),
    FILTER_IN_PROGRESS: {STATUS_QUEUED, STATUS_RUNNING},
    FILTER_COMPLETED: {STATUS_COMPLETED},
    FILTER_NOT_COMPLETED: {STATUS_FAILED, STATUS_CANCELLED, STATUS_ABANDONED},
}

def status_label(status: str) -> str:
    """Etichetta tradotta di uno stato del modello ("in_corso" -> "In corso").

    Lo stato grezzo resta il valore del modello: qui si traduce solo cio' che
    si mostra. Uno stato non mappato ricade sul valore grezzo, che e' comunque
    diagnosticabile.
    """
    key = _STATUS_LABEL_KEY.get(status)
    return t(key) if key else status


_PROGRESS_COLOR_KEY = {
    STATUS_RUNNING: "accent_active",
    STATUS_COMPLETED: "completed_track",
    STATUS_FAILED: "accent_fail",
    STATUS_ABANDONED: "accent_fail",
    STATUS_CANCELLED: "accent_warn",
    STATUS_QUEUED: "text_dim",
}


class _ElidedLabel(QLabel):
    """QLabel che tronca il testo con elisione automatica al resize.

    Tooltip impostato al testo completo per accessibilità.
    SizePolicy Ignored permette di ridurre il label a zero senza imporre
    un minimo basato sul contenuto: fondamentale per evitare scroll orizzontale.
    """

    def __init__(
        self,
        elide_mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        parent: "QWidget | None" = None,
    ) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802
        if self._full_text == text:
            return
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._apply_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        fm = self.fontMetrics()
        one_line = " ".join(self._full_text.splitlines())
        elided = fm.elidedText(one_line, self._elide_mode, max(1, self.contentsRect().width()))
        super().setText(elided)


def _fmt_speed(bps: float) -> str:
    if bps < 1:
        return ""
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


class _JobCard(QFrame):
    cancel_requested = pyqtSignal(int, bool)  # file_id, delete_folder
    delete_requested = pyqtSignal(int)        # file_id
    open_folder_requested = pyqtSignal(int)   # file_id
    restart_requested = pyqtSignal(int)       # file_id
    double_clicked = pyqtSignal(int)          # file_id

    def __init__(self, model: JobsModel, file_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.file_id = file_id
        self._expanded = False
        self._error_key = None

        self._build_ui()
        self._refresh()
        model.job_updated.connect(self._on_model_updated)

    def _build_ui(self) -> None:
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 7, 12, 11)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        self._expand_btn = QToolButton()
        self._expand_btn.setObjectName("rowAction")
        self._expand_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._expand_btn.setCheckable(True)
        self._expand_btn.setIconSize(QSize(12, 12))
        self._expand_btn.toggled.connect(self._set_expanded)
        grid.addWidget(self._expand_btn, 0, 0)

        self._name_lbl = _ElidedLabel(Qt.TextElideMode.ElideMiddle)
        self._name_lbl.setObjectName("fileName")
        grid.addWidget(self._name_lbl, 0, 1)
        self._action_btn = QToolButton()
        self._action_btn.setObjectName("rowMenu")
        self._action_btn.setText("…")
        self._action_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._action_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._action_btn)
        self._details_action = menu.addAction("")
        self._details_action.triggered.connect(lambda: self.double_clicked.emit(self.file_id))
        self._file_action = menu.addAction("")
        self._file_action.triggered.connect(self._on_action)
        self._action_btn.setMenu(menu)
        grid.addWidget(self._action_btn, 0, 2)

        meta = QHBoxLayout()
        meta.setSpacing(10)
        self._badge = QLabel()
        self._badge.setObjectName("statusBadge")
        meta.addWidget(self._badge)
        self._speed_lbl = QLabel()
        self._speed_lbl.setObjectName("transferRate")
        meta.addWidget(self._speed_lbl)
        meta.addStretch()
        self._percent_lbl = QLabel()
        self._percent_lbl.setObjectName("transferPercent")
        meta.addWidget(self._percent_lbl)
        grid.addLayout(meta, 1, 1, 1, 2)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._progress.setObjectName("transferProgress")
        self._progress.setFixedHeight(3)
        grid.addWidget(self._progress, 2, 1, 1, 2)

        self._terminal_stats_lbl = QLabel()
        self._terminal_stats_lbl.hide()
        grid.addWidget(self._terminal_stats_lbl, 3, 1, 1, 2)

        self._detail = QFrame()
        self._detail.setObjectName("jobDetails")
        details = QVBoxLayout(self._detail)
        details.setContentsMargins(0, 8, 0, 0)
        details.setSpacing(5)
        facts = QHBoxLayout()
        self._attempts_lbl = QLabel()
        facts.addWidget(self._attempts_lbl)
        facts.addStretch()
        self._ip_lbl = QLabel()
        facts.addWidget(self._ip_lbl)
        self._details_btn = QPushButton()
        self._details_btn.setObjectName("textAction")
        self._details_btn.clicked.connect(lambda: self.double_clicked.emit(self.file_id))
        facts.addWidget(self._details_btn)
        details.addLayout(facts)
        self._error_lbl = _ElidedLabel()
        details.addWidget(self._error_lbl)

        actions = QHBoxLayout()
        self._path_lbl = _ElidedLabel(Qt.TextElideMode.ElideMiddle)
        self._path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        actions.addWidget(self._path_lbl, 1)
        self._open_btn = QPushButton()
        self._open_btn.setObjectName("textAction")
        self._open_btn.clicked.connect(self._open_folder)
        actions.addWidget(self._open_btn)
        details.addLayout(actions)
        for label in (self._terminal_stats_lbl, self._ip_lbl, self._attempts_lbl, self._error_lbl, self._path_lbl):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setObjectName("secondaryText")
        self._detail.hide()
        grid.addWidget(self._detail, 4, 1, 1, 2)

    # ---- segnali/slot interni --------------------------------------------

    def _on_model_updated(self, file_id: int) -> None:
        if file_id == self.file_id:
            self._refresh()

    def _on_action(self) -> None:
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            message = QMessageBox(self)
            message.setWindowTitle(t("jobs_panel.action_cancel"))
            message.setText(t("jobs_panel.confirm_cancel", name=job.file_name or link_caption(job.url)))
            message.setTextFormat(Qt.TextFormat.PlainText)
            discard = QCheckBox(t("jobs_panel.discard_partial"))
            message.setCheckBox(discard)
            message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            message.setDefaultButton(QMessageBox.StandardButton.No)
            if message.exec() == QMessageBox.StandardButton.Yes:
                self.cancel_requested.emit(self.file_id, discard.isChecked())
        elif job.status == STATUS_COMPLETED:
            self.open_folder_requested.emit(self.file_id)
        elif job.status in (STATUS_FAILED, STATUS_ABANDONED, STATUS_CANCELLED):
            self.restart_requested.emit(self.file_id)
        else:
            QApplication.clipboard().setText(job.url)

    def _open_folder(self) -> None:
        job = self.model.get_job(self.file_id)
        if job and job.output_path:
            p = Path(job.output_path)
            folder = p.parent if p.is_file() else p
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.file_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._expand_btn.toggle()
        super().mousePressEvent(event)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._expand_btn.setIcon(_style.disclosure_icon(expanded, _style.CURRENT_PALETTE["text_dim"]))
        self._detail.setVisible(expanded)

    # ---- refresh visuale --------------------------------------------------

    def _refresh(self) -> None:
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        p = _style.CURRENT_PALETTE

        title = job.file_name or link_caption(job.url)
        self._name_lbl.setText(title)
        speed = _fmt_speed(job.speed) if job.status == STATUS_RUNNING else ""
        self._speed_lbl.setText(speed)
        self._speed_lbl.setVisible(bool(speed))
        state = status_label(job.status)
        self._badge.setText(state)
        self._expand_btn.setAccessibleName(t("jobs_panel.details_for", name=title))
        self._expand_btn.setToolTip(self._expand_btn.accessibleName())
        self._details_btn.setText(t("jobs_panel.details"))
        self._details_action.setText(t("jobs_panel.details"))
        self._open_btn.setText(t("jobs_panel.open_folder_button"))

        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            action = "jobs_panel.action_cancel"
        elif job.status == STATUS_COMPLETED:
            action = "jobs_panel.action_open_folder"
        elif job.status in (STATUS_FAILED, STATUS_ABANDONED, STATUS_CANCELLED):
            action = "jobs_panel.action_restart"
        else:
            action = "jobs_panel.action_copy_url"
        self._file_action.setText(t(action))
        self._action_btn.setAccessibleName(t("jobs_panel.actions_for", name=title))
        self._action_btn.setToolTip(self._action_btn.accessibleName())
        pct = 100 if job.status == STATUS_COMPLETED else job.progress
        self._progress.setValue(pct)
        self._progress.setAccessibleName(f"{title} · {state}")
        self._percent_lbl.setText(f"{pct}%")

        # I campioni di velocità non richiedono di riapplicare lo stile di Qt.
        appearance = (job.status, p["panel"])
        if getattr(self, "_appearance", None) != appearance:
            self._appearance = appearance
            self._expand_btn.setIcon(_style.disclosure_icon(self._expanded, p["text_dim"]))
            color = p[_PROGRESS_COLOR_KEY.get(job.status, "text_dim")]
            self._progress.setStyleSheet(
                f"QProgressBar#transferProgress {{ background: {p['panel_alt']}; border: none; border-radius: 1px;"
                "height: 3px; min-height: 3px; max-height: 3px; padding: 0; }"
                f"QProgressBar#transferProgress::chunk {{ background: {color}; border-radius: 1px; }}"
            )

        # Riga statistiche finali (job terminato con byte scaricati).
        _TERMINAL = {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED, STATUS_ABANDONED}
        if job.status in _TERMINAL and job.downloaded_bytes > 0:
            vol_str = _fmt_bytes(job.downloaded_bytes)
            dur = job.duration_s()
            dur_str = f"{int(dur) // 60:02d}:{int(dur) % 60:02d}"
            if job.average_bps_final is not None:
                spd_str = t(
                    "jobs_panel.avg_speed",
                    value=_fmt_speed_stat(job.average_bps_final),
                )
            else:
                spd_str = "—"
            self._terminal_stats_lbl.setText(
                t(
                    "jobs_panel.terminal_stats",
                    speed=spd_str, volume=vol_str, duration=dur_str,
                )
            )
            self._terminal_stats_lbl.setVisible(True)
        else:
            self._terminal_stats_lbl.setVisible(False)

        self._ip_lbl.setText(t("jobs_panel.current_ip", ip=job.current_ip or ""))
        self._ip_lbl.setVisible(bool(job.current_ip))
        counts = t("jobs_panel.attempts", n=job.attempts)
        if job.errors_count:
            counts += t("jobs_panel.errors_suffix", n=job.errors_count)
        self._attempts_lbl.setText(counts)
        self._refresh_error(job.last_error)
        self._path_lbl.setText(job.output_path or "")
        self._path_lbl.setVisible(bool(job.output_path))
        self._open_btn.setVisible(bool(job.output_path))

    def _refresh_error(self, error: tuple[str, dict] | None) -> None:
        key = (TR.language(), error)
        if key == self._error_key:
            return
        self._error_key = key
        self._error_lbl.setVisible(bool(error))
        if error:
            self._error_lbl.setText(t("jobs_panel.last_error", error=render_queue_cause(*error)))
            full = render_error(*error)
            self._error_lbl.setToolTip(full)
            self._error_lbl.setAccessibleDescription(full)

    def refresh_theme(self) -> None:
        self._refresh()

    def retranslate(self) -> None:
        self._refresh()


class _EmptyState(QWidget):
    """Riquadro guida mostrato quando non ci sono link in lista."""

    paste_clicked = pyqtSignal()
    import_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("queueSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addStretch()
        self._msg = QLabel()
        self._msg.setObjectName("emptyTitle")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._msg)
        self._sub = QLabel()
        self._sub.setObjectName("secondaryText")
        self._sub.setWordWrap(True)
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._sub)
        actions = QHBoxLayout()
        actions.addStretch()
        self._btn = QPushButton()
        self._btn.setProperty("primary", "true")
        self.setFocusProxy(self._btn)
        self._btn.clicked.connect(self.paste_clicked)
        actions.addWidget(self._btn)
        self._import_btn = QPushButton()
        self._import_btn.clicked.connect(self.import_clicked)
        actions.addWidget(self._import_btn)
        actions.addStretch()
        layout.addSpacing(6)
        layout.addLayout(actions)
        layout.addStretch()
        self.retranslate()

    def retranslate(self) -> None:
        button_label = t("controls.paste_links")
        self._msg.setText(t("jobs_panel.empty_title"))
        self._sub.setText(t("jobs_panel.empty_hint"))
        self._btn.setText(button_label)
        self._import_btn.setText(t("link_panel.import"))

    def refresh_theme(self) -> None:
        pass  # colori ereditati da QSS globale


class JobsPanel(QWidget):
    """Pannello lista job. Espone gli stessi slot pubblici del precedente."""

    job_double_clicked = pyqtSignal(int)      # file_id
    cancel_job_requested = pyqtSignal(int, bool)  # file_id, delete_folder
    delete_folder_requested = pyqtSignal(int)  # file_id
    import_requested = pyqtSignal()
    paste_links_requested = pyqtSignal()      # empty-state paste button
    restart_job_requested = pyqtSignal(int)   # file_id
    restart_all_failed_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.model = JobsModel()
        self._cards: dict[int, _JobCard] = {}
        self._filter_category = FILTER_ALL
        self.model.aggregates_changed.connect(self._on_aggregates_changed)
        self.model.job_updated.connect(self._on_job_status_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Barra filtri: pulsanti a selezione esclusiva (segmented control).
        self._filters = QWidget()
        filter_row = QHBoxLayout(self._filters)
        filter_row.setContentsMargins(0, 0, 0, 8)
        filter_row.setSpacing(5)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}
        # Etichette base (senza conteggio): il numero di file per categoria
        # viene appeso da _update_filter_counts a ogni cambio di aggregati.
        self._filter_label_keys: dict[str, str] = {
            FILTER_ALL: "jobs_panel.filter_all",
            FILTER_IN_PROGRESS: "jobs_panel.filter_in_progress",
            FILTER_COMPLETED: "jobs_panel.filter_completed",
            FILTER_NOT_COMPLETED: "jobs_panel.filter_not_completed",
        }
        for category in self._filter_label_keys:
            btn = QPushButton()
            btn.setObjectName("queueFilter")
            btn.setCheckable(True)
            btn.setChecked(category == self._filter_category)
            btn.clicked.connect(lambda _checked, c=category: self._on_filter_button_clicked(c))
            self._filter_group.addButton(btn)
            self._filter_buttons[category] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch(1)
        # Pulsante bulk per riavviare tutti i job falliti/abbandonati/annullati.
        self._restart_all_btn = QPushButton(t("jobs_panel.restart_all", n=0))
        self._restart_all_btn.setEnabled(False)
        self._restart_all_btn.setToolTip(t("jobs_panel.restart_all_tooltip"))
        self._restart_all_btn.clicked.connect(self.restart_all_failed_requested)
        filter_row.addWidget(self._restart_all_btn)
        layout.addWidget(self._filters)
        self._filter_empty = QLabel()
        self._filter_empty.setObjectName("secondaryText")
        self._filter_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._filter_empty.setWordWrap(True)
        layout.addWidget(self._filter_empty, 1)

        # Stack: empty state O lista card.
        self._empty = _EmptyState()
        self.setFocusProxy(self._empty)
        self._empty.paste_clicked.connect(self.paste_links_requested)
        self._empty.import_clicked.connect(self.import_requested)
        layout.addWidget(self._empty, 1)

        # Scroll area per le card: solo scroll verticale, mai orizzontale.
        self._scroll = QScrollArea()
        self._scroll.setObjectName("transferList")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("queueList")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._cards_layout = QVBoxLayout(self._content)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(0)
        self._cards_layout.addStretch(1)  # spazio in fondo
        self._scroll.setWidget(self._content)
        self._scroll.setVisible(False)
        layout.addWidget(self._scroll, 1)

        self._on_aggregates_changed()

    # ---- gestione card ---------------------------------------------------

    def _update_visibility(self, counts: dict[str, int] | None = None) -> None:
        has_cards = bool(self._cards)
        self._empty.setVisible(not has_cards)
        self._filters.setVisible(has_cards)
        if counts is None:
            counts = self._category_counts()
        empty_filter = has_cards and counts[self._filter_category] == 0
        self._filter_empty.setVisible(empty_filter)
        self._scroll.setVisible(has_cards and not empty_filter)

    def _add_card(self, file_id: int) -> _JobCard:
        card = _JobCard(self.model, file_id)
        card.cancel_requested.connect(self.cancel_job_requested)
        card.delete_requested.connect(self.delete_folder_requested)
        card.open_folder_requested.connect(self._open_folder_for)
        card.restart_requested.connect(self.restart_job_requested)
        card.double_clicked.connect(self.job_double_clicked)
        # Inserisce PRIMA dell'ultimo stretch.
        self._cards_layout.insertWidget(len(self._cards), card)
        self._cards[file_id] = card
        return card

    def _clear_cards(self) -> None:
        for card in list(self._cards.values()):
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _apply_filter(self) -> None:
        allowed_statuses = _FILTER_CATEGORIES.get(self._filter_category, set())
        for fid, card in self._cards.items():
            job = self.model.get_job(fid)
            if job is None:
                card.setVisible(True)
                continue
            card.setVisible(job.status in allowed_statuses)

    def _on_filter_button_clicked(self, category: str) -> None:
        self._filter_category = category
        self._apply_filter()
        self._update_visibility()

    def _category_counts(self) -> dict[str, int]:
        # Conteggio file per categoria di filtro, derivato dagli aggregati del
        # modello (le tre categorie coprono tutti gli stati possibili).
        agg = self.model.aggregates()
        return {
            FILTER_ALL: agg["total"],
            FILTER_IN_PROGRESS: agg["queued"] + agg["running"],
            FILTER_COMPLETED: agg["completed"],
            FILTER_NOT_COMPLETED: agg["failed"] + agg["cancelled"] + agg["abandoned"],
        }

    def _update_filter_counts(self) -> dict[str, int]:
        self._filter_empty.setText(t("jobs_panel.filtered_empty"))
        counts = self._category_counts()
        for category, btn in self._filter_buttons.items():
            btn.setText(
                t(
                    "jobs_panel.filter_with_count",
                    label=t(self._filter_label_keys[category]),
                    n=counts.get(category, 0),
                )
            )

        return counts

    def _on_aggregates_changed(self) -> None:
        counts = self._update_filter_counts()
        n = self.model.restartable_count()
        self._restart_all_btn.setText(t("jobs_panel.restart_all", n=n))
        self._restart_all_btn.setEnabled(n > 0)
        self._restart_all_btn.setVisible(n > 0)
        self._update_visibility(counts)

    def _on_job_status_changed(self, file_id: int) -> None:
        card = self._cards.get(file_id)
        if card is None:
            return
        job = self.model.get_job(file_id)
        if job is None:
            card.setVisible(True)
            return
        allowed = _FILTER_CATEGORIES.get(self._filter_category, set())
        card.setVisible(job.status in allowed)

    def _open_folder_for(self, file_id: int) -> None:
        job = self.model.get_job(file_id)
        if job and job.output_path:
            p = Path(job.output_path)
            folder = p.parent if p.is_file() else p
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---- slot pubblici (stesso contratto di JobsPanel precedente) --------

    def reset(self, links: list[str] | dict[int, str]) -> None:
        self._clear_cards()
        self.model.reset(links)
        for job in self.model.jobs_iter():
            self._add_card(job.file_id)
        self._apply_filter()
        self._update_visibility()

    def append_jobs(self, jobs: list[tuple[int, str]]) -> None:
        """Accoda righe a quelle esistenti (aggiunta a caldo a sessione viva).

        Il gemello di `reset()` che NON cancella nulla: le card gia' presenti
        restano com'erano, coi loro dati. L'ordine resta quello di creazione
        anche quando i link sono stati messi in TESTA alla coda: la lista e'
        cronologica, chi sta scaricando lo dice il proprio stato.
        """
        for file_id in self.model.append_jobs(jobs):
            self._add_card(file_id)
        self._apply_filter()
        self._update_visibility()

    def on_progress(self, file_id: int, _cycle: int, percent: int) -> None:
        self.model.set_progress(file_id, percent)

    def on_ip(self, file_id: int, _cycle: int, ip: str) -> None:
        self.model.set_ip(file_id, ip)

    def on_failed(self, file_id: int, _cycle: int, code: str, params: dict) -> None:
        self.model.add_failure(file_id, code, params)

    def on_cycle_completed(self, file_id: int, _cycle: int) -> None:
        self.model.set_progress(file_id, 100)

    def on_all_done(self, file_id: int) -> None:
        self.model.mark_completed(file_id)

    def on_fatal(self, file_id: int, code: str, params: dict) -> None:
        self.model.mark_failed_fatal(file_id, code, params)

    def on_abandoned(
        self, file_id: int, _url: str, attempts: int, code: str, params: dict,
    ) -> None:
        # Qui, e solo qui, il codice del canale `failed` diventa quello
        # dell'ABBANDONO: e' l'unico punto che sa da quale segnale arriva.
        # Senza, la frase passerebbe dai due punti alle parentesi.
        self.model.mark_abandoned(
            file_id, attempts, ABANDON_ALIASES.get(code, code), params,
        )

    def on_cancel_all(self) -> None:
        self.model.mark_cancelled_all()

    def on_throughput(self, file_id: int, bps: float, downloaded: object, total: object) -> None:
        self.model.set_throughput(file_id, bps, int(downloaded), int(total))

    def on_file_resolved(self, file_id: int, file_name: str, _file_size: object, path: str) -> None:
        """Aggiorna nome file appena risolto (prima del completamento)."""
        self.model.set_file_info(file_id, file_name, path)

    def on_completed_info(
        self, file_id: int, _url: str, file_name: str, _file_size: object, path: str,
    ) -> None:
        self.model.set_file_info(file_id, file_name, path)

    # ---- i18n ------------------------------------------------------------

    def retranslate(self) -> None:
        """Ritraduce il cromo del pannello e ricasca su stato vuoto e card."""
        self._update_filter_counts()
        self._restart_all_btn.setText(
            t("jobs_panel.restart_all", n=self.model.restartable_count())
        )
        self._restart_all_btn.setToolTip(t("jobs_panel.restart_all_tooltip"))
        self._empty.retranslate()
        for card in self._cards.values():
            card.retranslate()

    def refresh_theme(self) -> None:
        self._empty.refresh_theme()
        for card in self._cards.values():
            card.refresh_theme()
