# Icona nell'area di notifica (accanto all'orologio): menu, avvisi a comparsa,
# suggerimento con lo stato della sessione, e la domanda «dove va la finestra
# quando la riduci a icona?».
#
# Perche' un modulo proprio e non altre righe in main_window.py: la finestra
# principale e' gia' il file piu' grande della GUI, e la parte che DECIDE
# (destinazione della riduzione, testo del suggerimento) si isola dalla parte
# che DISEGNA. Le due funzioni pure qui sotto — `resolve_minimize_action` e
# `tooltip_text` — sono provabili senza area di notifica e senza finestre,
# che e' esattamente cio' che manca alla piattaforma Qt offscreen dei test.
#
# i18n: nessun testo utente hard-coded. `TrayController` e' una superficie
# PERSISTENTE (vive quanto la finestra), quindi espone `retranslate()` ed e'
# nel fan-out di `MainWindow._on_language_changed`; il dialogo della domanda
# nasce su richiesta e non ne ha bisogno.
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QCheckBox, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from src.gui.format_helpers import fmt_speed
from src.gui.i18n import t

log = logging.getLogger(__name__)

# Destinazioni della riduzione a icona. Sono anche i valori persistiti in
# `preferences.json` (chiave `minimize_target`): non rinominarli senza una
# migrazione. `gui/preferences.py` li ripete come tupla letterale — non puo'
# importarli da qui (i18n importa preferences: sarebbe un ciclo) — e
# `tests/test_tray.py` verifica che i due elenchi coincidano.
MINIMIZE_ASK = "ask"
MINIMIZE_TRAY = "tray"
MINIMIZE_TASKBAR = "taskbar"
MINIMIZE_TARGETS = (MINIMIZE_ASK, MINIMIZE_TRAY, MINIMIZE_TASKBAR)

# Durata degli avvisi a comparsa. E' un suggerimento per il sistema: Windows
# applica comunque le proprie regole (e le rispetta poco).
NOTIFICATION_TIMEOUT_MS = 5000


def resolve_minimize_action(preference: str, tray_available: bool) -> str:
    """Cosa fare quando la finestra viene ridotta a icona. Funzione pura.

    Senza area di notifica (disattivata dall'utente, sessione senza shell) non
    c'e' nulla da chiedere e nessun posto dove andare: si ricade sulla barra
    delle applicazioni, cioe' il comportamento di sempre. Una preferenza
    sconosciuta (file scritto a mano, valore di una versione futura) vale
    «chiedi»: e' il ripiego che non decide al posto dell'utente.
    """
    if not tray_available:
        return MINIMIZE_TASKBAR
    pref = str(preference or "").strip().lower()
    return pref if pref in MINIMIZE_TARGETS else MINIMIZE_ASK


def tooltip_text(running: int, completed: int, total: int, speed_bps: float) -> str:
    """Testo del suggerimento dell'icona: stato sintetico della sessione.

    Pura rispetto a Qt (usa solo i dizionari): si prova senza area di notifica.
    """
    if total <= 0:
        return t("tray.tooltip_idle")
    if running <= 0:
        return t("tray.tooltip_done", done=completed, total=total)
    return t(
        "tray.tooltip_running",
        running=running,
        done=completed,
        total=total,
        speed=fmt_speed(speed_bps),
    )


def ask_minimize_target(parent: QWidget | None) -> tuple[str, bool]:
    """Chiede dove deve andare la finestra ridotta a icona.

    Ritorna `(destinazione, ricorda)`. Dialogo modale creato su richiesta:
    nasce, si legge e si chiude, quindi niente `retranslate()`.
    Chiudere la finestra senza scegliere (Esc, X) vale «barra delle
    applicazioni»: e' il comportamento di sempre, l'opzione che non sorprende.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(t("tray.ask_title"))
    box.setText(t("tray.ask_body"))
    tray_btn = box.addButton(t("tray.ask_tray"), QMessageBox.ButtonRole.AcceptRole)
    taskbar_btn = box.addButton(
        t("tray.ask_taskbar"), QMessageBox.ButtonRole.RejectRole
    )
    box.setDefaultButton(taskbar_btn)
    remember = QCheckBox(t("tray.ask_remember"))
    box.setCheckBox(remember)
    box.exec()
    chosen = MINIMIZE_TRAY if box.clickedButton() is tray_btn else MINIMIZE_TASKBAR
    return chosen, remember.isChecked()


class TrayController(QObject):
    """Icona nell'area di notifica: menu, doppio clic, avvisi, suggerimento.

    Se l'area di notifica non esiste (utente che l'ha disattivata, sessione
    remota, piattaforma Qt offscreen dei test) l'oggetto nasce comunque ma
    INERTE: `is_available()` torna False e ogni metodo e' un no-op. Chi lo usa
    non deve scrivere condizioni.
    """

    show_window_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._show_action: QAction | None = None
        self._quit_action: QAction | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info(
                "Area di notifica non disponibile: icona, avvisi e domanda "
                "sulla riduzione disattivati (riduzione normale come sempre)"
            )
            return
        self._tray = QSystemTrayIcon(icon, self)
        self._menu = QMenu()
        self._show_action = QAction(self._menu)
        self._show_action.triggered.connect(self.show_window_requested)
        self._quit_action = QAction(self._menu)
        self._quit_action.triggered.connect(self.quit_requested)
        self._menu.addAction(self._show_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self.retranslate()

    # ---- stato -------------------------------------------------------------

    def is_available(self) -> bool:
        """True se l'icona esiste davvero (area di notifica presente e non
        ancora smontata da `shutdown()`)."""
        return self._tray is not None

    def is_visible(self) -> bool:
        return self._tray is not None and self._tray.isVisible()

    # ---- ciclo di vita -----------------------------------------------------

    def show(self) -> None:
        if self._tray is not None:
            self._tray.show()

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    def shutdown(self) -> None:
        """Smonta l'icona PRIMA che l'applicazione esca.

        Un `QSystemTrayIcon` ancora registrato quando il processo muore lascia
        un fantasma nell'area di notifica finche' non ci si passa sopra col
        mouse. E' il gemello, per la shell di Windows, della regola sui thread
        attesi in `closeEvent`. Idempotente: chiamarlo due volte non fa nulla.
        """
        if self._tray is None:
            return
        tray, self._tray = self._tray, None
        tray.hide()
        tray.setContextMenu(None)
        self._menu = None
        self._show_action = None
        self._quit_action = None
        tray.deleteLater()

    # ---- uso ---------------------------------------------------------------

    def notify(self, title: str, body: str, *, warning: bool = False) -> None:
        """Avviso a comparsa. Silenzioso se l'icona non e' visibile o se il
        sistema non supporta i messaggi: un avviso senza icona non ha dove
        comparire."""
        if self._tray is None or not self._tray.isVisible():
            return
        if not QSystemTrayIcon.supportsMessages():
            return
        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if warning
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(title, body, icon, NOTIFICATION_TIMEOUT_MS)

    def set_tooltip(self, text: str) -> None:
        if self._tray is not None:
            self._tray.setToolTip(text)

    # ---- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive le voci del menu nella lingua corrente (gemello di
        `ControlsBar.retranslate`). Il suggerimento lo riscrive la finestra,
        che e' l'unica a conoscere lo stato della sessione."""
        if self._show_action is None or self._quit_action is None:
            return
        self._show_action.setText(t("tray.menu_show"))
        self._quit_action.setText(t("tray.menu_quit"))

    # ---- interni -----------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()
