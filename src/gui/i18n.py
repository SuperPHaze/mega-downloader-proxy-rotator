# Motore di traduzione della GUI (IT/EN).
#
# Perche' un modulo proprio e non `tr()` + .ts/.qm di Qt: il progetto si
# distribuisce senza compilare (scompatta lo zip -> install.ps1 -> avvia.bat) e
# nel venv non c'e' `lrelease`. I dizionari sono Python normale, quindi l'EN si
# scrive e si rilegge come si fa gia' con README.it.md -> README.md, e la parita'
# IT<->EN si verifica con un test offline. Vedi MyDocs/i18n-gui-2.0.0-design.md §2.
#
# Il cambio a caldo e' il gemello di quello del tema (`style.apply_theme` +
# `CURRENT_PALETTE`): `TR` e' un singleton di modulo, chi ha testo a video si
# collega a `TR.language_changed` e riesegue i propri `setText()` in un metodo
# `retranslate()`.
#
# Ambito: SOLO l'interfaccia. I log restano in italiano (sono diagnostici e
# devono restare stabili): non tradurre i messaggi passati al logging.
from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QCoreApplication,
    QLibraryInfo,
    QLocale,
    QObject,
    QTranslator,
    pyqtSignal,
)

from src.gui.preferences import load_language, save_language
from src.gui.strings_en import STRINGS as _STRINGS_EN
from src.gui.strings_it import STRINGS as _STRINGS_IT

log = logging.getLogger(__name__)

# Lingua sorgente: e' anche il fallback quando una chiave manca nell'altra.
SOURCE_LANGUAGE = "it"
FALLBACK_LANGUAGE = "en"          # locale di sistema non italiano -> inglese
LANGUAGES = ("it", "en")
PREFERENCES = ("auto", "it", "en")

_TABLES: dict[str, dict[str, object]] = {"it": _STRINGS_IT, "en": _STRINGS_EN}

# Chiavi gia' segnalate: il WARNING esce UNA volta per chiave, altrimenti una
# stringa mancante in un pannello ridisegnato a ogni tick allagherebbe il log.
_warned_keys: set[str] = set()


def _warn_once(key: str, msg: str, *args: object) -> None:
    if key in _warned_keys:
        return
    _warned_keys.add(key)
    log.warning(msg, *args)


def language_from_locale_name(locale_name: str) -> str:
    """Lingua effettiva a partire dal nome di un locale ('it_IT' -> 'it').

    Funzione pura (niente Qt, niente I/O): e' il punto testabile del
    rilevamento. Tutto cio' che non e' italiano ricade su `en`.
    """
    prefix = (locale_name or "").split("_", 1)[0].strip().lower()
    return SOURCE_LANGUAGE if prefix == SOURCE_LANGUAGE else FALLBACK_LANGUAGE


def detect_system_language() -> str:
    """Lingua rilevata dal locale di sistema. Non solleva mai."""
    try:
        return language_from_locale_name(QLocale.system().name())
    except Exception:      # pragma: no cover - difensivo: Qt senza locale
        log.warning("Locale di sistema non leggibile, uso '%s'", FALLBACK_LANGUAGE)
        return FALLBACK_LANGUAGE


def normalize_preference(pref: object) -> str:
    """Preferenza valida ('auto'|'it'|'en'). Qualunque altro valore -> 'auto'."""
    value = str(pref or "").strip().lower()
    return value if value in PREFERENCES else "auto"


class Translator(QObject):
    """Lingua corrente dell'interfaccia + notifica di cambio.

    `preference()` e' cio' che l'utente ha scelto ('auto' compreso),
    `language()` e' la lingua EFFETTIVA in uso e non vale mai 'auto'.
    """

    language_changed = pyqtSignal(str)      # 'it' | 'en' (lingua EFFETTIVA)

    def __init__(self) -> None:
        super().__init__()
        # Nessuna lettura da disco qui: il singleton nasce all'import del modulo,
        # la preferenza persistita si applica con initialize() da src/main.py.
        self._preference = "auto"
        self._language = detect_system_language()
        self._qt_translator: QTranslator | None = None

    # ---- stato -------------------------------------------------------------

    def language(self) -> str:
        """Lingua effettiva in uso ('it' | 'en')."""
        return self._language

    def preference(self) -> str:
        """Preferenza dell'utente ('auto' | 'it' | 'en')."""
        return self._preference

    def detected_language(self) -> str:
        """Lingua che 'auto' sceglierebbe adesso (per l'etichetta del selettore)."""
        return detect_system_language()

    # ---- avvio e cambio lingua ---------------------------------------------

    def initialize(self) -> None:
        """Applica la preferenza persistita. Da chiamare UNA volta all'avvio,
        prima di costruire la finestra: non persiste nulla e non emette il
        segnale (non c'e' ancora niente da ritradurre)."""
        self._preference = normalize_preference(load_language())
        self._language = self._resolve(self._preference)
        self._install_qt_translator()
        log.info("Lingua GUI: %s (preferenza: %s)", self._language, self._preference)

    def set_preference(self, pref: str) -> None:
        """Cambia la preferenza: risolve 'auto', persiste, ricarica il .qm di Qt
        ed emette `language_changed` se la lingua EFFETTIVA cambia."""
        new_pref = normalize_preference(pref)
        if new_pref != str(pref or "").strip().lower():
            log.warning("Preferenza lingua non valida (%r), uso 'auto'", pref)
        self._preference = new_pref
        save_language(new_pref)
        new_lang = self._resolve(new_pref)
        if new_lang == self._language:
            return
        self._language = new_lang
        self._install_qt_translator()
        log.info("Lingua GUI cambiata: %s (preferenza: %s)", new_lang, new_pref)
        self.language_changed.emit(new_lang)

    def _resolve(self, pref: str) -> str:
        return pref if pref in LANGUAGES else detect_system_language()

    def _install_qt_translator(self) -> None:
        """Carica `qtbase_<lang>.qm` per i testi che genera Qt stessa (bottoni
        dei QMessageBox, menu contestuali di QLineEdit, QFileDialog): nessun
        dizionario nostro puo' tradurli.

        Il path va chiesto a QLibraryInfo, mai scritto a mano: cambia fra il
        venv di sviluppo e la macchina dell'utente. Se il .qm manca si prosegue
        senza - degrado accettabile (testi di Qt in inglese), non un errore.
        """
        app = QCoreApplication.instance()
        if app is None:
            return          # nessuna QApplication (test puri): niente da fare
        translator = QTranslator()
        try:
            base = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            loaded = translator.load(f"qtbase_{self._language}", base)
        except Exception as exc:        # pragma: no cover - difensivo
            log.warning("Traduzioni Qt non caricabili: %s", exc)
            loaded = False
        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
            self._qt_translator = None
        if not loaded:
            log.info(
                "qtbase_%s.qm non disponibile: testi di Qt in inglese",
                self._language,
            )
            return
        app.installTranslator(translator)
        # Riferimento tenuto vivo: un QTranslator raccolto dal GC verrebbe
        # rimosso dall'applicazione e i testi di Qt tornerebbero in inglese.
        self._qt_translator = translator

    # ---- lookup ------------------------------------------------------------

    def entry(self, key: str) -> object | None:
        """Voce grezza del dizionario (stringa o dict dei plurali).

        Chiave assente nella lingua corrente -> si ricade sull'italiano, che e'
        la fonte: una traduzione incompleta mostra testo italiano, mai lo slug.
        """
        value = _TABLES.get(self._language, _STRINGS_IT).get(key)
        if value is not None:
            return value
        if self._language != SOURCE_LANGUAGE:
            fallback = _STRINGS_IT.get(key)
            if fallback is not None:
                _warn_once(
                    key,
                    "Chiave i18n assente in '%s': %s (mostro il testo italiano)",
                    self._language,
                    key,
                )
                return fallback
        return None


TR = Translator()       # singleton di modulo, come CURRENT_PALETTE in style.py


def _format(key: str, text: str, params: dict[str, object]) -> str:
    """Sostituisce i parametri nominati. Un parametro mancante o un refuso nel
    dizionario non deve mai far crashare la GUI: si logga e si mostra il testo
    grezzo."""
    if not params:
        return text
    try:
        return text.format(**params)
    except Exception as exc:
        _warn_once(
            f"{key}#format",
            "Parametri i18n non applicabili a %s (%s): %s",
            key,
            exc,
            text,
        )
        return text


def t(key: str, **params: object) -> str:
    """Testo tradotto per `key`, con parametri SEMPRE nominati.

    Non solleva mai: chiave assente nella lingua corrente -> testo italiano; se
    manca anche in italiano (bug nostro, coperto dal test di parita') -> lo
    slug, unica ultima risorsa diagnosticabile.
    """
    value = TR.entry(key)
    if value is None:
        _warn_once(key, "Chiave i18n sconosciuta: %s", key)
        return key
    if isinstance(value, dict):
        # Voce con forme plurali usata senza `tn()`: si mostra la forma
        # generica invece di un dict a video.
        _warn_once(f"{key}#plural", "Chiave i18n con plurali usata da t(): %s", key)
        value = value.get("other") or value.get("one") or key
    return _format(key, str(value), params)


def tn(key: str, n: int, **params: object) -> str:
    """Come `t()`, ma sceglie la forma singolare/plurale in base a `n`.

    `n` viene passato anche ai parametri, cosi' il dizionario puo' scriverlo
    ({n} link pronti) senza ripeterlo al chiamante. IT ed EN hanno la stessa
    regola (1 / altro): la scelta e' la stessa in entrambe le lingue.
    """
    value = TR.entry(key)
    if value is None:
        _warn_once(key, "Chiave i18n sconosciuta: %s", key)
        return key
    params = {"n": n, **params}
    if isinstance(value, dict):
        form = value.get("one") if n == 1 else value.get("other")
        if form is None:
            form = value.get("other") or value.get("one") or key
        return _format(key, str(form), params)
    # Voce senza forme plurali: e' comunque formattabile con {n}.
    return _format(key, str(value), params)
