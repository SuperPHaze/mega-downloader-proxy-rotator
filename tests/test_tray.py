# Test dell'area di notifica: la parte DECISIONALE (dove va la finestra
# ridotta a icona, che cosa dice il suggerimento) e il dialogo della domanda.
#
# Cosa NON si prova qui e perche': la piattaforma Qt usata dalla suite
# (offscreen) non ha un'area di notifica — `QSystemTrayIcon.isSystemTrayAvailable()`
# e' False — quindi l'icona vera, il suo menu e gli avvisi a comparsa non
# esistono. I test che li richiedono si SALTANO dichiarandolo (`pytest.skip`
# con il motivo): farli passare per finto direbbe che funzionano senza averli
# mai eseguiti. Su piattaforma reale (`QT_QPA_PLATFORM=windows`) girano
# davvero — ed e' li' che sono stati eseguiti a mano prima di consegnarli.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from src.gui import preferences
from src.gui.i18n import t
from src.gui.main_window import MainWindow
from src.gui.tray import (
    MINIMIZE_ASK,
    MINIMIZE_TARGETS,
    MINIMIZE_TASKBAR,
    MINIMIZE_TRAY,
    TrayController,
    ask_minimize_target,
    resolve_minimize_action,
    tooltip_text,
)

_MOTIVO_SKIP = (
    "area di notifica assente sulla piattaforma Qt dei test (offscreen): "
    "l'icona vera, il suo menu e gli avvisi non sono verificabili qui"
)


def _area_di_notifica_disponibile() -> bool:
    """Va chiesto DENTRO un test, mai all'import: senza QApplication viva la
    domanda fa cadere il processo (violazione di accesso, non un'eccezione).
    La fixture `qt_app` di conftest garantisce l'istanza."""
    return QSystemTrayIcon.isSystemTrayAvailable()


# ---- 1. decisione: dove va la finestra ridotta a icona ----------------------

def test_resolve_senza_area_di_notifica_resta_nella_barra():
    """Senza area di notifica non c'e' nulla da chiedere e nessun posto dove
    andare: si ricade sul comportamento di sempre, anche se la preferenza
    dice altro (es. un profilo portato da un'altra macchina)."""
    for pref in MINIMIZE_TARGETS:
        assert resolve_minimize_action(pref, tray_available=False) == MINIMIZE_TASKBAR


def test_resolve_con_area_di_notifica_rispetta_la_preferenza():
    assert resolve_minimize_action(MINIMIZE_ASK, True) == MINIMIZE_ASK
    assert resolve_minimize_action(MINIMIZE_TRAY, True) == MINIMIZE_TRAY
    assert resolve_minimize_action(MINIMIZE_TASKBAR, True) == MINIMIZE_TASKBAR


def test_resolve_preferenza_ignota_torna_a_chiedere():
    """Un valore scritto a mano o di una versione futura non deve decidere al
    posto dell'utente: si torna a chiedere."""
    for ignota in ("", "   ", None, "TRAY_2", 3):
        assert resolve_minimize_action(ignota, True) == MINIMIZE_ASK


# ---- 2. preferenza: giro completo di salvataggio e rilettura ----------------

def test_preferenza_riduzione_default_e_chiedi(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    assert preferences.load_minimize_target() == MINIMIZE_ASK


def test_preferenza_riduzione_giro_completo(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    for valore in MINIMIZE_TARGETS:
        preferences.save_minimize_target(valore)
        assert preferences.load_minimize_target() == valore


def test_preferenza_riduzione_valore_ignoto_vale_chiedi(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target("area_magica")
    assert preferences.load_minimize_target() == MINIMIZE_ASK


def test_preferenza_riduzione_non_sovrascrive_le_altre(tmp_path, monkeypatch):
    """`_save_pref` rilegge e fonde: salvare la nuova chiave non deve
    cancellare il resto del file."""
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_dark_theme(True)
    preferences.save_minimize_target(MINIMIZE_TRAY)
    assert preferences.load_dark_theme() is True
    assert preferences.load_minimize_target() == MINIMIZE_TRAY


def test_i_valori_ammessi_coincidono_fra_tray_e_preferences(tmp_path, monkeypatch):
    """`preferences` ripete l'elenco invece di importarlo (sarebbe un ciclo):
    se i due divergono, un valore valido diventa muto e si comporta come
    «chiedi» senza che nulla protesti."""
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    for valore in MINIMIZE_TARGETS:
        preferences.save_minimize_target(valore)
        assert preferences.load_minimize_target() == valore, valore


# ---- 3. suggerimento dell'icona --------------------------------------------

def test_tooltip_senza_sessione(italian_ui):
    assert tooltip_text(0, 0, 0, 0.0) == "Nessun download in corso"


def test_tooltip_con_download_in_corso(italian_ui):
    testo = tooltip_text(2, 1, 5, 3 * 1024 * 1024)
    assert "2 in corso" in testo
    assert "1/5 completati" in testo
    assert "MB/s" in testo


def test_tooltip_a_sessione_finita(italian_ui):
    assert tooltip_text(0, 5, 5, 0.0) == "5/5 completati"


# ---- 4. dialogo della domanda (modale: esiste anche offscreen) --------------

def _rispondi_al_dialogo(chiave_pulsante: str, ricorda: bool) -> None:
    """Clicca un pulsante del QMessageBox modale non appena compare.

    Il timer si programma PRIMA di `exec()`: scatta dentro il ciclo di eventi
    modale. La rete di sicurezza chiude comunque il dialogo se il pulsante non
    si trova, cosi' un refuso non blocca la suite per sempre."""
    def _clicca() -> None:
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            return
        if ricorda:
            box.checkBox().setChecked(True)
        atteso = t(chiave_pulsante)
        for pulsante in box.buttons():
            if pulsante.text() == atteso:
                pulsante.click()
                return

    def _rete_di_sicurezza() -> None:
        box = QApplication.activeModalWidget()
        if box is not None:
            box.close()

    QTimer.singleShot(0, _clicca)
    QTimer.singleShot(3000, _rete_di_sicurezza)


def test_dialogo_scelta_area_di_notifica(qt_app, italian_ui):
    _rispondi_al_dialogo("tray.ask_tray", ricorda=False)
    scelta, ricorda = ask_minimize_target(None)
    assert scelta == MINIMIZE_TRAY
    assert ricorda is False


def test_dialogo_scelta_barra_con_ricorda(qt_app, italian_ui):
    _rispondi_al_dialogo("tray.ask_taskbar", ricorda=True)
    scelta, ricorda = ask_minimize_target(None)
    assert scelta == MINIMIZE_TASKBAR
    assert ricorda is True


# ---- 5. controller inerte senza area di notifica ---------------------------

def test_controller_inerte_non_solleva(qt_app):
    """Senza area di notifica il controller nasce inerte: chi lo usa non deve
    scrivere condizioni, e nessuna chiamata deve sollevare."""
    from PyQt6.QtGui import QIcon

    if _area_di_notifica_disponibile():
        pytest.skip("qui l'area di notifica c'e' davvero: vedi il test gemello")

    controller = TrayController(QIcon())
    assert controller.is_available() is False
    assert controller.is_visible() is False
    controller.show()
    controller.set_tooltip("qualcosa")
    controller.notify("titolo", "corpo")
    controller.notify("titolo", "corpo", warning=True)
    controller.retranslate()
    controller.hide()
    controller.shutdown()
    controller.shutdown()       # idempotente


def test_controller_vivo_mostra_icona_e_menu(qt_app, italian_ui):
    """Gira solo dove l'area di notifica esiste davvero (piattaforma Qt
    `windows`): icona visibile, voci di menu tradotte, smontaggio pulito.
    Sulla piattaforma offscreen della suite viene SALTATO, dichiarandolo."""
    from src.core.icon_loader import build_app_icon

    if not _area_di_notifica_disponibile():
        pytest.skip(_MOTIVO_SKIP)

    controller = TrayController(build_app_icon())
    try:
        assert controller.is_available() is True
        controller.show()
        assert controller.is_visible() is True
        assert controller._show_action.text() == t("tray.menu_show")
        assert controller._quit_action.text() == t("tray.menu_quit")
        controller.set_tooltip("prova")
        controller.notify("prova", "corpo")
    finally:
        controller.shutdown()
    assert controller.is_available() is False


# ---- 6. la finestra: decide senza avere un'area di notifica vera ------------

class _TrayFinto:
    def __init__(self, disponibile: bool) -> None:
        self._disponibile = disponibile

    def is_available(self) -> bool:
        return self._disponibile


class _ControlsFinti:
    def __init__(self) -> None:
        self.ultimo = None

    def set_minimize_target(self, value: str) -> None:
        self.ultimo = value


class _FinestraFinta:
    """Solo la logica di riduzione a icona di MainWindow, coi metodi VERI
    della classe: costruire la finestra intera aprirebbe thread di rete
    (aggiornamenti, speed test), che i test non devono fare. Stesso trucco
    gia' usato in `tests/test_i18n.py` per la riga di stato."""

    _handle_minimized = MainWindow._handle_minimized

    def __init__(self, tray_disponibile: bool) -> None:
        self._tray = _TrayFinto(tray_disponibile)
        self.controls = _ControlsFinti()
        self._minimize_prompt_open = False
        self.nascosta = False
        self.stato = None

    def isMinimized(self) -> bool:      # noqa: N802 - firma di QWidget
        return True

    def isVisible(self) -> bool:        # noqa: N802 - firma di QWidget
        return True

    def _hide_to_tray(self) -> None:
        self.nascosta = True

    def _set_status_t(self, key, **params) -> None:
        self.stato = key


def test_senza_area_di_notifica_la_riduzione_resta_quella_di_sempre(
    tmp_path, monkeypatch,
):
    """Trappola nota: se l'area di notifica non c'e', niente domanda e niente
    icona — la finestra si riduce come ha sempre fatto."""
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target(MINIMIZE_TRAY)
    chiamate = []
    monkeypatch.setattr(
        "src.gui.main_window.ask_minimize_target",
        lambda parent: chiamate.append(parent) or (MINIMIZE_TRAY, False),
    )
    finestra = _FinestraFinta(tray_disponibile=False)
    finestra._handle_minimized()
    assert finestra.nascosta is False
    assert chiamate == []


def test_preferenza_area_di_notifica_nasconde_senza_chiedere(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target(MINIMIZE_TRAY)
    chiamate = []
    monkeypatch.setattr(
        "src.gui.main_window.ask_minimize_target",
        lambda parent: chiamate.append(parent) or (MINIMIZE_TRAY, False),
    )
    finestra = _FinestraFinta(tray_disponibile=True)
    finestra._handle_minimized()
    assert finestra.nascosta is True
    assert chiamate == []


def test_preferenza_barra_non_nasconde_nulla(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target(MINIMIZE_TASKBAR)
    finestra = _FinestraFinta(tray_disponibile=True)
    finestra._handle_minimized()
    assert finestra.nascosta is False


def test_ricorda_la_scelta_la_persiste(tmp_path, monkeypatch):
    """Con «ricorda la scelta» spuntata la domanda non torna: la preferenza
    finisce su disco e il menu Impostazioni lo sa."""
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target(MINIMIZE_ASK)
    monkeypatch.setattr(
        "src.gui.main_window.ask_minimize_target",
        lambda parent: (MINIMIZE_TRAY, True),
    )
    finestra = _FinestraFinta(tray_disponibile=True)
    finestra._handle_minimized()
    assert preferences.load_minimize_target() == MINIMIZE_TRAY
    assert finestra.controls.ultimo == MINIMIZE_TRAY
    assert finestra.nascosta is True


def test_senza_ricorda_la_domanda_torna_la_prossima_volta(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_minimize_target(MINIMIZE_ASK)
    monkeypatch.setattr(
        "src.gui.main_window.ask_minimize_target",
        lambda parent: (MINIMIZE_TRAY, False),
    )
    finestra = _FinestraFinta(tray_disponibile=True)
    finestra._handle_minimized()
    assert finestra.nascosta is True
    assert preferences.load_minimize_target() == MINIMIZE_ASK


def test_uscita_esplicita_alla_chiusura_della_finestra():
    """`setQuitOnLastWindowClosed(False)` toglie l'uscita automatica: se
    `closeEvent` smette di chiudere l'applicazione, la X lascia il processo
    vivo e invisibile. Si controlla il sorgente perche' costruire la finestra
    vera aprirebbe thread di rete."""
    import inspect

    corpo = inspect.getsource(MainWindow.closeEvent)
    assert "self._tray.shutdown()" in corpo
    assert "app.quit()" in corpo
    assert "quitOnLastWindowClosed" in corpo


def test_main_disattiva_l_uscita_automatica():
    """L'altra meta' della stessa regola: senza questa riga, nascondere la
    finestra nell'area di notifica ucciderebbe l'applicazione."""
    import inspect

    import src.main

    assert "setQuitOnLastWindowClosed(False)" in inspect.getsource(src.main.main)
