# Finestra "Manutenzione": azzeramento dei dati che il programma lascia su
# disco (storico, stato della sessione, cartella dei download, log, cache dei
# proxy).
#
# Qui si cancellano DATI DELL'UTENTE, quindi ogni scelta va nella direzione
# piu' prudente e le tre regole sono vincolanti (vedi rules/gui.md):
#   1. nessuna casella e' spuntata all'apertura;
#   2. prima di cancellare si elenca riga per riga cio' che sparira', con
#      dimensioni, e il pulsante che conferma NON e' quello predefinito;
#   3. dopo l'operazione resta un resoconto nella finestra e una riga nel log.
#
# La misura e la cancellazione vivono in `core/maintenance.py`, che non sa
# nulla dell'interfaccia. L'unica voce che non passa di li' e' la cache dei
# proxy: sta in `src/proxy/` e `core/` non puo' importarla, quindi la si
# azzera qui chiamando `delete_proxy_cache()` — la stessa funzione del
# pulsante nella zona proxy, non una seconda copia della logica.
#
# i18n: dialogo modale creato su richiesta, quindi legge i testi con
# `t("maintenance.*")` alla costruzione e non ha bisogno di `retranslate()`.
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core import maintenance
from src.core.maintenance import (
    ITEM_DOWNLOADS,
    ITEM_HISTORY,
    ITEM_LOGS,
    ITEM_PROXY_CACHE,
    ITEM_SESSION,
    SESSION_LOCKED_ITEMS,
    ItemResult,
)
from src.gui import style as _style
from src.gui.format_helpers import fmt_bytes
from src.gui.i18n import t, tn
from src.proxy.proxy_cache import cache_path, delete_proxy_cache

log = logging.getLogger(__name__)

# Ordine di presentazione: dalla voce meno distruttiva alla piu' distruttiva.
# La cache dei proxy chiude la lista perche' e' l'unica che si rifa' da sola al
# prossimo avvio (costa solo tempo, non dati).
_ROWS = (
    ITEM_HISTORY,
    ITEM_SESSION,
    ITEM_DOWNLOADS,
    ITEM_LOGS,
    ITEM_PROXY_CACHE,
)


class MaintenanceDialog(QDialog):
    """Finestra di manutenzione, modale.

    `session_running` arriva da chi la apre (la finestra principale): le voci
    di `SESSION_LOCKED_ITEMS` restano disattivate e la finestra dice perche'.
    `output_root` e' la cartella di download configurata ("" / None = quella
    predefinita del programma).
    """

    def __init__(
        self,
        parent=None,
        *,
        session_running: bool = False,
        output_root: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("maintenance.title"))
        self.setMinimumWidth(520)
        self._session_running = bool(session_running)
        self._output_root = output_root
        self._checks: dict[str, QCheckBox] = {}
        self._details: dict[str, QLabel] = {}
        self._surveys: dict[str, maintenance.ItemSurvey] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        intro = QLabel(t("maintenance.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        if self._session_running:
            locked = QLabel(t("maintenance.locked_note"))
            locked.setWordWrap(True)
            locked.setStyleSheet(
                f"color: {_style.CURRENT_PALETTE['accent_warn']};"
            )
            layout.addWidget(locked)

        layout.addSpacing(4)
        for key in _ROWS:
            layout.addWidget(self._build_row(key))

        note = QLabel(t("maintenance.preferences_note"))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_style.CURRENT_PALETTE['text_dim']};")
        layout.addSpacing(4)
        layout.addWidget(note)

        # Resoconto dell'ultima operazione: vive NELLA finestra (oltre che nel
        # log), cosi' chi ha appena cancellato vede cosa e' sparito senza
        # doversi fidare.
        self._report = QLabel("")
        self._report.setWordWrap(True)
        self._report.setVisible(False)
        layout.addWidget(self._report)

        layout.addLayout(self._build_buttons())

        self._refresh_surveys()

    # ---- costruzione -------------------------------------------------------

    def _build_row(self, key: str) -> QWidget:
        container = QFrame()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 2, 0, 2)
        box.setSpacing(1)

        check = QCheckBox(t(f"maintenance.item_{key}"))
        check.setChecked(False)          # regola 1: mai nulla di pre-selezionato
        check.toggled.connect(self._refresh_confirm_button)
        self._checks[key] = check
        box.addWidget(check)

        detail = QLabel("")
        detail.setStyleSheet(f"color: {_style.CURRENT_PALETTE['text_dim']};")
        detail.setContentsMargins(22, 0, 0, 0)
        self._details[key] = detail
        box.addWidget(detail)

        warning = QLabel(t(f"maintenance.warn_{key}"))
        warning.setWordWrap(True)
        warning.setContentsMargins(22, 0, 0, 0)
        warning.setStyleSheet(f"color: {_style.CURRENT_PALETTE['text_dim']};")
        box.addWidget(warning)

        # Abilitazione e stile della riga li decide `_apply_row_state()`, che
        # gira anche DOPO ogni azzeramento: una voce appena svuotata non deve
        # restare selezionabile.
        return container

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton(t("maintenance.close"))
        self.cancel_btn.setDefault(True)      # regola 2: il default e' uscire
        self.cancel_btn.clicked.connect(self.reject)
        row.addWidget(self.cancel_btn)

        self.confirm_btn = QPushButton(t("maintenance.confirm_button"))
        self.confirm_btn.setProperty("danger", "true")
        self.confirm_btn.setAutoDefault(False)
        self.confirm_btn.setDefault(False)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._on_confirm)
        row.addWidget(self.confirm_btn)
        return row

    # ---- misura ------------------------------------------------------------

    def _refresh_surveys(self) -> None:
        """Rimisura tutto e riscrive le righe di dettaglio.

        Si chiama all'apertura e dopo ogni azzeramento: i numeri mostrati sono
        SEMPRE quelli appena letti dal disco, mai una stima."""
        self._surveys = maintenance.survey_all(output_root=self._output_root)
        self._surveys[ITEM_PROXY_CACHE] = maintenance.survey_paths(
            ITEM_PROXY_CACHE, [cache_path()]
        )
        for key in self._details:
            self._apply_row_state(key)
        self._refresh_confirm_button()

    def is_locked(self, key: str) -> bool:
        """Voce rifiutata perche' c'e' una sessione in corso."""
        return self._session_running and key in SESSION_LOCKED_ITEMS

    def _apply_row_state(self, key: str) -> None:
        """Riga di dettaglio, abilitazione e colore di UNA voce.

        Una voce si puo' spuntare solo se c'e' davvero qualcosa da cancellare
        e nessuna sessione la sta usando. Il perche' resta scritto: «niente da
        cancellare» oppure la clausola di blocco — il solo grigio non basta,
        e con il foglio di stile del progetto una casella disattivata non si
        distingue nemmeno (`QCheckBox { color: text }` vale sempre)."""
        detail = self._detail_text(key)
        locked = self.is_locked(key)
        if locked:
            detail = t("maintenance.detail_locked", detail=detail)
        self._details[key].setText(detail)

        survey = self._surveys.get(key)
        selectable = not locked and survey is not None and not survey.is_empty
        check = self._checks[key]
        if not selectable:
            check.setChecked(False)
        check.setEnabled(selectable)
        check.setToolTip(t("maintenance.locked_tooltip") if locked else "")
        check.setStyleSheet(
            "" if selectable
            else f"QCheckBox {{ color: {_style.CURRENT_PALETTE['text_dim']}; }}"
        )

    def _detail_text(self, key: str) -> str:
        survey = self._surveys.get(key)
        if survey is None or survey.is_empty:
            return t("maintenance.detail_empty")
        size = fmt_bytes(survey.total_bytes)
        if key == ITEM_HISTORY:
            return tn("maintenance.detail_history", survey.count, size=size)
        if key == ITEM_SESSION:
            return tn("maintenance.detail_session", survey.count, size=size)
        if key == ITEM_DOWNLOADS:
            return tn(
                "maintenance.detail_downloads",
                survey.count,
                parts=tn("maintenance.count_parts", survey.extra_count),
                size=size,
            )
        if key == ITEM_LOGS:
            return tn("maintenance.detail_logs", survey.count, size=size)
        return size

    def _selected_keys(self) -> list[str]:
        return [
            key for key in _ROWS
            if self._checks[key].isChecked() and self._checks[key].isEnabled()
        ]

    def _refresh_confirm_button(self) -> None:
        self.confirm_btn.setEnabled(bool(self._selected_keys()))

    # ---- conferma ed esecuzione -------------------------------------------

    def confirm_lines(self, keys: list[str]) -> list[str]:
        """Le righe dell'elenco mostrato prima di cancellare.

        Pubblica perche' e' il punto che il test controlla: cio' che l'utente
        legge deve coincidere con cio' che poi sparisce."""
        lines: list[str] = []
        for key in keys:
            survey = self._surveys.get(key)
            if survey is None:
                continue
            lines.append(
                t(
                    "maintenance.confirm_line",
                    item=t(f"maintenance.item_{key}"),
                    detail=self._detail_text(key),
                )
            )
            # Le voci con pochi file si mostrano per nome: e' l'elenco esatto
            # di cio' che sparisce. La cartella dei download no — sarebbero
            # migliaia di righe: si mostra la cartella e i conteggi.
            if key == ITEM_DOWNLOADS:
                if survey.root is not None:
                    lines.append("    " + str(survey.root))
                continue
            for path in survey.paths:
                lines.append(
                    "    " + t(
                        "maintenance.confirm_file",
                        name=path.name,
                        size=fmt_bytes(_safe_size(path)),
                    )
                )
        return lines

    def _on_confirm(self) -> None:
        keys = self._selected_keys()
        if not keys:
            return
        body = "\n".join(
            [t("maintenance.confirm_intro"), ""] + self.confirm_lines(keys)
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(t("maintenance.confirm_title"))
        box.setText(body)
        yes = box.addButton(
            t("maintenance.confirm_button"), QMessageBox.ButtonRole.DestructiveRole
        )
        no = box.addButton(
            t("maintenance.cancel_button"), QMessageBox.ButtonRole.RejectRole
        )
        # Regola 2: il predefinito e' ANNULLA. Un invio distratto non deve
        # cancellare niente.
        box.setDefaultButton(no)
        box.setEscapeButton(no)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self._run(keys)

    def _run(self, keys: list[str]) -> None:
        core_keys = [k for k in keys if k != ITEM_PROXY_CACHE]
        results = maintenance.clear_items(core_keys, output_root=self._output_root)
        if ITEM_PROXY_CACHE in keys:
            results.append(self._clear_proxy_cache())
        self._show_report(results)
        self._uncheck_all()
        self._refresh_surveys()

    def _clear_proxy_cache(self) -> ItemResult:
        """Azzeramento della cache dei proxy: chiama la funzione che esiste
        gia' (`delete_proxy_cache`), non una copia della sua logica."""
        size = _safe_size(cache_path())
        try:
            deleted = delete_proxy_cache()
        except OSError as exc:
            log.warning("[manutenzione] cache proxy non cancellabile: %s", exc)
            return ItemResult(
                key=ITEM_PROXY_CACHE, ok=False, error=str(exc), failures=(str(exc),)
            )
        return ItemResult(
            key=ITEM_PROXY_CACHE,
            ok=True,
            freed_bytes=size if deleted else 0,
            removed=1 if deleted else 0,
        )

    def _uncheck_all(self) -> None:
        for check in self._checks.values():
            check.setChecked(False)

    def _show_report(self, results: list[ItemResult]) -> None:
        """Resoconto nella finestra + riga nel log (regola 3)."""
        lines: list[str] = []
        freed = 0
        failed: list[ItemResult] = []
        for result in results:
            name = t(f"maintenance.item_{result.key}")
            if result.ok:
                freed += result.freed_bytes
                lines.append(
                    t(
                        "maintenance.report_ok",
                        item=name,
                        size=fmt_bytes(result.freed_bytes),
                    )
                )
            else:
                failed.append(result)
                lines.append(
                    t("maintenance.report_failed", item=name, error=result.error or "")
                )
        lines.append(t("maintenance.report_total", size=fmt_bytes(freed)))
        self._report.setText("\n".join(lines))
        self._report.setStyleSheet(
            "color: "
            + _style.CURRENT_PALETTE["accent_warn" if failed else "accent_ok"]
            + ";"
        )
        self._report.setVisible(True)

        log.info(
            "[manutenzione] azzerate %d voci (%s), %d byte liberati, %d fallite",
            len(results),
            ", ".join(r.key for r in results),
            freed,
            len(failed),
            extra={
                "event_type": "maintenance_done",
                "items": [r.key for r in results],
                "freed_bytes": freed,
                "failed": [r.key for r in failed],
            },
        )
        # Un fallimento non deve restare in una riga che si puo' non vedere.
        if failed:
            QMessageBox.warning(
                self,
                t("maintenance.report_failed_title"),
                "\n".join(
                    t(
                        "maintenance.report_failed",
                        item=t(f"maintenance.item_{r.key}"),
                        error=r.error or "",
                    )
                    for r in failed
                ),
            )


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
