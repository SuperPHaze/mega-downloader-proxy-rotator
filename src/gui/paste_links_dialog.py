# Dialog modale per incollare/editare la lista di link Mega.
# Pattern dialog-as-pure-input: ritorna i link al chiamante, non muta stato esterno.
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.style import PALETTE


MEGA_PREFIX = "https://mega.nz/"


class _NoEnterTextEdit(QTextEdit):
    # Subclasse per evitare che Enter chiuda il dialog: i link multi-riga
    # richiedono di poter inserire newline normalmente.
    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        # Niente da fare di speciale: il default di QTextEdit gia' inserisce
        # un newline su Enter. Mantenere la classe serve solo a impedire che
        # QDialog.keyPressEvent catturi Enter come "accept".
        super().keyPressEvent(e)


class PasteLinksDialog(QDialog):
    def __init__(
        self,
        existing_links: list[str],
        allow_duplicates: bool,
        parent: QWidget | None = None,
        prefill: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Incolla link Mega")
        self.setModal(True)
        self.resize(560, 360)

        self._existing = list(existing_links)
        self._allow_duplicates = allow_duplicates
        self._accepted: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Incolla link Mega (uno per riga):"))

        self.edit = _NoEnterTextEdit()
        self.edit.setPlaceholderText("https://mega.nz/...")
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.edit.setMinimumHeight(200)
        if prefill:
            self.edit.setPlainText("\n".join(prefill))
        layout.addWidget(self.edit, 1)

        # Riga statistiche live.
        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        self.lbl_valid = QLabel("Validi: 0")
        self.lbl_invalid = QLabel("Non validi: 0")
        self.lbl_dups = QLabel("Duplicati: 0")
        for lbl, color in (
            (self.lbl_valid, PALETTE["accent_ok"]),
            (self.lbl_invalid, PALETTE["accent_fail"]),
            (self.lbl_dups, PALETTE["accent_warn"]),
        ):
            lbl.setStyleSheet(f"color: {color}; font-size: 9pt;")
            stats_row.addWidget(lbl)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        # Bottoni: Annulla / Aggiungi N.
        self.buttons = QDialogButtonBox()
        self.cancel_btn = self.buttons.addButton(
            "Annulla", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.add_btn = self.buttons.addButton(
            "Aggiungi 0", QDialogButtonBox.ButtonRole.AcceptRole
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

        self.edit.textChanged.connect(self._recompute_stats)
        self._recompute_stats()

    # ---- parsing/statistiche ----------------------------------------------

    def _parse_current(self) -> tuple[list[str], int, int]:
        # Ritorna (validi_nuovi, n_invalidi, n_duplicati).
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
        # "Validi" totale = righe che matchano il prefisso, indipendentemente
        # dai duplicati (per dare all'utente il colpo d'occhio).
        valid_total = len(valid_new) + (dups if not self._allow_duplicates else 0)
        self.lbl_valid.setText(f"Validi: {valid_total}")
        self.lbl_invalid.setText(f"Non validi: {invalid}")
        self.lbl_dups.setText(f"Duplicati: {dups}")
        n_to_add = len(valid_new)
        self.add_btn.setText(f"Aggiungi {n_to_add}")
        self.add_btn.setEnabled(n_to_add > 0)

    # ---- accept -----------------------------------------------------------

    def _on_accept(self) -> None:
        valid_new, _, _ = self._parse_current()
        self._accepted = valid_new
        self.accept()

    def accepted_links(self) -> list[str]:
        # Lista filtrata: validi e (se non allow_duplicates) non duplicati.
        return list(self._accepted)
