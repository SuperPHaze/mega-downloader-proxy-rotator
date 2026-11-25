# Dialog modale per incollare/editare la lista di link Mega.
# Pattern dialog-as-pure-input: ritorna i link al chiamante, non muta stato esterno.
#
# i18n: dialogo creato su richiesta, legge i testi con t("paste.*") alla
# costruzione: nessun retranslate() necessario. I conteggi sono parametri
# nominati ({n}), non plurali: il testo non cambia forma.
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QKeyEvent, QKeySequence, QTextCursor, QTextOption
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.mega_links import is_folder_link
from src.gui.i18n import t
from src.gui.style import CURRENT_PALETTE


MEGA_PREFIX = "https://mega.nz/"

# Dove finiscono i link aggiunti a una sessione in corso. Valori stabili:
# li legge `MainWindow` e diventano il parametro `at_top` di
# `DownloadOrchestrator.add_jobs`.
POSITION_BOTTOM = "bottom"
POSITION_TOP = "top"


class _LinkEditor(QTextEdit):
    submit_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if enter and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PasteLinksDialog(QDialog):
    def __init__(
        self,
        existing_links: list[str],
        allow_duplicates: bool,
        parent: QWidget | None = None,
        prefill: list[str] | None = None,
        show_position: bool = False,
    ) -> None:
        super().__init__(parent)
        self._editing_list = bool(prefill)
        self.setWindowTitle(t("paste.list_title" if self._editing_list else "paste.title"))
        self.setModal(True)
        self.resize(620, 365)

        self._existing = list(existing_links)
        self._allow_duplicates = allow_duplicates
        self._accepted: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        instructions = QLabel(t("paste.list_hint" if self._editing_list else "paste.instructions"))
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.edit = _LinkEditor()
        self.edit.setObjectName("linkEditor")
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPointSizeF(max(13.0, font.pointSizeF()))
        self.edit.setFont(font)
        self.edit.document().setDefaultFont(font)
        self.edit.document().setDocumentMargin(10)
        self.edit.setAcceptRichText(False)
        self.edit.setAccessibleName(instructions.text())
        instructions.setBuddy(self.edit)
        self.edit.setFocus()
        self.edit.setPlaceholderText("https://mega.nz/...")
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.edit.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.edit.setMinimumHeight(130)
        if prefill:
            self.edit.setPlainText("\n".join(prefill) + "\n")
            self.edit.moveCursor(QTextCursor.MoveOperation.End)
        layout.addWidget(self.edit, 1)

        # Riga statistiche live.
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        self.lbl_valid = QLabel(t("paste.valid", n=0))
        self.lbl_folders = QLabel(t("paste.folders", n=0))
        self.lbl_invalid = QLabel(t("paste.invalid", n=0))
        self.lbl_dups = QLabel(t("paste.duplicates", n=0))
        # La cartella conta come UN link qui: quanti file contenga si sa solo
        # dopo l'espansione (che fa rete e avviene all'Avvia).
        self.lbl_folders.setToolTip(t("paste.folders_tooltip"))
        for lbl, color in (
            (self.lbl_valid, CURRENT_PALETTE["text_dim"]),
            (self.lbl_folders, CURRENT_PALETTE["text_dim"]),
            (self.lbl_invalid, CURRENT_PALETTE["accent_fail"]),
            (self.lbl_dups, CURRENT_PALETTE["accent_warn"]),
        ):
            lbl.setStyleSheet(f"color: {color};")
            stats_row.addWidget(lbl)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        # Dove mettere i link, chiesto solo quando c'e' una sessione in corso
        # a cui accodarli: fuori sessione la coda non esiste ancora e la
        # domanda non avrebbe senso. Sta QUI e non in una seconda finestra
        # perche' e' la stessa decisione dell'aggiunta, non una successiva.
        self.pos_bottom: QRadioButton | None = None
        self.pos_top: QRadioButton | None = None
        if show_position:
            pos_lbl = QLabel(t("paste.position_label"))
            layout.addWidget(pos_lbl)
            pos_row = QHBoxLayout()
            pos_row.setSpacing(14)
            self.pos_bottom = QRadioButton(t("paste.position_bottom"))
            self.pos_bottom.setToolTip(t("paste.position_bottom_tooltip"))
            self.pos_bottom.setChecked(True)
            self.pos_top = QRadioButton(t("paste.position_top"))
            self.pos_top.setToolTip(t("paste.position_top_tooltip"))
            pos_row.addWidget(self.pos_bottom)
            pos_row.addWidget(self.pos_top)
            pos_row.addStretch(1)
            layout.addLayout(pos_row)

        # Bottoni: Annulla / Aggiungi N.
        self.buttons = QDialogButtonBox()
        self.cancel_btn = self.buttons.addButton(
            t("paste.cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.add_btn = self.buttons.addButton(
            t("paste.add_button", n=0), QDialogButtonBox.ButtonRole.AcceptRole
        )
        # Marca il bottone primario per il selettore QSS dedicato.
        self.add_btn.setProperty("primary", "true")
        self.add_btn.setDefault(False)
        self.add_btn.setAutoDefault(False)
        self.cancel_btn.setDefault(False)
        self.cancel_btn.setAutoDefault(False)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.add_btn.setToolTip(QKeySequence("Ctrl+Return").toString(QKeySequence.SequenceFormat.NativeText))
        self.edit.submit_requested.connect(self.add_btn.click)
        self.edit.textChanged.connect(self._recompute_stats)
        self._recompute_stats()

    # ---- parsing/statistiche ----------------------------------------------

    def _parse_current(self) -> tuple[list[str], int, int]:
        # Ritorna (validi_nuovi, n_invalidi, n_duplicati).
        # I link a cartella passano di qui come qualunque altro link Mega:
        # l'espansione in singoli file avviene all'avvio (richiede rete).
        raw = self.edit.toPlainText().splitlines()
        seen_in_input: set[str] = set()
        valid_new: list[str] = []
        invalid = 0
        dups = 0
        for line in raw:
            url = line.strip()
            if not url:
                continue
            if not url.startswith(MEGA_PREFIX):
                invalid += 1
                continue
            # Duplicato: gia' presente nei link esistenti del LinkPanel,
            # oppure ripetuto piu' volte nello stesso input.
            is_dup_existing = url in self._existing
            is_dup_input = url in seen_in_input
            if not self._allow_duplicates and (is_dup_existing or is_dup_input):
                dups += 1
                continue
            seen_in_input.add(url)
            valid_new.append(url)
        return valid_new, invalid, dups

    def _recompute_stats(self) -> None:
        valid_new, invalid, dups = self._parse_current()
        n_folders = sum(1 for u in valid_new if is_folder_link(u))
        self.lbl_folders.setText(t("paste.folders", n=n_folders))
        # "Validi" totale = righe che matchano il prefisso, indipendentemente
        # dai duplicati (per dare all'utente il colpo d'occhio).
        valid_total = len(valid_new) + (dups if not self._allow_duplicates else 0)
        self.lbl_valid.setText(t("paste.valid", n=valid_total))
        self.lbl_invalid.setText(t("paste.invalid", n=invalid))
        self.lbl_dups.setText(t("paste.duplicates", n=dups))
        for label, count in ((self.lbl_folders, n_folders), (self.lbl_invalid, invalid), (self.lbl_dups, dups)):
            label.setVisible(count > 0)
        n_to_add = len(valid_new)
        if self._editing_list:
            self.add_btn.setText(t("paste.save_list"))
            self.add_btn.setEnabled(bool(valid_new) or not self.edit.toPlainText().strip())
        else:
            self.add_btn.setText(t("paste.add_button", n=n_to_add))
            self.add_btn.setEnabled(n_to_add > 0)

    # ---- accept -----------------------------------------------------------

    def _on_accept(self) -> None:
        valid_new, _, _ = self._parse_current()
        self._accepted = valid_new
        self.accept()

    def accepted_links(self) -> list[str]:
        # Lista filtrata: validi e (se non allow_duplicates) non duplicati.
        return list(self._accepted)

    def selected_position(self) -> str:
        """Dove mettere i link: `POSITION_TOP` o `POSITION_BOTTOM`.

        Senza il selettore (dialogo aperto fuori sessione) vale sempre
        `POSITION_BOTTOM`: e' l'ordine di inserimento di sempre.
        """
        if self.pos_top is not None and self.pos_top.isChecked():
            return POSITION_TOP
        return POSITION_BOTTOM
