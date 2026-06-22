# Finestra "Funzioni Sperimentali": superficie separata dal popup
# "Impostazioni" stabile. Ospita le leve sui proxy ancora in prova
# (connessioni per file configurabili, selezione per velocita' osservata),
# disattivate di default. I due valori sono persistiti in preferences.json
# e ricaricati al riavvio; MainWindow li legge a inizio sessione (non a
# caldo durante un download in corso).
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
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
    load_throughput_selection,
    save_connections_per_file,
    save_throughput_selection,
)

_FEEDBACK_URL = "https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues"


class ExperimentalFeaturesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Funzioni Sperimentali")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        header = QLabel(
            "<b>Funzioni Sperimentali</b> — funzioni in prova, disattivate di "
            "default. Attivale per testarle e facci sapere com'è andata: ogni "
            "feedback ci aiuta a migliorarle."
        )
        header.setWordWrap(True)
        layout.addWidget(header)
        layout.addSpacing(8)

        # --- Controllo 1: connessioni per file. ---
        conn_row = QHBoxLayout()
        conn_lbl = QLabel("Connessioni per file:")
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(PARALLEL_CONNECTIONS_MIN, PARALLEL_CONNECTIONS_MAX)
        self.connections_spin.setValue(load_connections_per_file())
        self.connections_spin.valueChanged.connect(save_connections_per_file)
        conn_row.addWidget(conn_lbl)
        conn_row.addWidget(self.connections_spin)
        conn_row.addStretch(1)
        layout.addLayout(conn_row)

        conn_desc = QLabel(
            "Quante parti del file scaricare in parallelo, ognuna su un proxy "
            "diverso. Più connessioni possono aumentare la velocità complessiva, "
            "ma richiedono più proxy buoni nello stesso momento. Default: 4."
        )
        conn_desc.setWordWrap(True)
        conn_desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(conn_desc)
        layout.addSpacing(10)

        # --- Controllo 2: selezione per velocita'. ---
        self.throughput_check = QCheckBox("Selezione per velocità")
        self.throughput_check.setChecked(load_throughput_selection())
        self.throughput_check.toggled.connect(save_throughput_selection)
        layout.addWidget(self.throughput_check)

        throughput_desc = QLabel(
            "Il pool misura la velocità reale di ogni proxy e preferisce i più "
            "rapidi, ruotandoli per non farli bloccare da Mega. All'inizio "
            "servono pochi secondi per \"imparare\" quali sono i migliori. "
            "Sperimentale: se noti comportamenti strani, disattivala e segnalacelo."
        )
        throughput_desc.setWordWrap(True)
        throughput_desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(throughput_desc)
        layout.addSpacing(10)

        # --- Feedback. ---
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
