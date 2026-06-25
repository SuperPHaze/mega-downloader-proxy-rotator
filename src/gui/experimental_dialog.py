# Finestra "Funzioni Sperimentali": superficie separata dal popup
# "Impostazioni" stabile. La selezione per velocita' (Leva B) resta ritirata
# dall'interfaccia; le connessioni per file (Leva A) e il budget per pezzo
# sono invece riesposti qui per permettere prove senza ricompilare i default
# di config.py.
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
from src.gui.preferences import (
    load_connections_per_file,
    load_segment_max_duration_s,
    save_connections_per_file,
    save_segment_max_duration_s,
)

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

        budget_row = QHBoxLayout()
        budget_label = QLabel("Budget per pezzo (s):")
        self.segment_max_duration_spin = QSpinBox()
        self.segment_max_duration_spin.setRange(60, 1800)
        self.segment_max_duration_spin.setSingleStep(30)
        self.segment_max_duration_spin.setSuffix(" s")
        self.segment_max_duration_spin.setValue(load_segment_max_duration_s())
        self.segment_max_duration_spin.valueChanged.connect(save_segment_max_duration_s)
        budget_row.addWidget(budget_label)
        budget_row.addWidget(self.segment_max_duration_spin)
        layout.addLayout(budget_row)

        budget_desc = QLabel(
            "Tempo massimo per scaricare un pezzo da un proxy, poi si cambia. "
            "Default 180 s."
        )
        budget_desc.setWordWrap(True)
        budget_desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(budget_desc)
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
