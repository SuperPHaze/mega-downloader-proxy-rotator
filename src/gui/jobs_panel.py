# Lista job a righe-card con barra di avanzamento integrata ed espansione
# inline. Sostituisce la precedente QTableView.
#
# Architettura: QScrollArea + un _JobCard per riga, creato e aggiornato da
# JobsPanel. Il JobsModel resta la fonte di verita'; le card si aggiornano
# tramite model.job_updated (segnale con file_id).
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import (
    QModelIndex,
    QUrl,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.failed_log import failed_log_path
from src.gui import style as _style
from src.gui.jobs_model import (
    Job,
    JobsModel,
    STATUS_ABANDONED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
)

# Categorie del filtro "Mostra:" — ciascuna raggruppa piu' stati. Le tre
# categorie insieme coprono tutti gli stati possibili (nessuna voce "Tutti").
FILTER_IN_PROGRESS = "in_progress"
FILTER_COMPLETED = "completed"
FILTER_NOT_COMPLETED = "not_completed"

_FILTER_CATEGORIES: dict[str, set[str]] = {
    FILTER_IN_PROGRESS: {STATUS_QUEUED, STATUS_RUNNING},
    FILTER_COMPLETED: {STATUS_COMPLETED},
    FILTER_NOT_COMPLETED: {STATUS_FAILED, STATUS_CANCELLED, STATUS_ABANDONED},
}

# Colori foreground (testo) per badge di stato — letti da CURRENT_PALETTE.
_STATUS_FG_KEY = {
    STATUS_QUEUED: "text_dim",
    STATUS_RUNNING: "accent_active",
    STATUS_COMPLETED: "accent_ok",
    STATUS_FAILED: "accent_fail",
    STATUS_CANCELLED: "accent_warn",
    STATUS_ABANDONED: "accent_fail",
}
_STATUS_BG_KEY = {
    STATUS_QUEUED: "status_bg_queued",
    STATUS_RUNNING: "status_bg_running",
    STATUS_COMPLETED: "status_bg_completed",
    STATUS_FAILED: "status_bg_failed",
    STATUS_CANCELLED: "status_bg_cancelled",
    STATUS_ABANDONED: "status_bg_abandoned",
}
_STATUS_LABELS = {
    STATUS_QUEUED: "In coda",
    STATUS_RUNNING: "In corso",
    STATUS_COMPLETED: "Completato",
    STATUS_FAILED: "Fallito",
    STATUS_CANCELLED: "Annullato",
    STATUS_ABANDONED: "Abbandonato",
}
_PROGRESS_COLOR_KEY = {
    STATUS_RUNNING: "accent_active",
    STATUS_COMPLETED: "accent_ok",
    STATUS_FAILED: "accent_fail",
    STATUS_ABANDONED: "accent_fail",
    STATUS_CANCELLED: "accent_warn",
    STATUS_QUEUED: "text_dim",
}

# Status icon (unicode).
_STATUS_ICON = {
    STATUS_QUEUED: "⏳",
    STATUS_RUNNING: "▶",
    STATUS_COMPLETED: "✓",
    STATUS_FAILED: "✗",
    STATUS_CANCELLED: "⊘",
    STATUS_ABANDONED: "✗",
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
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, self._elide_mode, max(1, self.width()))
        super().setText(elided)


def _fmt_speed(bps: float) -> str:
    if bps < 1:
        return ""
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


def _short_url(url: str) -> str:
    # Mostra la parte finale dell'URL Mega come titolo prima che il nome file
    # sia noto.
    try:
        part = url.split("/")[-1]
        if "#" in part:
            handle = part.split("#")[0]
            return f"mega://{handle}" if handle else url
        return part[:40] or url
    except Exception:
        return url[:60]


class _JobCard(QFrame):
    cancel_requested = pyqtSignal(int)        # file_id
    delete_requested = pyqtSignal(int)        # file_id
    open_folder_requested = pyqtSignal(int)   # file_id
    restart_requested = pyqtSignal(int)       # file_id
    double_clicked = pyqtSignal(int)          # file_id

    def __init__(self, model: JobsModel, file_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.file_id = file_id
        self._expanded = False

        self._build_ui()
        self._refresh()
        model.job_updated.connect(self._on_model_updated)

    def _build_ui(self) -> None:
        p = _style.CURRENT_PALETTE
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {p['card_bg']}; "
            f"border: 1px solid {p['card_border']}; border-radius: 8px; }}"
        )
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        # --- Riga principale ---
        top = QHBoxLayout()
        top.setSpacing(8)

        self._icon_lbl = QLabel("⏳")
        self._icon_lbl.setFixedWidth(20)
        f = QFont()
        f.setPointSize(11)
        self._icon_lbl.setFont(f)
        top.addWidget(self._icon_lbl)

        # Nome file / URL (stretch): eliso a destra per non forzare larghezza.
        self._name_lbl = _ElidedLabel(Qt.TextElideMode.ElideRight)
        self._name_lbl.setFont(QFont("Segoe UI", 10))
        self._name_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        top.addWidget(self._name_lbl, 1)

        # Velocita'.
        self._speed_lbl = QLabel()
        sf = QFont("Consolas", 9)
        self._speed_lbl.setFont(sf)
        top.addWidget(self._speed_lbl)

        # Badge stato.
        self._badge = QLabel()
        bf = QFont("Segoe UI", 8)
        bf.setBold(True)
        self._badge.setFont(bf)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedWidth(88)
        top.addWidget(self._badge)

        # Pulsante azione contestuale — dimensioni aumentate per bersaglio più comodo.
        top.addSpacing(6)
        self._action_btn = QPushButton()
        self._action_btn.setFixedWidth(34)
        self._action_btn.setFixedHeight(30)
        self._action_btn.setToolTip("")
        self._action_btn.clicked.connect(self._on_action)
        top.addWidget(self._action_btn)

        outer.addLayout(top)

        # --- Barra di avanzamento ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        outer.addWidget(self._progress)

        # --- Pannello dettagli (collassato di default) ---
        self._detail = QFrame()
        self._detail.setFrameShape(QFrame.Shape.NoFrame)
        dl = QVBoxLayout(self._detail)
        dl.setContentsMargins(24, 2, 4, 2)
        dl.setSpacing(2)

        self._ip_lbl = QLabel()
        self._ip_lbl.setFont(QFont("Consolas", 9))
        dl.addWidget(self._ip_lbl)

        self._attempts_lbl = QLabel()
        self._attempts_lbl.setFont(QFont("Segoe UI", 9))
        dl.addWidget(self._attempts_lbl)

        path_row = QHBoxLayout()
        # Percorso: eliso al centro (mantiene inizio e nome file visibili).
        # Tooltip = percorso completo; TextSelectableByMouse per copiare.
        self._path_lbl = _ElidedLabel(Qt.TextElideMode.ElideMiddle)
        self._path_lbl.setFont(QFont("Consolas", 8))
        self._path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        path_row.addWidget(self._path_lbl, 1)
        self._open_btn = QPushButton("Apri cartella")
        self._open_btn.setFixedHeight(22)
        self._open_btn.clicked.connect(self._open_folder)
        path_row.addWidget(self._open_btn)
        dl.addLayout(path_row)

        self._detail.setVisible(False)
        outer.addWidget(self._detail)

    # ---- segnali/slot interni --------------------------------------------

    def _on_model_updated(self, file_id: int) -> None:
        if file_id == self.file_id:
            self._refresh()

    def _on_action(self) -> None:
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            self.cancel_requested.emit(self.file_id)
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
        self.double_clicked.emit(self.file_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Clic semplice: toggle espansione dettagli.
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)
        super().mousePressEvent(event)

    # ---- refresh visuale --------------------------------------------------

    def _refresh(self) -> None:
        job = self.model.get_job(self.file_id)
        if job is None:
            return
        p = _style.CURRENT_PALETTE

        # Card background (aggiornato per il tema).
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {p['card_bg']}; "
            f"border: 1px solid {p['card_border']}; border-radius: 8px; }}"
        )

        # Icona e nome.
        icon = _STATUS_ICON.get(job.status, "•")
        icon_color = p.get(_STATUS_FG_KEY.get(job.status, "text"), p["text"])
        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(f"color: {icon_color}; border: none;")

        title = job.file_name or _short_url(job.url)
        dur = job.duration_s()
        dur_str = f"  {int(dur) // 60:02d}:{int(dur) % 60:02d}" if job.started_at else ""
        self._name_lbl.setText(title + dur_str)
        self._name_lbl.setStyleSheet(f"color: {p['text']}; border: none;")

        # Velocita'.
        speed_str = _fmt_speed(job.speed) if job.status == STATUS_RUNNING else ""
        self._speed_lbl.setText(speed_str)
        self._speed_lbl.setStyleSheet(
            f"color: {p['accent_info']}; border: none;"
        )

        # Badge stato.
        fg = p.get(_STATUS_FG_KEY.get(job.status, "text_dim"), p["text"])
        bg = p.get(_STATUS_BG_KEY.get(job.status, "panel_alt"), p["panel_alt"])
        label = _STATUS_LABELS.get(job.status, job.status)
        self._badge.setText(label)
        self._badge.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 4px; "
            f"padding: 2px 6px; border: 1px solid {fg}40;"
        )

        # Pulsante azione — selettori CSS multipli per hover visibile.
        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            self._action_btn.setText("✕")
            self._action_btn.setToolTip("Annulla download")
            self._action_btn.setStyleSheet(
                f"QPushButton {{ color: {p['danger']}; border: 1.5px solid {p['danger']}; "
                f"border-radius: 4px; background: transparent; font-size: 12pt; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {p['danger_hover_bg']}; color: {p['danger']}; }}"
                f"QPushButton:pressed {{ background-color: {p['danger']}; color: white; }}"
            )
        elif job.status == STATUS_COMPLETED:
            self._action_btn.setText("📂")
            self._action_btn.setToolTip("Apri cartella")
            self._action_btn.setStyleSheet(
                f"QPushButton {{ color: {p['accent_ok']}; border: 1px solid {p['border']}; "
                f"border-radius: 4px; background: transparent; font-size: 12pt; }}"
                f"QPushButton:hover {{ background-color: {p['panel_alt']}; }}"
            )
        elif job.status in (STATUS_FAILED, STATUS_ABANDONED, STATUS_CANCELLED):
            self._action_btn.setText("↻")
            self._action_btn.setToolTip("Riavvia download")
            self._action_btn.setStyleSheet(
                f"QPushButton {{ color: {p['accent_info']}; border: 1px solid {p['accent_info']}; "
                f"border-radius: 4px; background: transparent; font-size: 14pt; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {p['selection_bg']}; color: {p['accent_info']}; }}"
                f"QPushButton:pressed {{ background-color: {p['accent_info']}; color: white; }}"
            )
        else:
            self._action_btn.setText("⎘")
            self._action_btn.setToolTip("Copia URL")
            self._action_btn.setStyleSheet(
                f"QPushButton {{ color: {p['text_dim']}; border: 1px solid {p['border']}; "
                f"border-radius: 4px; background: transparent; font-size: 12pt; }}"
                f"QPushButton:hover {{ background-color: {p['panel_alt']}; }}"
            )

        # Progress bar.
        pct = job.progress
        if job.status == STATUS_COMPLETED:
            pct = 100
        self._progress.setValue(pct)
        chunk_color = p.get(_PROGRESS_COLOR_KEY.get(job.status, "text_dim"), p["text_dim"])
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {p['panel_alt']}; border: none; "
            f"border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {chunk_color}; border-radius: 3px; }}"
        )

        # Pannello dettagli.
        self._ip_lbl.setText(f"IP corrente: {job.current_ip or '—'}")
        self._ip_lbl.setStyleSheet(f"color: {p['text_dim']}; border: none;")
        self._attempts_lbl.setText(
            f"Tentativi: {job.attempts}"
            + (f"  •  Errori: {job.errors_count}" if job.errors_count else "")
            + (f"  •  Ultimo errore: {job.last_error}" if job.last_error else "")
        )
        self._attempts_lbl.setStyleSheet(f"color: {p['text_dim']}; border: none;")
        path_text = job.output_path or "—"
        self._path_lbl.setText(path_text)
        self._path_lbl.setStyleSheet(f"color: {p['text_dim']}; border: none;")
        self._open_btn.setVisible(bool(job.output_path))

    def refresh_theme(self) -> None:
        self._refresh()


class _EmptyState(QWidget):
    """Riquadro guida mostrato quando non ci sono link in lista."""

    paste_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel("⬇")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFont(QFont("Segoe UI", 36))
        layout.addWidget(icon_lbl)

        msg = QLabel("Aggiungi i tuoi link Mega per iniziare")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setFont(QFont("Segoe UI", 13))
        layout.addWidget(msg)

        sub = QLabel(
            "Usa il pulsante «Aggiungi link» nella barra comandi\n"
            "oppure clicca qui sotto."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        btn = QPushButton("  Aggiungi link")
        btn.setProperty("primary", "true")
        btn.setFixedWidth(160)
        btn.clicked.connect(self.paste_clicked)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)

    def refresh_theme(self) -> None:
        pass  # colori ereditati da QSS globale


class JobsPanel(QWidget):
    """Pannello lista job. Espone gli stessi slot pubblici del precedente."""

    job_double_clicked = pyqtSignal(int)      # file_id
    cancel_job_requested = pyqtSignal(int, bool)  # file_id, delete_folder
    delete_folder_requested = pyqtSignal(int)  # file_id
    paste_links_requested = pyqtSignal()      # empty-state paste button
    restart_job_requested = pyqtSignal(int)   # file_id
    restart_all_failed_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.model = JobsModel()
        self._cards: dict[int, _JobCard] = {}
        self._filter_category: str = FILTER_IN_PROGRESS
        self.model.aggregates_changed.connect(self._on_aggregates_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Barra filtri: pulsanti a selezione esclusiva (segmented control).
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(6, 4, 6, 4)
        filter_row.addWidget(QLabel("Mostra:"))
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}
        for category, label in (
            (FILTER_IN_PROGRESS, "In corso"),
            (FILTER_COMPLETED, "Completati"),
            (FILTER_NOT_COMPLETED, "Non completati"),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(category == FILTER_IN_PROGRESS)
            btn.clicked.connect(lambda _checked, c=category: self._on_filter_button_clicked(c))
            self._filter_group.addButton(btn)
            self._filter_buttons[category] = btn
            filter_row.addWidget(btn)
        self._style_filter_buttons()
        filter_row.addStretch(1)
        # Pulsante bulk per riavviare tutti i job falliti/abbandonati/annullati.
        self._restart_all_btn = QPushButton("Riavvia falliti (0)")
        self._restart_all_btn.setEnabled(False)
        self._restart_all_btn.setToolTip(
            "Riavvia tutti i download falliti, abbandonati o annullati.\n"
            "Il download riprende dai segmenti già scaricati (.part)."
        )
        self._restart_all_btn.clicked.connect(self.restart_all_failed_requested)
        filter_row.addWidget(self._restart_all_btn)
        layout.addLayout(filter_row)

        # Stack: empty state O lista card.
        self._empty = _EmptyState()
        self._empty.paste_clicked.connect(self.paste_links_requested)
        layout.addWidget(self._empty)

        # Scroll area per le card: solo scroll verticale, mai orizzontale.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._cards_layout = QVBoxLayout(self._content)
        self._cards_layout.setContentsMargins(6, 4, 6, 4)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch(1)  # spazio in fondo
        self._scroll.setWidget(self._content)
        self._scroll.setVisible(False)
        layout.addWidget(self._scroll, 1)

        self._update_visibility()

    # ---- gestione card ---------------------------------------------------

    def _update_visibility(self) -> None:
        has_cards = bool(self._cards)
        self._empty.setVisible(not has_cards)
        self._scroll.setVisible(has_cards)

    def _add_card(self, file_id: int) -> _JobCard:
        card = _JobCard(self.model, file_id)
        card.cancel_requested.connect(
            lambda fid: self.cancel_job_requested.emit(fid, True)
        )
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
        self._style_filter_buttons()
        self._apply_filter()

    def _style_filter_buttons(self) -> None:
        p = _style.CURRENT_PALETTE
        for category, btn in self._filter_buttons.items():
            if category == self._filter_category:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {p['primary']}; color: white; "
                    f"border: 1px solid {p['primary']}; border-radius: 4px; "
                    f"padding: 4px 10px; font-weight: bold; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: transparent; color: {p['text']}; "
                    f"border: 1px solid {p['border']}; border-radius: 4px; padding: 4px 10px; }}"
                    f"QPushButton:hover {{ background-color: {p['panel_alt']}; }}"
                )

    def _on_aggregates_changed(self) -> None:
        n = self.model.restartable_count()
        self._restart_all_btn.setText(f"Riavvia falliti ({n})")
        self._restart_all_btn.setEnabled(n > 0)

    def _open_folder_for(self, file_id: int) -> None:
        job = self.model.get_job(file_id)
        if job and job.output_path:
            p = Path(job.output_path)
            folder = p.parent if p.is_file() else p
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---- slot pubblici (stesso contratto di JobsPanel precedente) --------

    def reset(self, links: list[str]) -> None:
        self._clear_cards()
        self.model.reset(links)
        for i in range(len(links)):
            self._add_card(i)
        self._apply_filter()
        self._update_visibility()

    def on_progress(self, file_id: int, _cycle: int, percent: int) -> None:
        self.model.set_progress(file_id, percent)

    def on_ip(self, file_id: int, _cycle: int, ip: str) -> None:
        self.model.set_ip(file_id, ip)

    def on_failed(self, file_id: int, _cycle: int, reason: str) -> None:
        self.model.add_failure(file_id, reason)

    def on_cycle_completed(self, file_id: int, _cycle: int) -> None:
        self.model.set_progress(file_id, 100)

    def on_all_done(self, file_id: int) -> None:
        self.model.mark_completed(file_id)

    def on_fatal(self, file_id: int, reason: str) -> None:
        self.model.mark_failed_fatal(file_id, reason)

    def on_abandoned(self, file_id: int, _url: str, attempts: int, last_error: str) -> None:
        self.model.mark_abandoned(file_id, attempts, last_error)

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

    def refresh_theme(self) -> None:
        self._style_filter_buttons()
        self._empty.refresh_theme()
        for card in self._cards.values():
            card.refresh_theme()
