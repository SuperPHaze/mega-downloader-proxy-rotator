# Barra sottile e richiudibile mostrata in cima alla finestra principale
# quando il controllo aggiornamenti silenzioso all'avvio trova una nuova
# versione disponibile.
#
# i18n: superficie PERSISTENTE (nasce con la finestra e resta viva anche
# nascosta), quindi espone `retranslate()` come ControlsBar. La versione
# annunciata e' tenuta in `_version` proprio per poter riscrivere l'etichetta
# nella lingua nuova senza che il chiamante debba ripassarla.
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src.gui.i18n import t


class UpdateBanner(QWidget):
    download_requested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("background-color: #2d6cdf; color: white;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Nessuna versione ancora annunciata: l'etichetta resta vuota finche'
        # non arriva show_update().
        self._version = ""

        self._label = QLabel("")
        layout.addWidget(self._label, 1)

        self._download_btn = QPushButton()
        self._download_btn.clicked.connect(self.download_requested)
        layout.addWidget(self._download_btn)

        # Glifo di chiusura: e' un'icona, non testo da tradurre.
        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        self.retranslate()
        self.hide()

    # ---- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive i testi nella lingua corrente (chiamato dal costruttore e
        da MainWindow._on_language_changed)."""
        self._download_btn.setText(t("update_banner.download"))
        self._refresh_label()

    def _refresh_label(self) -> None:
        self._label.setText(
            t("update_banner.available", version=self._version) if self._version else ""
        )

    # ---- uso ---------------------------------------------------------------

    def show_update(self, version: str) -> None:
        self._version = version
        self._refresh_label()
        self.show()

    def _on_close(self) -> None:
        self.hide()
        self.dismissed.emit()
