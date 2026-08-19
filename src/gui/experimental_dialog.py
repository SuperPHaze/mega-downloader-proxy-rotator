# Finestra "Funzioni Sperimentali": superficie separata dal popup
# "Impostazioni" stabile. Espone: selezione per velocita' (Leva B, con
# toggle e soglia configurabile), connessioni per file (Leva A) e budget
# per pezzo.
#
# i18n: dialogo creato su richiesta (nasce alla pressione del pulsante), quindi
# legge i testi con t("experimental.*") alla costruzione e non ha bisogno di
# retranslate(). Le descrizioni brevi/estese vivono nei dizionari, non piu' in
# costanti di modulo.
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
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
from src.gui.i18n import t
from src.gui.preferences import (
    load_connections_per_file,
    load_segment_max_duration_s,
    load_speed_selection_enabled,
    load_speed_selection_min_kbps,
    save_connections_per_file,
    save_segment_max_duration_s,
    save_speed_selection_enabled,
    save_speed_selection_min_kbps,
)

_FEEDBACK_URL = "https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues"


class ExperimentalFeaturesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("experimental.title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # --- Selezione per velocita' (Leva B) ---
        self.speed_sel_check = QCheckBox(t("experimental.speed_selection"))
        self.speed_sel_check.setChecked(load_speed_selection_enabled())
        self.speed_sel_check.toggled.connect(save_speed_selection_enabled)

        self.speed_sel_spin = QSpinBox()
        self.speed_sel_spin.setRange(100, 5000)
        self.speed_sel_spin.setSingleStep(50)
        self.speed_sel_spin.setSuffix(" KB/s")
        self.speed_sel_spin.setValue(load_speed_selection_min_kbps())
        self.speed_sel_spin.setEnabled(self.speed_sel_check.isChecked())
        self.speed_sel_spin.valueChanged.connect(save_speed_selection_min_kbps)
        self.speed_sel_check.toggled.connect(self.speed_sel_spin.setEnabled)

        self._add_speed_sel_row(layout)
        layout.addSpacing(8)

        # --- Connessioni per file (Leva A) ---
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(PARALLEL_CONNECTIONS_MIN, PARALLEL_CONNECTIONS_MAX)
        self.connections_spin.setValue(load_connections_per_file())
        self.connections_spin.valueChanged.connect(save_connections_per_file)
        self._add_control_row(
            layout,
            t("experimental.connections_label"),
            self.connections_spin,
            t("experimental.connections_title"),
            t("experimental.connections_desc_short"),
            t("experimental.connections_desc_long"),
        )
        layout.addSpacing(8)

        # --- Budget per pezzo ---
        self.segment_max_duration_spin = QSpinBox()
        self.segment_max_duration_spin.setRange(60, 1800)
        self.segment_max_duration_spin.setSingleStep(30)
        self.segment_max_duration_spin.setSuffix(" s")
        self.segment_max_duration_spin.setValue(load_segment_max_duration_s())
        self.segment_max_duration_spin.valueChanged.connect(save_segment_max_duration_s)
        self._add_control_row(
            layout,
            t("experimental.budget_label"),
            self.segment_max_duration_spin,
            t("experimental.budget_title"),
            t("experimental.budget_desc_short"),
            t("experimental.budget_desc_long"),
        )
        layout.addSpacing(8)

        feedback_lbl = QLabel(t("experimental.feedback", url=_FEEDBACK_URL))
        feedback_lbl.setWordWrap(True)
        feedback_lbl.setOpenExternalLinks(True)
        layout.addWidget(feedback_lbl)
        layout.addSpacing(8)

        close_btn = QPushButton(t("experimental.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _add_speed_sel_row(self, layout: QVBoxLayout) -> None:
        """Riga checkbox + spinbox velocità minima + icona info."""
        row = QHBoxLayout()
        row.addWidget(self.speed_sel_check)
        row.addWidget(self.speed_sel_spin)

        info_btn = QToolButton()
        info_btn.setText("ⓘ")
        info_btn.setToolTip(t("experimental.info_tooltip"))
        info_btn.setAutoRaise(True)
        info_btn.clicked.connect(
            lambda: QMessageBox.information(
                self,
                t("experimental.speed_selection"),
                t("experimental.speed_selection_desc_long"),
            )
        )
        row.addWidget(info_btn)
        row.addStretch(1)
        layout.addLayout(row)

        desc_lbl = QLabel(t("experimental.speed_selection_desc_short"))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc_lbl)

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
        info_btn.setToolTip(t("experimental.info_tooltip"))
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
