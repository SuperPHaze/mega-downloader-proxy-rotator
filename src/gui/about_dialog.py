# Finestra "Info": nome/acronimo/autore/nick/link (risolti dal branding
# remoto con fallback a cache/default), licenza, e controllo aggiornamenti
# manuale. Il branding viene aggiornato a runtime se il fetch remoto
# (in QThread) ritorna un risultato piu' recente della cache.
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImageReader, QMovie, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.core.branding import Branding, resolve as resolve_branding
from src.core.config import APP_LICENSE, APP_VERSION, LOGO_DARK_PATH, LOGO_LIGHT_PATH
from src.gui.branding_fetch import BrandingFetchWorker, branding_enabled
from src.gui.preferences import (
    load_check_updates_on_startup,
    load_dark_theme,
    save_check_updates_on_startup,
)
from src.gui.update_check import (
    STATUS_AVAILABLE,
    STATUS_UP_TO_DATE,
    UpdateCheckWorker,
    repo_url,
    updates_enabled,
)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Info")
        self.setMinimumWidth(380)
        self._worker: UpdateCheckWorker | None = None
        self._branding_worker: BrandingFetchWorker | None = None
        self._movie: QMovie | None = None

        layout = QVBoxLayout(self)

        self._logo_lbl = QLabel()
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._logo_lbl)

        self._title_lbl = QLabel()
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title_lbl)

        self._author_lbl = self._centered_label("")
        layout.addWidget(self._author_lbl)
        layout.addWidget(self._centered_label(f"Licenza: {APP_LICENSE}"))

        self._branding_link_lbl = QLabel()
        self._branding_link_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._branding_link_lbl.setOpenExternalLinks(True)
        layout.addWidget(self._branding_link_lbl)

        self._apply_branding(resolve_branding())

        if updates_enabled():
            link_lbl = QLabel(f'<a href="{repo_url()}">{repo_url()}</a>')
            link_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            link_lbl.setOpenExternalLinks(True)
            layout.addWidget(link_lbl)

        layout.addSpacing(8)

        update_row = QHBoxLayout()
        self._update_status_lbl = QLabel("Controllo aggiornamenti non eseguito.")
        self._check_btn = QPushButton("Controlla aggiornamenti")
        self._check_btn.clicked.connect(self._check_for_updates)
        update_row.addWidget(self._update_status_lbl, 1)
        update_row.addWidget(self._check_btn)
        layout.addLayout(update_row)

        if not updates_enabled():
            self._check_btn.setEnabled(False)
            self._update_status_lbl.setText("Controllo aggiornamenti non configurato.")

        self._startup_check_box = QCheckBox("Controlla aggiornamenti all'avvio")
        self._startup_check_box.setChecked(load_check_updates_on_startup())
        self._startup_check_box.toggled.connect(save_check_updates_on_startup)
        layout.addWidget(self._startup_check_box)

        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._start_branding_fetch()

    # ---- branding (nome/autore/link/logo) ---------------------------------

    def _apply_branding(self, b: Branding) -> None:
        self._title_lbl.setText(f"<b>{b.name}</b> ({b.acronym}) — v{APP_VERSION}")
        self._author_lbl.setText(f"Autore: {b.author}")

        github = b.links.get("github") if b.links else None
        if b.nick and github:
            self._branding_link_lbl.setText(f'<a href="{github}">{b.nick}</a>')
            self._branding_link_lbl.setVisible(True)
        elif b.nick:
            self._branding_link_lbl.setText(b.nick)
            self._branding_link_lbl.setVisible(True)
        else:
            self._branding_link_lbl.setVisible(False)

        self._set_logo(self._resolve_logo_path(b))

    @staticmethod
    def _resolve_logo_path(b: Branding) -> str | None:
        """Logo remoto in cache se presente, altrimenti fallback offline
        cotto nell'app scelto in base al tema corrente (la finestra Info e'
        modale: il tema non puo' cambiare mentre e' aperta)."""
        if b.logo_path:
            return b.logo_path
        fallback = LOGO_DARK_PATH if load_dark_theme() else LOGO_LIGHT_PATH
        return str(fallback) if fallback.exists() else None

    def _set_logo(self, logo_path: str | None) -> None:
        """Mostra il logo: QMovie se animato (GIF multi-frame), altrimenti
        QPixmap statico. Ferma sempre il QMovie precedente prima di
        sostituirlo, per non lasciare timer pendenti (vedi closeEvent)."""
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        self._logo_lbl.setMovie(None)
        self._logo_lbl.clear()

        if not logo_path:
            self._logo_lbl.setVisible(False)
            return

        reader = QImageReader(logo_path)
        is_animated = reader.canRead() and reader.supportsAnimation() and reader.imageCount() > 1

        if is_animated:
            movie = QMovie(logo_path)
            if not movie.isValid():
                self._logo_lbl.setVisible(False)
                return
            movie.jumpToFrame(0)
            frame_size = movie.currentImage().size()
            if frame_size.isValid() and frame_size.height() > 0:
                scale = 96 / frame_size.height()
                movie.setScaledSize(
                    QSize(max(1, round(frame_size.width() * scale)), 96)
                )
            self._movie = movie
            self._logo_lbl.setMovie(movie)
            movie.start()
            self._logo_lbl.setVisible(True)
            return

        pix = QPixmap(logo_path)
        if pix.isNull():
            self._logo_lbl.setVisible(False)
            return
        self._logo_lbl.setPixmap(
            pix.scaledToHeight(96, Qt.TransformationMode.SmoothTransformation)
        )
        self._logo_lbl.setVisible(True)

    def _start_branding_fetch(self) -> None:
        if not branding_enabled():
            return
        self._branding_worker = BrandingFetchWorker()
        self._branding_worker.branding_updated.connect(
            self._apply_branding, Qt.ConnectionType.QueuedConnection
        )
        self._branding_worker.start()

    @staticmethod
    def _centered_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        return lbl

    # ---- controllo aggiornamenti -------------------------------------------

    def _check_for_updates(self) -> None:
        if not updates_enabled():
            return
        self._check_btn.setEnabled(False)
        self._update_status_lbl.setText("Controllo in corso…")
        self._worker = UpdateCheckWorker()
        self._worker.finished_check.connect(
            self._on_check_done, Qt.ConnectionType.QueuedConnection
        )
        self._worker.start()

    def _on_check_done(self, status: str, latest_version: str) -> None:
        self._check_btn.setEnabled(True)
        if status == STATUS_AVAILABLE:
            self._update_status_lbl.setText(f"Disponibile la versione {latest_version}.")
        elif status == STATUS_UP_TO_DATE:
            self._update_status_lbl.setText("Sei aggiornato all'ultima versione.")
        else:
            self._update_status_lbl.setText("Impossibile determinare se ci sono aggiornamenti.")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        if self._branding_worker is not None and self._branding_worker.isRunning():
            self._branding_worker.wait(2000)
        if self._movie is not None:
            self._movie.stop()
        super().closeEvent(event)
