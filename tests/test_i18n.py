# Test del motore i18n della GUI (offline, nessuna rete).
# Coprono i punti del piano MyDocs/i18n-gui-2.0.0-design.md §3 "test necessari"
# relativi alla fase F1: parita' chiavi/parametri IT<->EN, rilevamento dal
# locale, precedenza della preferenza, chiave mancante, ritraduzione a caldo.
# I plurali per-chiave si testano in F2 (nessuna voce plurale esiste ancora):
# qui si verifica solo che il meccanismo di `tn()` funzioni.
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from src.gui import i18n, preferences
from src.gui.controls import ControlsBar
from src.gui.i18n import TR, Translator, language_from_locale_name, t, tn
from src.gui.strings_en import STRINGS as STRINGS_EN
from src.gui.strings_it import STRINGS as STRINGS_IT

_PARAM_RE = re.compile(r"\{(\w+)\}")


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
