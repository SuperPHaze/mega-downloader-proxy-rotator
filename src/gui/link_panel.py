# Pannello di input dei link Mega. Layout compatto su singola riga: tre
# bottoni (import file / paste dialog / svuota), checkbox duplicati, label
# contatore allineata a destra. L'API pubblica (`get_links`) e la lista
# interna `self._links` restano invariate; cambiano solo i metodi che la
# popolano.
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from src.core.download_history import extract_handle, load_history
from src.gui.paste_links_dialog import PasteLinksDialog
from src.gui.style import PALETTE


MEGA_PREFIX = "https://mega.nz/"


def _format_history_date(iso_ts: str | None) -> str:
    # "2026-06-10T14:30:00" -> "10/06/2026"; input malformato -> "?".
    if not iso_ts or len(iso_ts) < 10:
        return "?"
    date = iso_ts[:10]
    parts = date.split("-")
    if len(parts) != 3:
        return "?"
    return f"{parts[2]}/{parts[1]}/{parts[0]}"


def confirm_already_downloaded(
    links: list[str], parent: QWidget | None = None,
) -> list[str] | None:
    """Confronta i link con lo storico download (dedup per handle Mega, non
    per stringa URL) e, se alcuni risultano gia' scaricati, mostra UN dialog
    riepilogativo con la lista (data + nome file).

    Ritorna:
      - la lista filtrata (senza i gia' scaricati) se l'utente sceglie
        «Salta gia' scaricati» (default);
      - la lista intatta se sceglie «Scarica comunque»;
      - None se sceglie «Annulla» (il chiamante deve abortire l'operazione).

    NOTA: e' indipendente dalla checkbox "Consenti duplicati", che governa
    solo i duplicati dentro l'input corrente.
    """
    if not links:
        return list(links)
    try:
        history = load_history()
    except Exception:
        return list(links)
    if not history:
        return list(links)
    dup_entries: list[tuple[int, dict]] = []
    for i, url in enumerate(links):
        handle = extract_handle(url)
        if handle is not None and handle in history:
            dup_entries.append((i, history[handle]))
    if not dup_entries:
        return list(links)

    max_shown = 15
    lines = []
    for i, rec in dup_entries[:max_shown]:
        name = rec.get("file_name") or "?"
        date = _format_history_date(rec.get("completed_at"))
        lines.append(f"• {name} (scaricato il {date})")
    if len(dup_entries) > max_shown:
        lines.append(f"... e altri {len(dup_entries) - max_shown} link")

    box = QMessageBox(parent)
    box.setWindowTitle("Link gia' scaricati")
    box.setIcon(QMessageBox.Icon.Warning)
    n = len(dup_entries)
    box.setText(
        f"{n} link su {len(links)} risulta gia' scaricato in passato:"
        if n == 1
        else f"{n} link su {len(links)} risultano gia' scaricati in passato:"
    )
    box.setInformativeText("\n".join(lines))
    skip_btn = box.addButton(
        "Salta gia' scaricati", QMessageBox.ButtonRole.AcceptRole
    )
    anyway_btn = box.addButton(
        "Scarica comunque", QMessageBox.ButtonRole.DestructiveRole
    )
    box.addButton("Annulla", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(skip_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is anyway_btn:
        return list(links)
    if clicked is skip_btn:
        skip = {i for i, _ in dup_entries}
        return [u for i, u in enumerate(links) if i not in skip]
    return None


class LinkPanel(QWidget):
    # Emesso quando la lista interna cambia dimensione (import, paste, svuota).
    links_count_changed = pyqtSignal(int)

    # Scelta di design (Opzione A in task spec): rimosso il QListWidget di
    # anteprima. La label contatore + il pre-fill del dialog "Incolla link"
    # con la lista corrente sostituiscono funzionalmente la lista visibile;
    # i job in corso sono comunque mostrati da JobsPanel.

    def __init__(self) -> None:
        super().__init__()
        self._links: list[str] = []
        self._build_ui()
        self._refresh_counter()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.import_btn = QPushButton("Importa da file")
        self.import_btn.clicked.connect(self._on_import_file)
        layout.addWidget(self.import_btn)

        self.paste_btn = QPushButton("Aggiungi link")
        # Marca come azione primaria (vedi selettore QSS in style.py).
        self.paste_btn.setProperty("primary", "true")
        self.paste_btn.clicked.connect(self._on_paste)
        layout.addWidget(self.paste_btn)

        self.clear_btn = QPushButton("Svuota")
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_btn)

        # Permette di inserire piu' volte lo stesso URL: ogni copia diventa
        # un worker con file_id diverso e va in una cartella separata
        # (es. <hash>_0, <hash>_1).
        self.allow_dups = QCheckBox("Consenti duplicati")
        self.allow_dups.setToolTip(
            "Se attivo, lo stesso link puo' essere aggiunto piu' volte. "
            "Ogni copia viene scaricata in una cartella separata."
        )
        layout.addWidget(self.allow_dups)

        layout.addStretch(1)

        self.counter_lbl = QLabel("")
        self.counter_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.counter_lbl)

        # Altezza fissa contenuta: una sola riga di controlli.
        self.setMaximumHeight(40)

    # ---- azioni utente ----------------------------------------------------

    def _on_paste(self) -> None:
        # Apriamo il dialog pre-fillato con la lista corrente: l'utente vede
        # cosa c'e' gia' e puo' aggiungere/correggere. In conferma, sostituiamo
        # _links con accepted_links() (NON append, altrimenti raddoppieremmo
        # i link prefillati).
        dlg = PasteLinksDialog(
            existing_links=[],  # i duplicati intra-input li gestisce il dialog
            allow_duplicates=self.allow_dups.isChecked(),
            parent=self,
            prefill=list(self._links),
        )
        if dlg.exec() != PasteLinksDialog.DialogCode.Accepted:
            return
        new_list = dlg.accepted_links()
        # Alert storico: avvisa se qualche link e' gia' stato scaricato in
        # una sessione precedente (dedup per handle, vedi download_history).
        new_list = confirm_already_downloaded(new_list, self)
        if new_list is None:
            return  # utente ha annullato: lista corrente invariata
        if new_list == self._links:
            return
        self._links = new_list
        self._refresh_counter()
        self.links_count_changed.emit(len(self._links))

    def _on_import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importa link da file",
            "",
            "File di testo (*.txt);;Tutti i file (*)",
        )
        if not path:
            return
        try:
            valid, n_invalid, n_dups = self._parse_links_file(path)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Errore lettura file",
                f"Impossibile leggere il file:\n{exc}",
            )
            return

        # Alert storico sui soli link nuovi in import: stesso dialog del paste.
        valid = confirm_already_downloaded(valid, self)
        if valid is None:
            return  # utente ha annullato l'import

        added = 0
        for url in valid:
            self._links.append(url)
            added += 1

        if added == 0:
            QMessageBox.warning(
                self,
                "Nessun link importato",
                "Il file non contiene link Mega validi "
                f"(non validi: {n_invalid}, duplicati ignorati: {n_dups}).",
            )
            return

        QMessageBox.information(
            self,
            "Import completato",
            f"Import completato.\n"
            f"- Aggiunti: {added} link\n"
            f"- Non validi: {n_invalid}\n"
            f"- Duplicati ignorati: {n_dups}",
        )
        self._refresh_counter()
        self.links_count_changed.emit(len(self._links))

    def _on_clear(self) -> None:
        if not self._links:
            return
        self._links.clear()
        self._refresh_counter()
        self.links_count_changed.emit(0)

    # ---- parsing file -----------------------------------------------------

    def _parse_links_file(self, path: str) -> tuple[list[str], int, int]:
        # Ritorna (links_validi_nuovi, n_non_validi, n_duplicati).
        # Righe vuote ignorate. Righe che iniziano con '#' = commenti, saltate.
        # Encoding utf-8 con errori "replace" per non bloccarsi su file misti.
        allow_dups = self.allow_dups.isChecked()
        valid: list[str] = []
        invalid = 0
        dups = 0
        seen: set[str] = set(self._links)
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                if not url.startswith(MEGA_PREFIX):
                    invalid += 1
                    continue
                if not allow_dups and url in seen:
                    dups += 1
                    continue
                seen.add(url)
                valid.append(url)
        return valid, invalid, dups

    # ---- API pubblica -----------------------------------------------------

    def get_links(self) -> list[str]:
        return list(self._links)

    def open_paste_dialog(self) -> None:
        """Alias pubblico di _on_paste per le connessioni dalla ControlsBar."""
        self._on_paste()

    def set_running(self, running: bool) -> None:
        # Solo import e svuota vengono bloccati durante la sessione.
        # Il paste rimane sempre accessibile (nuovi link pronti per la
        # prossima sessione; la barra comandi li incoda tramite open_paste_dialog).
        self.import_btn.setEnabled(not running)
        self.clear_btn.setEnabled(not running)

    # ---- helper -----------------------------------------------------------

    def _refresh_counter(self) -> None:
        n = len(self._links)
        if n == 0:
            text = "nessun link"
        elif n == 1:
            text = "1 link pronto"
        else:
            text = f"{n} link pronti"
        self.counter_lbl.setText(text)
        self.counter_lbl.setStyleSheet(
            f"color: {PALETTE['text_dim']}; font-size: 9pt;"
        )
