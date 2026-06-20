# Barra sottile e richiudibile mostrata in cima alla finestra principale
# quando il controllo aggiornamenti silenzioso all'avvio trova una nuova
# versione disponibile.
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class UpdateBanner(QWidget):
    download_requested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("background-color: #2d6cdf; color: white;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._label = QLabel("")
        layout.addWidget(self._label, 1)

        download_btn = QPushButton("Scarica")
        download_btn.clicked.connect(self.download_requested)
        layout.addWidget(download_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        self.hide()

    def show_update(self, version: str) -> None:
        self._label.setText(f"Disponibile la versione {version}.")
        self.show()

    def _on_close(self) -> None:
        self.hide()
        self.dismissed.emit()
