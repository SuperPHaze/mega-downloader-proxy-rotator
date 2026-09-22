# Test del motore i18n della GUI (offline, nessuna rete).
# Coprono i punti del piano MyDocs/i18n-gui-2.0.0-design.md §3 "test necessari"
# relativi alla fase F1: parita' chiavi/parametri IT<->EN, rilevamento dal
# locale, precedenza della preferenza, chiave mancante, ritraduzione a caldo.
# Da F2c il dizionario ha voci plurali vere: i test sotto le esercitano
# tutte, a n=1 e n=2, in entrambe le lingue.
import inspect
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from src.gui import about_dialog, i18n, preferences
from src.gui.about_dialog import AboutDialog
from src.gui.controls import ControlsBar
from src.gui.experimental_dialog import ExperimentalFeaturesDialog
from src.gui.format_helpers import build_header_summary
from src.gui.jobs_panel import JobsPanel
from src.gui.link_panel import LinkPanel
from src.gui.main_window import MainWindow
from src.gui.proxy_bar import ProxyBar
from src.gui.stats_bar import StatsBar
from src.gui.stats_panel import StatsPanel
from src.gui.i18n import TR, Translator, language_from_locale_name, t, tn
from src.gui.paste_links_dialog import PasteLinksDialog
from src.gui.strings_en import STRINGS as STRINGS_EN
from src.gui.strings_it import STRINGS as STRINGS_IT
from src.gui.update_banner import UpdateBanner

# Anche gli specificatori di formato contano: `{required:,}` e `{kbps:.1f}`
# arrivano dal catalogo degli errori e un refuso li' renderebbe illeggibili
# solo in una delle due lingue.
_PARAM_RE = re.compile(r"\{(\w+)(?::[^{}]*)?\}")
_SPEC_RE = re.compile(r"\{\w+:([^{}]*)\}")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_prefs(tmp_path, monkeypatch):
    """preferences.json su tmp_path: nessuna scrittura nel progetto."""
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    return tmp_path


@pytest.fixture
def make_translator(isolated_prefs, monkeypatch):
    """Fabbrica di Translator nuovi (non il singleton: i test non si sporcano a
    vicenda) con il locale di SISTEMA simulato.

    Il locale va simulato PRIMA di costruire il Translator, perche' il
    costruttore risolve subito la lingua: costruirlo prima e simulare dopo
    lascerebbe lo stato iniziale in mano alla macchina che lancia la suite, e
    gli stessi test passerebbero in Italia e fallirebbero altrove."""
    def _make(system_language: str = "it") -> Translator:
        monkeypatch.setattr(i18n, "detect_system_language", lambda: system_language)
        return Translator()

    return _make


@pytest.fixture(autouse=True)
def restore_singleton():
    """Il singleton TR e' condiviso: qualunque test lo tocchi lo rimette com'era."""
    pref, lang = TR.preference(), TR.language()
    yield
    TR._preference = pref
    TR._language = lang


def _params(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for form in value.values():
            found |= set(_PARAM_RE.findall(str(form)))
        return found
    return set(_PARAM_RE.findall(str(value)))


# ---- 1. parita' delle chiavi (nessun estrattore automatico ci copre) --------

def test_key_parity_it_en():
    assert set(STRINGS_IT) == set(STRINGS_EN)


def test_plural_forms_parity():
    """Se una voce ha forme plurali in una lingua, le ha (uguali) anche nell'altra."""
    for key, it_value in STRINGS_IT.items():
        en_value = STRINGS_EN[key]
        assert isinstance(it_value, dict) == isinstance(en_value, dict), key
        if isinstance(it_value, dict):
            assert set(it_value) == set(en_value), key


# ---- 2. parita' dei parametri {nome} ---------------------------------------

def test_param_parity_it_en():
    """Un refuso in un {nome} inglese esploderebbe solo in inglese e solo a
    runtime: qui si vede subito."""
    for key, it_value in STRINGS_IT.items():
        assert _params(it_value) == _params(STRINGS_EN[key]), key


def test_format_spec_parity_it_en():
    """Gli specificatori (`:,`, `:.1f`) fanno parte del testo: se l'inglese ne
    perde uno, il numero esce formattato in modo diverso dai log."""
    for key, it_value in STRINGS_IT.items():
        forms_it = it_value.values() if isinstance(it_value, dict) else [it_value]
        en_value = STRINGS_EN[key]
        forms_en = en_value.values() if isinstance(en_value, dict) else [en_value]
        specs_it = {s for f in forms_it for s in _SPEC_RE.findall(str(f))}
        specs_en = {s for f in forms_en for s in _SPEC_RE.findall(str(f))}
        assert specs_it == specs_en, key


def test_no_positional_placeholders():
    """I parametri sono sempre nominati: `{}` o `{0}` non sono ammessi."""
    for table in (STRINGS_IT, STRINGS_EN):
        for key, value in table.items():
            forms = value.values() if isinstance(value, dict) else [value]
            for form in forms:
                assert "{}" not in str(form), key
                assert not re.search(r"\{\d+\}", str(form)), key


def test_language_names_are_not_translated():
    """Ogni lingua compare nel proprio nome, anche nell'altra lingua."""
    for key in ("controls.language_it", "controls.language_en"):
        assert STRINGS_IT[key] == STRINGS_EN[key]


# ---- 3. default dal locale di sistema --------------------------------------

@pytest.mark.parametrize(
    "locale_name, expected",
    [
        ("it_IT", "it"),
        ("it", "it"),
        ("it_CH", "it"),
        ("en_US", "en"),
        ("en_GB", "en"),
        ("de_DE", "en"),
        ("zz_ZZ", "en"),
        ("C", "en"),
        ("", "en"),
    ],
)
def test_language_from_locale_name(locale_name, expected):
    assert language_from_locale_name(locale_name) == expected


@pytest.mark.parametrize("system_language", ["it", "en"])
def test_auto_follows_detected_language(make_translator, system_language):
    tr = make_translator(system_language)
    tr.set_preference("auto")
    assert tr.language() == system_language


# ---- 4. precedenza della preferenza esplicita ------------------------------

def test_explicit_preference_wins_over_locale(make_translator):
    """language="en" su sistema italiano -> inglese."""
    tr = make_translator("it")
    tr.set_preference("en")
    assert tr.language() == "en"
    assert tr.preference() == "en"


def test_explicit_italian_wins_over_english_locale(make_translator):
    """E il reciproco: language="it" su sistema inglese -> italiano."""
    tr = make_translator("en")
    tr.set_preference("it")
    assert tr.language() == "it"
    assert tr.preference() == "it"


def test_initialize_reads_persisted_preference(make_translator):
    preferences.save_language("en")
    tr = make_translator("it")
    tr.initialize()
    assert tr.preference() == "en"
    assert tr.language() == "en"


def test_preference_is_persisted(make_translator):
    tr = make_translator("it")
    tr.set_preference("en")
    assert preferences.load_language() == "en"


def test_preference_default_is_auto_when_unset(isolated_prefs):
    assert preferences.load_language() == "auto"


def test_unknown_persisted_preference_falls_back_to_auto(isolated_prefs):
    preferences.save_language("klingon")
    assert preferences.load_language() == "auto"


def test_invalid_preference_falls_back_to_auto(make_translator):
    tr = make_translator("it")
    tr.set_preference("klingon")
    assert tr.preference() == "auto"
    assert tr.language() == "it"


@pytest.mark.parametrize(
    "system_language, same, other", [("it", "it", "en"), ("en", "en", "it")]
)
def test_language_changed_emitted_only_on_real_change(
    make_translator, system_language, same, other
):
    """Il segnale parte solo se la lingua EFFETTIVA cambia. Provato su entrambi
    i locali di sistema: l'esito non deve dipendere dalla macchina."""
    tr = make_translator(system_language)
    seen: list[str] = []
    tr.language_changed.connect(seen.append)
    tr.set_preference(same)        # gia' quella lingua: nessun cambio effettivo
    assert seen == []
    tr.set_preference(other)
    assert seen == [other]


# ---- 5/6. lookup: parametri, chiave mancante, plurali ----------------------

def test_translation_uses_current_language(isolated_prefs):
    """Dall'API pubblica, non toccando lo stato interno: e' il percorso che usa
    l'app quando l'utente sceglie dal menu."""
    TR.set_preference("it")
    assert t("controls.start") == "Avvia"
    TR.set_preference("en")
    assert t("controls.start") == "Start"


def test_named_params_are_substituted():
    TR._language = "it"
    out = t("main_window.title", name="MDPR", version="1.21.0")
    assert out == "MDPR v1.21.0"


def test_missing_key_in_english_falls_back_to_italian(monkeypatch):
    """Traduzione incompleta = testo italiano a video, mai lo slug, mai eccezione."""
    monkeypatch.setitem(i18n._TABLES, "en", {})
    TR._language = "en"
    assert t("controls.start") == "Avvia"


def test_unknown_key_does_not_raise():
    TR._language = "it"
    assert t("chiave.che.non.esiste") == "chiave.che.non.esiste"


def test_missing_param_does_not_raise():
    """Un parametro dimenticato dal chiamante non deve far crashare la GUI."""
    TR._language = "it"
    assert "{path}" in t("controls.download_dir_tooltip_chosen")


def test_tn_selects_singular_and_plural(monkeypatch):
    """Il meccanismo dei plurali (le voci vere arrivano in F2)."""
    entry = {"one": "1 link pronto", "other": "{n} link pronti"}
    monkeypatch.setitem(i18n._TABLES, "it", {"tmp.ready": entry})
    TR._language = "it"
    assert tn("tmp.ready", 1) == "1 link pronto"
    assert tn("tmp.ready", 3) == "3 link pronti"


# ---- 7. ritraduzione a caldo (pannello pilota) -----------------------------

def test_controls_bar_retranslates_hot(qapp, isolated_prefs, monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    bar = ControlsBar()
    assert bar.start_btn.text().strip() == "Avvia"

    TR.set_preference("en")
    bar.retranslate()       # in app lo fa MainWindow._on_language_changed
    assert bar.start_btn.text().strip() == "Start"
    assert bar.cancel_btn.text().strip() == "Cancel"
    assert bar._settings_labels["controls.row_language"].text() == "Language:"

    TR.set_preference("it")
    bar.retranslate()
    assert bar.start_btn.text().strip() == "Avvia"


def test_controls_bar_keeps_state_across_retranslation(qapp, isolated_prefs, monkeypatch):
    """La ritraduzione riscrive i testi, non lo stato: pausa, tema e cartella
    scelta devono sopravvivere."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    bar = ControlsBar()
    bar._paused = True
    bar.set_dark(True)
    bar.set_download_dir(r"C:\Downloads\Mega")

    TR.set_preference("en")
    bar.retranslate()
    assert bar.pause_btn.text().strip() == "Resume"
    assert bar.download_dir_btn.text() == "Mega"
    assert "Switch to the light theme" in bar.theme_btn.toolTip()
    assert bar._paused is True
    assert bar._dark is True


def test_language_combo_reflects_preference(qapp, isolated_prefs, monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("en")
    bar = ControlsBar()
    assert bar.language_combo.currentData() == "en"
    # La voce "Automatica" mostra la lingua rilevata, nel suo nome.
    assert bar.language_combo.itemText(0) == "Automatic (Italiano)"


def test_language_combo_selection_changes_preference(qapp, isolated_prefs, monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    bar = ControlsBar()
    idx = bar.language_combo.findData("en")
    bar.language_combo.setCurrentIndex(idx)
    assert TR.preference() == "en"
    assert TR.language() == "en"


def test_retranslate_does_not_reenter_preference_change(qapp, isolated_prefs, monkeypatch):
    """Riscrivere il combo in retranslate() non deve valere come una scelta
    dell'utente (sarebbe un rientro su set_preference)."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("en")
    bar = ControlsBar()
    changes: list[str] = []
    TR.language_changed.connect(changes.append)
    try:
        bar.retranslate()
    finally:
        TR.language_changed.disconnect(changes.append)
    assert changes == []
    assert TR.preference() == "en"


# ---- F2a: banner e dialoghi ------------------------------------------------

# Superfici migrate finora: un file che perde la sua voce qui e' un file
# dimenticato dalla migrazione, non un test da aggiornare a cuor leggero.
MIGRATED_SURFACES = (
    "main_window", "controls", "update_banner", "about", "experimental", "paste",
    "format", "stats_bar", "proxy_bar", "stats_panel", "jobs_panel",
    "link_panel", "folder_expand",
    # E2: errori del motore, righe di stato del setup, cronologia e dettaglio
    # del job. Con queste la traduzione dell'interfaccia e' completa.
    "err", "setup", "job_log", "job_detail",
)


@pytest.mark.parametrize("surface", MIGRATED_SURFACES)
def test_migrated_surface_has_keys(surface):
    prefix = f"{surface}."
    assert any(k.startswith(prefix) for k in STRINGS_IT), surface
    assert any(k.startswith(prefix) for k in STRINGS_EN), surface


def test_update_banner_retranslates_hot(qapp, isolated_prefs, monkeypatch):
    """Il banner e' una superficie persistente: deve ritradursi a caldo."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    banner = UpdateBanner()
    banner.show_update("2.0.0")
    assert banner._label.text() == "Disponibile la versione 2.0.0."
    assert banner._download_btn.text() == "Scarica"

    TR.set_preference("en")
    banner.retranslate()        # in app lo fa MainWindow._on_language_changed
    assert banner._label.text() == "Version 2.0.0 is available."
    assert banner._download_btn.text() == "Download"


def test_update_banner_keeps_version_across_retranslation(qapp, isolated_prefs, monkeypatch):
    """La versione annunciata sopravvive al cambio lingua: il chiamante non
    ripassa da show_update()."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    banner = UpdateBanner()
    banner.show_update("3.1.4")
    TR.set_preference("en")
    banner.retranslate()
    assert "3.1.4" in banner._label.text()


def test_update_banner_empty_before_any_update(qapp, isolated_prefs, monkeypatch):
    """Senza una versione annunciata l'etichetta resta vuota, in ogni lingua:
    non deve comparire una frase con un segnaposto al posto del numero."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")
    banner = UpdateBanner()
    assert banner._label.text() == ""
    TR.set_preference("en")
    banner.retranslate()
    assert banner._label.text() == ""


@pytest.mark.parametrize(
    "language, expected",
    [("it", "Incolla link Mega"), ("en", "Paste Mega links")],
)
def test_paste_dialog_built_in_current_language(
    qapp, isolated_prefs, monkeypatch, language, expected
):
    """I dialoghi nascono all'apertura: leggono la lingua corrente alla
    costruzione, quindi non hanno bisogno di retranslate()."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference(language)
    dlg = PasteLinksDialog([], False)
    assert dlg.windowTitle() == expected


@pytest.mark.parametrize(
    "language, expected", [("it", "Funzioni Sperimentali"), ("en", "Experimental Features")]
)
def test_experimental_dialog_built_in_current_language(
    qapp, isolated_prefs, monkeypatch, language, expected
):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference(language)
    dlg = ExperimentalFeaturesDialog()
    assert dlg.windowTitle() == expected


@pytest.mark.parametrize("language, expected", [("it", "Info"), ("en", "About")])
def test_about_dialog_built_in_current_language(
    qapp, isolated_prefs, monkeypatch, language, expected
):
    # Il fetch remoto del branding non deve partire: il test e' offline.
    monkeypatch.setattr(about_dialog, "branding_enabled", lambda: False)
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference(language)
    dlg = AboutDialog()
    assert dlg.windowTitle() == expected


def test_paste_dialog_counters_are_named_params(qapp, isolated_prefs, monkeypatch):
    """I conteggi sono parametri {n}, non plurali: il numero finisce nel testo
    in entrambe le lingue."""
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("en")
    dlg = PasteLinksDialog([], False)
    dlg.edit.setPlainText("https://mega.nz/file/AAA#k\nnon-un-link")
    assert dlg.lbl_valid.text() == "Valid: 1"
    assert dlg.lbl_invalid.text() == "Invalid: 1"
    assert dlg.add_btn.text() == "Add 1"


# ---- F2b: pannelli persistenti e cascate ----------------------------------

def _in_italian(monkeypatch):
    monkeypatch.setattr(i18n, "detect_system_language", lambda: "it")
    TR.set_preference("it")


def test_proxy_bar_retranslates_with_cascade(qapp, isolated_prefs, monkeypatch):
    """La cascata sulle _MetricCard: ogni card tiene la chiave, non il testo."""
    _in_italian(monkeypatch)
    bar = ProxyBar()
    assert bar._card_alive._label.text() == "VIVI"
    assert bar._card_validation._label.text() == "VALIDAZIONE"

    TR.set_preference("en")
    bar.retranslate()
    assert bar._card_alive._label.text() == "ALIVE"
    assert bar._card_validation._label.text() == "VALIDATION"
    assert bar._card_band_proxy._label.text() == "PROXY SPEED"
    assert bar._reset_btn.text() == "Reset cache"
    assert "proxy pool" in bar._proxy_speedtest_btn.toolTip()


def test_proxy_bar_retranslation_keeps_card_values(qapp, isolated_prefs, monkeypatch):
    """Ritradurre riscrive le ETICHETTE, non i VALORI: un cambio lingua non
    deve azzerare i numeri gia' mostrati."""
    _in_italian(monkeypatch)
    bar = ProxyBar()
    bar.on_pool_size(42)
    bar.on_proxy_stats(17, 3, 95.0)
    TR.set_preference("en")
    bar.retranslate()
    assert bar._card_alive._value.text() == "42"
    assert bar._card_discarded._value.text() == "17"
    assert bar._card_refills._value.text() == "3"


def test_stats_bar_retranslates(qapp, isolated_prefs, monkeypatch):
    _in_italian(monkeypatch)
    panel = JobsPanel()
    bar = StatsBar(panel.model)
    assert bar._speed_micro.text() == "VELOCITÀ"
    assert bar._job_micro.text() == "DOWNLOAD"
    assert "totali" in bar._job_total.text()

    TR.set_preference("en")
    bar.retranslate()
    assert bar._speed_micro.text() == "SPEED"
    assert bar._job_micro.text() == "DOWNLOADS"
    assert "total" in bar._job_total.text()
    assert "running" in bar._job_counts.text()


def test_stats_panel_retranslates(qapp, isolated_prefs, monkeypatch):
    _in_italian(monkeypatch)
    panel = JobsPanel()
    stats = StatsPanel(panel.model)
    stats._body.setVisible(True)
    stats.refresh()
    assert stats._title_lbl.text() == "Statistiche"
    assert stats._copy_btn.text() == "Copia riepilogo"
    assert stats._speed_hdr.text() == "Velocità di sessione"

    TR.set_preference("en")
    stats.retranslate()
    assert stats._title_lbl.text() == "Statistics"
    assert stats._copy_btn.text() == "Copy summary"
    assert stats._speed_hdr.text() == "Session speed"
    assert stats._detail_hdr.text() == "Per-download detail:"
    assert stats._throughput_lbl.text().startswith("  Effective throughput :")


def test_jobs_panel_retranslates_with_cascade(qapp, isolated_prefs, monkeypatch):
    """La cascata su _EmptyState e su OGNI _JobCard."""
    _in_italian(monkeypatch)
    panel = JobsPanel()
    assert panel._empty._msg.text() == "Aggiungi i tuoi link Mega per iniziare"
    assert panel._filter_buttons["in_progress"].text() == "In corso (0)"

    panel.reset(["https://mega.nz/file/AAA#k", "https://mega.nz/file/BBB#k"])
    panel.on_all_done(1)
    assert panel._cards[0]._badge.text() == "In coda"
    assert panel._cards[1]._badge.text() == "Completato"

    TR.set_preference("en")
    panel.retranslate()
    assert panel._empty._msg.text() == "Add your Mega links to get started"
    assert panel._filter_buttons["in_progress"].text() == "In progress (1)"
    assert panel._filter_buttons["completed"].text() == "Completed (1)"
    assert panel._restart_all_btn.text() == "Restart failed (0)"
    # La cascata ha raggiunto entrambe le card, non solo la prima.
    assert panel._cards[0]._badge.text() == "Queued"
    assert panel._cards[1]._badge.text() == "Completed"


def test_empty_state_button_matches_controls_key(qapp, isolated_prefs, monkeypatch):
    """Il pulsante dello stato vuoto e il suggerimento che lo nomina usano la
    STESSA chiave della barra comandi: non possono sfasarsi."""
    _in_italian(monkeypatch)
    panel = JobsPanel()
    TR.set_preference("en")
    panel.retranslate()
    assert panel._empty._btn.text().strip() == t("controls.paste_links")
    assert t("controls.paste_links") in panel._empty._sub.text()


def test_job_card_renders_the_error_in_both_languages(qapp, isolated_prefs, monkeypatch):
    """Con E2 il confine di F2b si sposta: l'errore arriva dal modello come
    PAYLOAD e la card lo rende nella lingua corrente. La cascata di F2b
    (JobsPanel.retranslate -> ogni card) basta gia': niente cablaggio nuovo."""
    _in_italian(monkeypatch)
    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#k"])
    panel.on_abandoned(
        0, "https://mega.nz/file/AAA#k", 3, "ip_check_failed", {"error": "timeout"},
    )
    testo = panel._cards[0]._attempts_lbl.text()
    assert testo.startswith("Tentativi: 3")
    assert testo.endswith("Ultimo errore: IP check fallito: timeout")

    TR.set_preference("en")
    panel.retranslate()
    testo = panel._cards[0]._attempts_lbl.text()
    assert testo.startswith("Attempts: 3")
    assert testo.endswith("Last error: IP check failed: timeout")


def test_job_card_applies_the_abandon_alias(qapp, isolated_prefs, monkeypatch):
    """Il canale porta il codice del tentativo fallito (con le parentesi):
    l'abbandono deve comunque leggersi coi due punti, come prima di E2."""
    _in_italian(monkeypatch)
    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#k"])
    panel.on_abandoned(
        0, "https://mega.nz/file/AAA#k", 3,
        "ip_check_failed_paren", {"error": "timeout"},
    )
    testo = panel._cards[0]._attempts_lbl.text()
    assert testo.endswith("Ultimo errore: IP check fallito: timeout")


def test_job_card_frames_the_failed_attempt(qapp, isolated_prefs, monkeypatch):
    """Il tentativo fallito conserva la cornice «Tentativo N: » nell'ultimo
    errore, esattamente com'era prima di E2."""
    _in_italian(monkeypatch)
    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#k"])
    panel.on_failed(0, 1, "download_failed_paren", {"error": "boom"})
    testo = panel._cards[0]._attempts_lbl.text()
    assert testo.endswith("Ultimo errore: Tentativo 1: download fallito (boom)")


def test_header_summary_follows_language(isolated_prefs, monkeypatch):
    """build_header_summary non e' piu' puro rispetto alla lingua: le
    abbreviazioni tot/ok/fall. sono parole, non unita' di misura."""
    _in_italian(monkeypatch)
    totals = {"total": 5, "ok": 3, "fallen": 1}
    it_out = build_header_summary(60, 1024, 0.0, totals, True)
    assert "5 tot" in it_out and "1 fall." in it_out and "(completata)" in it_out

    TR.set_preference("en")
    en_out = build_header_summary(60, 1024, 0.0, totals, True)
    assert "5 tot" in en_out and "1 fail." in en_out and "(completed)" in en_out
    # Le unita' NON si traducono.
    assert "1 KB" in it_out and "1 KB" in en_out


# ---- F2c: plurali veri -----------------------------------------------------

PLURAL_KEYS = tuple(sorted(k for k, v in STRINGS_IT.items() if isinstance(v, dict)))


def test_there_are_plural_entries():
    """Guardia: se il dizionario perdesse le voci plurali, i test sotto
    passerebbero a vuoto senza verificare nulla."""
    assert len(PLURAL_KEYS) >= 14, PLURAL_KEYS


@pytest.mark.parametrize("key", PLURAL_KEYS)
@pytest.mark.parametrize("lang", ("it", "en"))
def test_plural_key_renders_the_right_form(key, lang, isolated_prefs, monkeypatch):
    """Per ogni voce plurale: n=1 rende la forma "one", n>1 la forma "other".

    E' il test che esercita `tn()` sul serio (in F1 c'era solo un dizionario
    finto). Il confronto e' sul TESTO reso, non sulla forma scelta: cosi'
    prende anche un parametro che non si sostituisce.
    """
    monkeypatch.setattr(i18n, "detect_system_language", lambda: lang)
    TR.set_preference(lang)
    table = STRINGS_IT if lang == "it" else STRINGS_EN
    forms = table[key]
    # Parametri fittizi per tutte le variabili diverse da {n}, che tn() mette
    # da se': senza, il testo resterebbe grezzo e il confronto sarebbe vacuo.
    names = set()
    for form in forms.values():
        names |= set(_PARAM_RE.findall(form))
    extra = {name: f"<{name}>" for name in names if name != "n"}

    assert tn(key, 1, **extra) == forms["one"].format(n=1, **extra)
    assert tn(key, 2, **extra) == forms["other"].format(n=2, **extra)
    # Nessun segnaposto rimasto da sostituire.
    assert "{" not in tn(key, 2, **extra), key


# L'inglese distingue singolare e plurale in ogni voce plurale tranne queste,
# dove la parola non cambia («2 file», «2 link» non esistono al plurale in
# quel contesto) oppure la frase non nomina il conteggio.
EN_INVARIANT_PLURALS = frozenset()


@pytest.mark.parametrize("key", PLURAL_KEYS)
def test_english_plurals_are_distinct(key, isolated_prefs, monkeypatch):
    """In inglese le due forme devono davvero differire: una voce plurale con
    forme identiche sarebbe una traduzione lasciata a meta'."""
    if key in EN_INVARIANT_PLURALS:
        pytest.skip("parola invariabile in inglese")
    forms = STRINGS_EN[key]
    assert forms["one"] != forms["other"], key


# Le 8 frasi italiane il cui singolare ripeteva il plurale («1 sottocartelle»),
# corrette in F3. Difetto PREESISTENTE alla traduzione: le fasi precedenti lo
# avevano tenuto identico di proposito, per non cambiare il testo IT mentre si
# migrava. Qui si blocca il testo CORRETTO, così una regressione si vede.
SINGOLARI_CORRETTI = {
    "folder_expand.subfolders_suffix": ", 1 sottocartella",
    "folder_expand.duplicates_removed":
        "• 1 file duplicato (stesso file incollato più volte) è stato rimosso.",
    "main_window.expand_ready": "1 file pronto al download.",
    "main_window.restart_all_done": "Riavviato 1 download.",
    "main_window.restored_status":
        "Ripristinato 1 link dalla sessione precedente. Premi Avvia per riprendere.",
}


@pytest.mark.parametrize("key", sorted(SINGOLARI_CORRETTI))
def test_italian_singulars_are_grammatical(key, isolated_prefs, monkeypatch):
    _in_italian(monkeypatch)
    assert tn(key, 1) == SINGOLARI_CORRETTI[key]


def test_italian_singulars_with_extra_params(isolated_prefs, monkeypatch):
    """Le tre frasi che portano anche un altro parametro oltre al conteggio."""
    _in_italian(monkeypatch)
    assert tn("main_window.abandoned_status", 1, file=2, error="X") == (
        "File 2 abbandonato dopo 1 tentativo: X"
    )
    assert tn("job_log.abandoned", 1, error="X") == (
        "Link abbandonato dopo 1 tentativo: X"
    )
    assert "1 file NON verrà scaricato" in tn(
        "main_window.expand_truncated_body", 1, kept=9
    )
    assert "1 link non completato" in tn("main_window.restore_body", 1)
    assert "Vuoi ricaricarlo" in tn("main_window.restore_body", 1)


def test_italian_plurals_still_plural(isolated_prefs, monkeypatch):
    """Correggere il singolare non deve aver toccato il plurale, che e' il
    testo che l'app mostra nel caso normale (n > 1)."""
    _in_italian(monkeypatch)
    assert tn("folder_expand.subfolders_suffix", 3) == ", 3 sottocartelle"
    assert tn("main_window.expand_ready", 3) == "3 file pronti al download."
    assert tn("main_window.restart_all_done", 3) == "Riavviati 3 download."
    assert tn("main_window.abandoned_status", 3, file=2, error="X") == (
        "File 2 abbandonato dopo 3 tentativi: X"
    )


def test_no_italian_plural_entry_repeats_itself():
    """Guardia generale: nessuna voce plurale italiana deve piu' avere le due
    forme identiche — tranne le `err.*`, il cui testo viene dal catalogo del
    motore (`core/error_catalog.py`) e li' e' anche il testo dei LOG, che non
    si tocca."""
    identiche = sorted(
        k for k in PLURAL_KEYS
        if not k.startswith("err.")
        and STRINGS_IT[k]["one"] == STRINGS_IT[k]["other"]
    )
    # Restano solo le voci in cui la parola italiana e' davvero invariabile
    # («1 file», «1 link»): li' il singolare corretto COINCIDE col plurale.
    # Le tre `maintenance.detail_*` sono lo stesso caso: contano «file» e
    # «link». Dove la parola italiana si flette davvero — «voce/voci»,
    # «frammento/frammenti» — le due forme sono distinte e non stanno qui.
    assert identiche == [
        "folder_expand.ok_line",
        "link_panel.history_more",
        "link_panel.import_done_body",
        "maintenance.detail_downloads",
        "maintenance.detail_logs",
        "maintenance.detail_session",
    ], identiche


# ---- F2c: pannello link ----------------------------------------------------

def test_link_panel_retranslates_hot(qapp, isolated_prefs, monkeypatch):
    """LinkPanel e' una superficie persistente: si ritraduce a caldo."""
    _in_italian(monkeypatch)
    panel = LinkPanel()
    assert panel.import_btn.text() == "Importa da file"
    assert panel.clear_btn.text() == "Svuota"
    assert panel.allow_dups.text() == "Consenti duplicati"

    TR.set_preference("en")
    panel.retranslate()
    assert panel.import_btn.text() == "Import from file"
    assert panel.clear_btn.text() == "Clear"
    assert panel.allow_dups.text() == "Allow duplicates"
    assert "separate folder" in panel.allow_dups.toolTip()


def test_link_panel_counter_singular_and_plural(qapp, isolated_prefs, monkeypatch):
    """Il contatore attraversa i tre casi: nessuno, uno, molti."""
    _in_italian(monkeypatch)
    panel = LinkPanel()
    assert panel.counter_lbl.text() == "nessun link"
    panel.set_links(["https://mega.nz/file/A#k"])
    assert panel.counter_lbl.text() == "1 link pronto"
    panel.set_links(["https://mega.nz/file/A#k", "https://mega.nz/file/B#k"])
    assert panel.counter_lbl.text() == "2 link pronti"

    TR.set_preference("en")
    panel.retranslate()
    assert panel.counter_lbl.text() == "2 links ready"
    panel.set_links(["https://mega.nz/file/A#k"])
    assert panel.counter_lbl.text() == "1 link ready"
    panel.set_links([])
    assert panel.counter_lbl.text() == "no links"


def test_link_panel_state_survives_retranslation(qapp, isolated_prefs, monkeypatch):
    """La ritraduzione riscrive i testi, non lo stato: la lista e la checkbox
    restano quelle."""
    _in_italian(monkeypatch)
    panel = LinkPanel()
    panel.set_links(["https://mega.nz/file/A#k"])
    panel.allow_dups.setChecked(True)
    panel.set_running(True)

    TR.set_preference("en")
    panel.retranslate()
    assert panel.get_links() == ["https://mega.nz/file/A#k"]
    assert panel.allow_dups.isChecked()
    assert not panel.import_btn.isEnabled()


# ---- F2c: espansione delle cartelle ---------------------------------------

def test_folder_expand_report_follows_language(qapp, isolated_prefs, monkeypatch):
    """Il report dell'espansione nasce in un QThread: deve leggere il
    dizionario come tutto il resto. Nessuna rete: l'espansione e' finta."""
    from src.downloader.mega_folder import FolderExpansion, FolderFile
    from src.gui import folder_expand_worker as few

    def fake_expand(url, should_abort=None, max_files=0):
        return FolderExpansion(
            folder_id="AAA", folder_name="Vacanze",
            files=(FolderFile("N1", "S2V5", 100, ("Vacanze", "a.bin")),),
            total_files=1, n_folders=1, n_skipped=0,
        )

    monkeypatch.setattr(few, "expand_folder_link", fake_expand)

    _in_italian(monkeypatch)
    worker = few.FolderExpandWorker(["https://mega.nz/folder/AAA#chiave"])
    catturato = []
    worker.finished_ok.connect(lambda links, report, tr: catturato.append(report))
    worker.run()
    assert catturato and "1 sottocartella" in catturato[0][0]

    TR.set_preference("en")
    worker2 = few.FolderExpandWorker(["https://mega.nz/folder/AAA#chiave"])
    catturato2 = []
    worker2.finished_ok.connect(lambda links, report, tr: catturato2.append(report))
    worker2.run()
    assert catturato2 and "1 subfolder" in catturato2[0][0]
    assert "sottocartelle" not in catturato2[0][0]


# ---- F2c: riga di stato della finestra ------------------------------------

class _FinestraFinta:
    """Solo la riga di stato di MainWindow, con i metodi VERI della classe:
    costruire la finestra intera aprirebbe thread di rete (aggiornamenti,
    speed test), che i test non devono fare."""

    _set_status_t = MainWindow._set_status_t
    _set_status_tn = MainWindow._set_status_tn
    _refresh_status = MainWindow._refresh_status

    def __init__(self, label):
        self._status_lbl = label
        self._status_source = None


def test_status_line_retranslates(qapp, isolated_prefs, monkeypatch):
    """La riga di stato ricorda chiave e parametri: al cambio lingua si
    riscrive invece di restare indietro fino all'evento successivo."""
    from PyQt6.QtWidgets import QLabel

    _in_italian(monkeypatch)
    win = _FinestraFinta(QLabel())
    win._set_status_t("main_window.file_done", file=2, done=2, total=5)
    assert win._status_lbl.text() == "File 2 completato (2/5)."

    TR.set_preference("en")
    win._refresh_status()
    assert win._status_lbl.text() == "File 2 completed (2/5)."


def test_status_line_retranslates_plural(qapp, isolated_prefs, monkeypatch):
    _in_italian(monkeypatch)
    from PyQt6.QtWidgets import QLabel

    win = _FinestraFinta(QLabel())
    win._set_status_tn("main_window.expand_status", 1)
    assert win._status_lbl.text() == "Espansione di 1 cartella Mega in corso…"

    TR.set_preference("en")
    win._refresh_status()
    assert win._status_lbl.text() == "Expanding 1 Mega folder…"


def test_no_raw_status_setter_left(qapp, isolated_prefs, monkeypatch):
    """Con E2 anche le righe dell'orchestrator hanno una chiave: il
    `_set_status()` grezzo non serve piu' e non deve tornare. Se qualcuno lo
    reintroduce, quel testo smette di ritradursi senza che nulla protesti."""
    assert not hasattr(MainWindow, "_set_status")
    sorgente = inspect.getsource(MainWindow)
    assert "self._set_status(" not in sorgente


def test_language_fanout_covers_every_persistent_surface():
    """Il fan-out di `_on_language_changed` deve nominare TUTTE le superfici
    persistenti: se ne nasce una nuova e non viene cablata, resta nella lingua
    vecchia finche' qualcuno non se ne accorge a video."""
    import inspect

    corpo = inspect.getsource(MainWindow._on_language_changed)
    for atteso in (
        "_refresh_window_title",
        "self.controls.retranslate",
        "self.update_banner.retranslate",
        "self.stats_bar.retranslate",
        "self.proxy_bar.retranslate",
        "self._stats_panel.retranslate",
        "self.jobs_panel.retranslate",
        "self.link_panel.retranslate",
        "self._tray.retranslate",
        "self._retranslate_open_details",
        "self._refresh_status",
    ):
        assert atteso in corpo, atteso


# ---- E2: dettaglio job, l'unico dialogo persistente ------------------------

def _job_con_storia(monkeypatch):
    """Un job con log e cronologia IP gia' popolati."""
    from src.gui.jobs_model import JobsModel

    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#k"])
    model.set_progress(0, 10)
    model.set_ip(0, "1.2.3.4")
    model.add_failure(0, "ip_check_failed_paren", {"error": "timeout"})
    model.mark_abandoned(0, 25, "ip_check_failed", {"error": "timeout"})
    return model


def test_job_detail_built_in_current_language(qapp, isolated_prefs, monkeypatch):
    from src.gui.job_detail_dialog import JobDetailDialog

    _in_italian(monkeypatch)
    TR.set_preference("en")
    dlg = JobDetailDialog(_job_con_storia(monkeypatch), 0)
    assert dlg.windowTitle() == "Job detail #1"
    assert dlg.close_btn.text() == "Close"
    assert dlg.log_label.text() == "Attempts log:"
    assert "Link abandoned after 25 attempts" in dlg.log_view.toPlainText()


def test_job_detail_retranslates_with_a_populated_log(qapp, isolated_prefs, monkeypatch):
    """IL caso che smaschera il difetto del conteggio: al cambio lingua il
    NUMERO di righe del log non cambia, quindi senza `force=True` il log
    resterebbe nella lingua vecchia."""
    from src.gui.job_detail_dialog import JobDetailDialog

    _in_italian(monkeypatch)
    dlg = JobDetailDialog(_job_con_storia(monkeypatch), 0)
    prima = dlg.log_view.toPlainText()
    assert "Download avviato" in prima
    assert "Link abbandonato dopo 25 tentativi" in prima
    n_righe = len(prima.splitlines())

    TR.set_preference("en")
    dlg.retranslate()
    dopo = dlg.log_view.toPlainText()
    assert len(dopo.splitlines()) == n_righe      # stesso numero di voci...
    assert "Download started" in dopo             # ...ma testo ritradotto
    assert "Link abandoned after 25 attempts" in dopo
    assert "Download avviato" not in dopo
    assert dlg.windowTitle() == "Job detail #1"
    assert dlg.ip_history_label.text() == "IP history:"
    assert dlg.abandoned_title.text() == "Link abandoned"
    assert "Last error: IP check failed: timeout" in dlg.summary_label.text()


def test_job_status_is_translated_everywhere(qapp, isolated_prefs, monkeypatch):
    """Lo stato del job non deve piu' comparire grezzo ("in_corso") da nessuna
    parte: badge della card e riepilogo del dettaglio usano la STESSA mappa."""
    from src.gui.job_detail_dialog import JobDetailDialog
    from src.gui.jobs_model import STATUS_ABANDONED, STATUS_RUNNING
    from src.gui.jobs_panel import status_label

    _in_italian(monkeypatch)
    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#k"])
    job = panel.model.get_job(0)
    dlg = JobDetailDialog(panel.model, 0)

    for stato, atteso_it, atteso_en in (
        (STATUS_RUNNING, "In corso", "Running"),
        (STATUS_ABANDONED, "Abbandonato", "Abandoned"),
    ):
        job.status = stato
        for lang, atteso in (("it", atteso_it), ("en", atteso_en)):
            TR.set_preference(lang)
            panel.retranslate()
            dlg.retranslate()
            assert status_label(stato) == atteso
            assert atteso in panel._cards[0]._badge.text()
            assert atteso in dlg.summary_label.text()
            assert stato not in dlg.summary_label.text()   # niente slug grezzo


def test_status_badge_fits_the_longest_label(qapp, isolated_prefs, monkeypatch):
    """Il badge ha larghezza fissa: l'etichetta piu' lunga (l'italiano
    "Abbandonato") ci deve stare, altrimenti viene tagliata a meta' parola.

    Due avvertenze, entrambe verificate e non dedotte:
      - si misura a **10pt**, non agli 8pt che il codice chiede con `setFont`:
        il QSS d'applicazione (`QWidget { font-size: 10pt }`) sovrascrive il
        font impostato a mano, quindi 10pt e' cio' che l'utente vede davvero;
      - senza Segoe UI (piattaforma offscreen, Linux, CI) le metriche vengono
        da un font sostitutivo piu' largo e il numero non direbbe nulla sul
        prodotto reale: li' il test si salta invece di fallire a vuoto.
    """
    from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics
    from src.gui.jobs_panel import _STATUS_LABEL_KEY

    if "Segoe UI" not in QFontDatabase.families():
        pytest.skip("Segoe UI non disponibile: le metriche non sarebbero quelle rese")

    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#k"])
    utile = panel._cards[0]._badge.width() - 14   # padding 2px 6px + bordo 1px
    reso = QFont("Segoe UI", 10)
    reso.setBold(True)
    fm = QFontMetrics(reso)
    for lang in ("it", "en"):
        TR.set_preference(lang)
        for key in _STATUS_LABEL_KEY.values():
            assert fm.horizontalAdvance(t(key)) <= utile, (lang, key, t(key))


def test_job_detail_ip_table_survives_retranslation(qapp, isolated_prefs, monkeypatch):
    from src.gui.job_detail_dialog import JobDetailDialog

    _in_italian(monkeypatch)
    dlg = JobDetailDialog(_job_con_storia(monkeypatch), 0)
    assert dlg.ip_table.rowCount() == 1
    assert dlg.ip_table.item(0, 1).text() == "1.2.3.4"

    TR.set_preference("en")
    dlg.retranslate()
    assert dlg.ip_table.rowCount() == 1
    assert dlg.ip_table.item(0, 1).text() == "1.2.3.4"
    assert dlg.ip_table.horizontalHeaderItem(1).text() == "IP"


# ---- E2: riga di stato con un errore dentro --------------------------------

def test_status_line_error_payload_follows_language(qapp, isolated_prefs, monkeypatch):
    """La riga di stato ricorda il PAYLOAD dell'errore, non il testo gia' reso:
    al cambio lingua cambiano insieme cornice e contenuto."""
    from PyQt6.QtWidgets import QLabel

    _in_italian(monkeypatch)
    win = _FinestraFinta(QLabel())
    win._set_status_tn(
        "main_window.abandoned_status",
        25,
        file=1,
        error={"code": "ip_check_failed", "params": {"error": "timeout"}},
    )
    assert win._status_lbl.text() == (
        "File 1 abbandonato dopo 25 tentativi: IP check fallito: timeout"
    )

    TR.set_preference("en")
    win._refresh_status()
    assert win._status_lbl.text() == (
        "File 1 abandoned after 25 attempts: IP check failed: timeout"
    )


def test_setup_status_line_follows_language(qapp, isolated_prefs, monkeypatch):
    """Le righe di stato dell'orchestrator ora hanno una chiave: `_set_status()`
    grezzo non serve piu' per loro."""
    from PyQt6.QtWidgets import QLabel

    _in_italian(monkeypatch)
    win = _FinestraFinta(QLabel())
    win._set_status_t("setup.validating", n=1200)
    assert win._status_lbl.text() == "Validazione di 1200 proxy contro Mega..."

    TR.set_preference("en")
    win._refresh_status()
    assert win._status_lbl.text() == "Validating 1200 proxies against Mega..."
