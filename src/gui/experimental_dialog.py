# Finestra "Funzioni Sperimentali": superficie separata dal popup
# "Impostazioni" stabile. La selezione per velocita' (Leva B) resta ritirata
# dall'interfaccia; le connessioni per file (Leva A) sono invece riesposte
# qui per permettere prove senza ricompilare i default di config.py.
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.core.config import PARALLEL_CONNECTIONS_MAX, PARALLEL_CONNECTIONS_MIN
from src.gui.preferences import load_connections_per_file, save_connections_per_file

_FEEDBACK_URL = "https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues"


class ExperimentalFeaturesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Funzioni Sperimentali")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        conn_row = QHBoxLayout()
        conn_label = QLabel("Connessioni per file:")
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(PARALLEL_CONNECTIONS_MIN, PARALLEL_CONNECTIONS_MAX)
        self.connections_spin.setValue(load_connections_per_file())
        self.connections_spin.valueChanged.connect(save_connections_per_file)
        conn_row.addWidget(conn_label)
        conn_row.addWidget(self.connections_spin)
        layout.addLayout(conn_row)

        conn_desc = QLabel(
            "Quante parti dello stesso file scaricare in parallelo, ognuna su un "
            "proxy diverso. Piu' connessioni = download piu' veloce ma piu' "
            "proxy consumati. Default 10."
        )
        conn_desc.setWordWrap(True)
        conn_desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(conn_desc)
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
