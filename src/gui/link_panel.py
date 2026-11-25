# Preparazione della coda: anteprima dei link, modifica della lista e import.
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.download_history import extract_handle, load_history
from src.gui.format_helpers import link_caption
from src.gui.i18n import t, tn
from src.gui.paste_links_dialog import PasteLinksDialog


MEGA_PREFIX = "https://mega.nz/"


def _format_history_date(iso_ts: str | None) -> str:
    # "2026-06-10T14:30:00" -> "10/06/2026"; input malformato -> "?".
    if not isinstance(iso_ts, str) or len(iso_ts) < 10:
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
        lines.append(t("link_panel.history_entry", name=name, date=date))
    if len(dup_entries) > max_shown:
        rest = len(dup_entries) - max_shown
        lines.append(tn("link_panel.history_more", rest))

    box = QMessageBox(parent)
    box.setWindowTitle(t("link_panel.history_title"))
    box.setIcon(QMessageBox.Icon.Warning)
    n = len(dup_entries)
    box.setText(tn("link_panel.history_text", n, total=len(links)))
    box.setInformativeText("\n".join(lines))
    skip_btn = box.addButton(
        t("link_panel.history_skip"), QMessageBox.ButtonRole.AcceptRole
    )
    anyway_btn = box.addButton(
        t("link_panel.history_anyway"), QMessageBox.ButtonRole.DestructiveRole
    )
    box.addButton(t("link_panel.history_cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(skip_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is anyway_btn:
        return list(links)
    if clicked is skip_btn:
        skip = {i for i, _ in dup_entries}
        return [u for i, u in enumerate(links) if i not in skip]
    return None


def dedup_key(url: str) -> str:
    """Chiave con cui due link si considerano lo STESSO file.

    L'handle Mega quando c'e' (lo stesso file incollato in due forme di URL e'
    un file solo, ed e' lo stesso criterio dello storico), altrimenti l'URL
    esatto — che copre i link a cartella non ancora espansi, dove un handle di
    file da confrontare non esiste.
    """
    handle = extract_handle(url)
    return handle if handle is not None else url.strip()


def find_session_duplicates(
    links: list[str], session_keys: dict[str, str],
) -> list[tuple[int, str]]:
    """Quali dei `links` sono gia' presenti nella sessione corrente.

    `session_keys` mappa `dedup_key(url)` -> descrizione gia' RESA del job che
    lo occupa (in coda / in download / concluso): la funzione non traduce e non
    tocca Qt, cosi' resta verificabile da sola.

    Ritorna le coppie (indice nel nuovo elenco, descrizione), in ordine.
    """
    found: list[tuple[int, str]] = []
    for i, url in enumerate(links):
        state = session_keys.get(dedup_key(url))
        if state is not None:
            found.append((i, state))
    return found


def confirm_session_duplicates(
    links: list[str],
    session_keys: dict[str, str],
    parent: QWidget | None = None,
) -> list[str] | None:
    """Gemello di `confirm_already_downloaded` per la sessione IN CORSO: elenca
    i link gia' in coda, in download o gia' conclusi e chiede conferma prima di
    aggiungerli comunque.

    Stesso contratto di ritorno: lista filtrata se si saltano i doppioni, lista
    intatta se si aggiungono comunque, None se si annulla.
    """
    if not links:
        return list(links)
    dups = find_session_duplicates(links, session_keys)
    if not dups:
        return list(links)

    max_shown = 15
    lines = [
        t("link_panel.session_dup_entry", url=links[i], state=state)
        for i, state in dups[:max_shown]
    ]
    if len(dups) > max_shown:
        lines.append(tn("link_panel.history_more", len(dups) - max_shown))

    box = QMessageBox(parent)
    box.setWindowTitle(t("link_panel.session_dup_title"))
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(tn("link_panel.session_dup_text", len(dups), total=len(links)))
    box.setInformativeText("\n".join(lines))
    skip_btn = box.addButton(
        t("link_panel.session_dup_skip"), QMessageBox.ButtonRole.AcceptRole
    )
    anyway_btn = box.addButton(
        t("link_panel.session_dup_anyway"), QMessageBox.ButtonRole.DestructiveRole
    )
    box.addButton(t("link_panel.history_cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(skip_btn)
    box.exec()
    clicked = box.clickedButton()
    if clicked is anyway_btn:
        return list(links)
    if clicked is skip_btn:
        skip = {i for i, _ in dups}
        return [u for i, u in enumerate(links) if i not in skip]
    return None


class LinkPanel(QWidget):
    # Emesso quando la lista interna cambia dimensione (import, paste, svuota).
    links_count_changed = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self._links: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("queueSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.counter_lbl = QLabel()
        self.counter_lbl.setObjectName("sectionTitle")
        layout.addWidget(self.counter_lbl)
        self.preview = QListWidget()
        self.preview.setAlternatingRowColors(True)
        self.preview.setUniformItemSizes(True)
        layout.addWidget(self.preview, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        layout.addLayout(actions)
        self.paste_btn = QPushButton()
        self.paste_btn.clicked.connect(self._on_paste)
        actions.addWidget(self.paste_btn)

        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self._on_import_file)
        actions.addWidget(self.import_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._on_clear)
        actions.addWidget(self.clear_btn)
        actions.addStretch()

        # Ogni copia occupa una riga della coda e ha un nome disponibile su disco.
        self.allow_dups = QCheckBox()
        actions.addWidget(self.allow_dups)

        self.retranslate()

    # ---- azioni utente ----------------------------------------------------

    def _on_paste(self) -> None:
        # Apriamo il dialog pre-fillato con la lista corrente: l'utente vede
        # cosa c'e' gia' e puo' aggiungere/correggere. In conferma, sostituiamo
        # _links con accepted_links() (NON append, altrimenti raddoppieremmo
        # i link prefillati).
        dlg = PasteLinksDialog(
            existing_links=[],  # i duplicati intra-input li gestisce il dialog
            allow_duplicates=self.allow_dups.isChecked(),
            parent=self.window(),
            prefill=list(self._links),
        )
        if dlg.exec() != PasteLinksDialog.DialogCode.Accepted:
            return
        new_list = dlg.accepted_links()
        if new_list == self._links:
            return
        # Alert storico: avvisa se qualche link e' gia' stato scaricato in
        # una sessione precedente (dedup per handle, vedi download_history).
        # La conferma riguarda solo le nuove occorrenze. Saltare un doppione
        # non deve rimuovere dalla bozza un file già accettato in precedenza.
        remaining = Counter(self._links)
        new_indices = []
        for index, url in enumerate(new_list):
            if remaining[url]:
                remaining[url] -= 1
            else:
                new_indices.append(index)
        additions = [new_list[i] for i in new_indices]
        accepted = confirm_already_downloaded(additions, self.window())
        if accepted is None:
            return
        accepted_urls = set(accepted)
        skipped = {i for i in new_indices if new_list[i] not in accepted_urls}
        self.set_links([url for i, url in enumerate(new_list) if i not in skipped])

    def _on_import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window(),
            t("link_panel.import_dialog_title"),
            "",
            t("link_panel.import_dialog_filter"),
        )
        if not path:
            return
        try:
            valid, n_invalid, n_dups = self._parse_links_file(path)
        except OSError as exc:
            QMessageBox.critical(
                self.window(),
                t("link_panel.read_error_title"),
                t("link_panel.read_error_body", error=exc),
            )
            return

        # Alert storico sui soli link nuovi in import: stesso dialog del paste.
        valid = confirm_already_downloaded(valid, self.window())
        if valid is None:
            return  # utente ha annullato l'import

        if not valid:
            QMessageBox.warning(
                self.window(),
                t("link_panel.nothing_imported_title"),
                t(
                    "link_panel.nothing_imported_body",
                    invalid=n_invalid,
                    dups=n_dups,
                ),
            )
            return

        self.set_links(self._links + valid)

        if n_invalid or n_dups:
            QMessageBox.information(
                self.window(),
                t("link_panel.import_done_title"),
                tn(
                    "link_panel.import_done_body",
                    len(valid),
                    invalid=n_invalid,
                    dups=n_dups,
                ),
            )

    def _on_clear(self) -> None:
        if not self._links:
            return
        self.set_links([])

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

    def set_links(self, links: list[str]) -> None:
        """Rimpiazza la lista link (usato dal ripristino sessione all'avvio)."""
        self._links = list(links)
        self.preview.clear()
        self.preview.addItems([link_caption(url) for url in links])
        self._refresh_counter()
        self.links_count_changed.emit(len(self._links))

    def open_paste_dialog(self) -> None:
        """Alias pubblico di _on_paste per le connessioni dalla ControlsBar."""
        self._on_paste()

    def set_running(self, running: bool) -> None:
        # Solo import e svuota vengono bloccati durante la sessione: riempire
        # la lista del PROSSIMO avvio mentre si scarica confonderebbe.
        # L'aggiunta resta invece sempre accessibile — a sessione viva la
        # barra comandi non passa piu' di qui ma accoda a caldo
        # (`MainWindow._on_add_links_requested`).
        self.import_btn.setEnabled(not running)
        self.clear_btn.setEnabled(not running)

    # ---- lingua -----------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive il cromo del pannello nella lingua corrente.

        Il contatore passa da `_refresh_counter` perche' il suo testo dipende
        dal numero di link, non solo dalla lingua.
        """
        self.preview.setAccessibleName(t("workspace.queue_title"))
        self.import_btn.setText(t("link_panel.import"))
        self.paste_btn.setText(t("link_panel.edit"))
        self.clear_btn.setText(t("link_panel.clear"))
        self.allow_dups.setText(t("link_panel.allow_duplicates"))
        self.allow_dups.setToolTip(t("link_panel.allow_duplicates_tooltip"))
        self._refresh_counter()

    # ---- helper -----------------------------------------------------------

    def _refresh_counter(self) -> None:
        n = len(self._links)
        # La scelta singolare/plurale la fa `tn()`: il caso 0 resta a
        # parte perche' non e' un plurale ma un testo diverso.
        text = (
            t("link_panel.counter_empty") if n == 0
            else tn("link_panel.counter", n)
        )
        self.counter_lbl.setText(text)
