# Finestra "Funzioni Sperimentali": superficie separata dal popup
# "Impostazioni" stabile. Dalla 1.9.0 non ospita piu' leve attive: i due
# controlli storici (connessioni per file, selezione per velocita') sono
# stati ritirati dall'interfaccia. Il dialog resta come segnaposto per
# future leve in prova; il motore (selection_mode/connections_per_file)
# e' invariato e usa i default di config.py.
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

_FEEDBACK_URL = "https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues"


class ExperimentalFeaturesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Funzioni Sperimentali")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        placeholder = QLabel("Nessuna funzione sperimentale attiva in questa versione.")
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: gray; font-size: 9pt;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder)
        layout.addSpacing(8)

        feedback_lbl = QLabel(
            f'Hai un\'idea o un problema? Apri una segnalazione su GitHub: '
            f'<a href="{_FEEDBACK_URL}">{_FEEDBACK_URL}</a>'
        )
        feedback_lbl.setWordWrap(True)
        feedback_lbl.setOpenExternalLinks(True)
        layout.addWidget(feedback_lbl)
        layout.addSpacing(8)

        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
