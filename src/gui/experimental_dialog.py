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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
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

_CONN_DESC_SHORT = (
    "Parti del file scaricate in parallelo, una per proxy. Default 10."
)
_CONN_DESC_LONG = (
    "Quante parti del file vengono scaricate contemporaneamente, ognuna su un "
    "proxy diverso. Più connessioni aumentano la velocità ma consumano più "
    "proxy nello stesso istante; con pochi proxy buoni può essere "
    "controproducente. Intervallo 2–16, default 10."
)
_BUDGET_DESC_SHORT = (
    "Tempo massimo per scaricare un pezzo da un proxy, poi si cambia. Default 180 s."
)
_BUDGET_DESC_LONG = (
    "Tempo massimo concesso a un proxy per completare un singolo pezzo. "
    "Superato il budget il tentativo viene annullato e il pezzo riprovato su "
    "un altro proxy, anche se la velocità era accettabile. Alzalo se usi "
    "pezzi grandi (128/256 MB) su proxy non velocissimi, altrimenti "
    "verrebbero annullati prima di finire. Default 180 s."
)


class ExperimentalFeaturesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Funzioni Sperimentali")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(PARALLEL_CONNECTIONS_MIN, PARALLEL_CONNECTIONS_MAX)
        self.connections_spin.setValue(load_connections_per_file())
        self.connections_spin.valueChanged.connect(save_connections_per_file)
        self._add_control_row(
            layout,
            "Connessioni per file:",
            self.connections_spin,
            "Connessioni per file",
            _CONN_DESC_SHORT,
            _CONN_DESC_LONG,
        )
        layout.addSpacing(8)

        self.segment_max_duration_spin = QSpinBox()
        self.segment_max_duration_spin.setRange(60, 1800)
        self.segment_max_duration_spin.setSingleStep(30)
        self.segment_max_duration_spin.setSuffix(" s")
        self.segment_max_duration_spin.setValue(load_segment_max_duration_s())
        self.segment_max_duration_spin.valueChanged.connect(save_segment_max_duration_s)
        self._add_control_row(
            layout,
            "Budget per pezzo (s):",
            self.segment_max_duration_spin,
            "Budget per pezzo",
            _BUDGET_DESC_SHORT,
            _BUDGET_DESC_LONG,
        )
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

    def _add_control_row(
        self,
        layout: QVBoxLayout,
        label_text: str,
        control,
        info_title: str,
        desc_short: str,
        desc_long: str,
    ) -> None:
        """Riga etichetta+controllo+icona info, seguita dalla descrizione breve."""
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        row.addWidget(control)

        info_btn = QToolButton()
        info_btn.setText("ⓘ")
        info_btn.setToolTip("Mostra la spiegazione estesa")
        info_btn.setAutoRaise(True)
        info_btn.clicked.connect(
            lambda: QMessageBox.information(self, info_title, desc_long)
        )
        row.addWidget(info_btn)
        row.addStretch(1)
        layout.addLayout(row)

        desc_lbl = QLabel(desc_short)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc_lbl)
