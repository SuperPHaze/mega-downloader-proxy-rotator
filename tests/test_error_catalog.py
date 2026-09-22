# Test del meccanismo dei codici d'errore (E1).
#
# Coprono le tre garanzie che rendono sicura questa fase:
#   1. nessun codice orfano, nei due sensi (catalogo <-> codice reale);
#   2. `format_it` non solleva MAI, qualunque cosa gli si passi: gira dentro la
#      gestione degli errori, dove un'eccezione maschererebbe l'errore vero;
#   3. il comportamento del motore e' invariato: le classi restano ciò che
#      erano e i rami `except` del worker catturano esattamente come prima.
#
# Più il vincolo che governa tutta la fase: i LOG restano italiani anche con
# l'interfaccia in inglese.
#
# Tutto offline: nessuna rete, nessuna scrittura nel progetto.
import ast
import json
import pathlib

import pytest

from src.core.disk import InsufficientDiskSpaceError
from src.core.error_catalog import ERROR_TEXTS_IT, UNEXPECTED
from src.core.errors import (
    UserFacingError,
    UserFacingOSError,
    UserFacingRuntimeError,
    UserFacingValueError,
    error_payload,
    format_it,
)
from src.downloader.mega_api import MegaApiError
from src.downloader.mega_client import MegaCryptoDependencyError
from src.downloader.mega_folder import MegaFolderError

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACCHETTI = ("src/core", "src/downloader")

# Le classi che portano un codice: un `raise` di una di queste DEVE avere come
# primo argomento un codice del catalogo, mai una frase scritta a mano.
CLASSI_CON_CODICE = frozenset({
    "UserFacingError",
    "UserFacingValueError",
    "UserFacingRuntimeError",
    "UserFacingOSError",
    "MegaApiError",
    "MegaFolderError",
    "MegaCryptoDependencyError",
    "InsufficientDiskSpaceError",
})

# I `raise` che restano con un testo libero: NON sono errori che l'utente
# legge, sono violazioni di contratto interno (se un utente le vede è un bug
# nostro). Elencarli qui significa che aggiungerne uno nuovo fa fallire il
# test invece di passare inosservato.
CONTRATTI_INTERNI = {
    ("core/file_naming.py", "rel_path vuoto"),
    ("core/mega_links.py", "folder_id, node_handle e node_key_b64 sono obbligatori"),
    ("core/mega_links.py", "rel_path non puo' essere vuoto"),
    ("downloader/mega_api.py", "formato proxy non riconosciuto: {}"),
    # Non e' un errore dell'utente ma il contratto dei flussi Python: un
    # flusso senza descrittore lo DICE invece di inventarne uno (avvio
    # silenzioso con pythonw.exe, dove non esiste console).
    (
        "core/logging_setup.py",
        "nessun descrittore: processo senza console (pythonw)",
    ),
    # Chiave di manutenzione non prevista: la passa il codice, non l'utente —
    # le voci sono una costante del modulo (`maintenance.ITEMS`). Se un utente
    # vedesse questo messaggio sarebbe un bug nostro, non un errore d'uso.
    ("core/maintenance.py", "voce di manutenzione sconosciuta: {}"),
}


def _moduli():
    for pkg in PACCHETTI:
        for path in sorted((ROOT / pkg).glob("*.py")):
            yield f"{pkg.split('/')[1]}/{path.name}", ast.parse(
                path.read_text(encoding="utf-8")
            )


def _testo_arg(node) -> str | None:
    """Il primo argomento come stringa: letterale, oppure f-string ridotta a
    forma canonica (`{}` al posto delle espressioni) per poterla confrontare."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parti = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parti.append(str(v.value))
            else:
                parti.append("{}")
        return "".join(parti)
    return None


# ---- 1. nessun codice orfano ----------------------------------------------

def test_ogni_raise_con_codice_usa_un_codice_noto():
    """Un `raise MegaApiError("una frase italiana")` tornerebbe a scrivere il
    testo al punto di sollevamento: e' esattamente cio' che questa fase toglie."""
    fuori_catalogo = []
    for modulo, tree in _moduli():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            nome = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if nome not in CLASSI_CON_CODICE:
                continue
            arg = node.exc.args[0] if node.exc.args else None
            code = arg.value if isinstance(arg, ast.Constant) else None
            if code not in ERROR_TEXTS_IT:
                fuori_catalogo.append((modulo, node.lineno, ast.dump(arg)[:60] if arg else None))
    assert not fuori_catalogo, fuori_catalogo


def _codici_realmente_usati() -> set[str]:
    """I codici consumati davvero, letti dall'AST nelle POSIZIONI in cui un
    codice viene usato:

      - `raise <ClasseConCodice>("code", ...)`      -> primo argomento
      - `format_it("code", {...})`                  -> primo argomento
      - `self._emit_failed(ciclo, tentativo, "code", params)` -> terzo

    Non una ricerca testuale: `"pool_empty"` compare anche come nome di evento
    telemetrico in `parallel_client.py`, e una ricerca grezza lo conterebbe come
    uso del catalogo anche se nessuno lo usasse piu'.
    """
    usati: set[str] = set()

    def aggiungi(arg):
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            usati.add(arg.value)

    for _modulo, tree in _moduli():
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                func = node.exc.func
                nome = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if nome in CLASSI_CON_CODICE and node.exc.args:
                    aggiungi(node.exc.args[0])
            elif isinstance(node, ast.Call):
                func = node.func
                nome = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if nome == "format_it" and node.args:
                    aggiungi(node.args[0])
                elif nome == "_emit_failed" and len(node.args) >= 3:
                    aggiungi(node.args[2])
    return usati


def test_nessun_codice_del_catalogo_e_morto():
    """L'altro senso: una voce che nessuno usa piu' e' peso morto, e in E2
    diventerebbe una chiave da tradurre per niente."""
    usati = _codici_realmente_usati()
    orfani = [
        code for code in ERROR_TEXTS_IT
        # `unexpected` si usa attraverso la costante UNEXPECTED, non come letterale.
        if code != UNEXPECTED and code not in usati
    ]
    assert not orfani, orfani


def test_il_rilevamento_dei_codici_morti_non_si_fa_ingannare():
    """Guardia sul test qui sopra: deve guardare le POSIZIONI d'uso, non
    cercare la stringa ovunque. `"pool_empty"` esiste anche come nome di evento
    telemetrico: se il rilevamento fosse testuale, quel codice risulterebbe
    vivo anche dopo averne tolto l'unico uso vero."""
    sorgenti = "\n".join(
        p.read_text(encoding="utf-8")
        for pkg in PACCHETTI
        for p in sorted((ROOT / pkg).glob("*.py"))
        if p.name != "error_catalog.py"
    )
    # La collisione c'e' davvero: la stringa compare piu' volte...
    assert sorgenti.count('"pool_empty"') > 1
    # ...ma come CODICE la usa un punto solo, e il rilevamento lo distingue.
    usati = _codici_realmente_usati()
    assert "pool_empty" in usati
    assert "telemetry" not in usati and "re_resolve" not in usati


def test_i_raise_con_testo_libero_sono_solo_i_contratti_interni():
    """Gli unici messaggi ancora scritti a mano sono violazioni di contratto
    interno. Se ne compare uno nuovo, o e' user-facing (va codificato) o va
    aggiunto qui di proposito."""
    liberi = set()
    for modulo, tree in _moduli():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            nome = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if nome in CLASSI_CON_CODICE:
                continue
            testo = _testo_arg(node.exc.args[0]) if node.exc.args else None
            if testo is not None:
                liberi.add((modulo, testo))
    assert liberi == CONTRATTI_INTERNI


# ---- 2. format_it non solleva mai ------------------------------------------

def test_ogni_codice_si_rende_senza_segnaposto_residui():
    """Ogni voce del catalogo, con parametri finti, produce testo completo."""
    import re

    nomi = re.compile(r"\{(\w+)")
    for code, template in ERROR_TEXTS_IT.items():
        params = {}
        for nome in set(nomi.findall(template)):
            # I numerici hanno specificatori di formato (`:,`, `:.1f`) che su
            # una stringa esploderebbero: si passa un numero.
            params[nome] = 1234.5 if f"{{{nome}:" in template else f"<{nome}>"
        reso = format_it(code, params)
        assert "{" not in reso and "}" not in reso, (code, reso)


def test_codice_sconosciuto_non_solleva_e_resta_leggibile():
    # Un `raise MegaApiError("frase libera")` rimasto in giro deve continuare a
    # comportarsi come prima, non mostrare un vuoto.
    assert format_it("questo codice non esiste", {}) == "questo codice non esiste"
    exc = MegaApiError("cartella non accessibile o scaduta")
    assert str(exc) == "cartella non accessibile o scaduta"


def test_parametri_mancanti_non_sollevano():
    reso = format_it("disk_full", {"path": "D:/x"})   # mancano gli altri
    assert isinstance(reso, str) and reso            # niente eccezione, testo diagnosticabile


def test_parametro_di_troppo_non_solleva():
    assert format_it("folder_no_nodes", {"inatteso": 1}) == ERROR_TEXTS_IT["folder_no_nodes"]


# ---- 3. il payload trasportabile ------------------------------------------

def test_payload_di_un_errore_nostro():
    exc = MegaApiError("api_error_code", api_code=-9)
    assert error_payload(exc) == {"code": "api_error_code", "params": {"api_code": -9}}


def test_payload_di_un_errore_non_nostro():
    """`requests`, `OSError` grezzi e i contratti interni non hanno codice: il
    ripiego evita che la GUI resti senza niente da rendere."""
    payload = error_payload(ConnectionError("connessione rifiutata"))
    assert payload["code"] == UNEXPECTED
    assert payload["params"]["error"] == "connessione rifiutata"
    assert format_it(payload["code"], payload["params"]) == "connessione rifiutata"


def test_payload_e_una_copia_dei_parametri():
    """Il payload viaggia su un segnale Qt: non deve restare legato al dict
    dell'eccezione."""
    exc = MegaApiError("api_error_code", api_code=-9)
    payload = error_payload(exc)
    payload["params"]["api_code"] = 999
    assert exc.params["api_code"] == -9


# ---- 4. il comportamento del motore NON cambia ----------------------------

@pytest.mark.parametrize(
    "cls, base",
    [
        (MegaApiError, Exception),
        (MegaFolderError, MegaApiError),
        (MegaCryptoDependencyError, RuntimeError),
        (InsufficientDiskSpaceError, OSError),
        (UserFacingValueError, ValueError),
        (UserFacingRuntimeError, RuntimeError),
        (UserFacingOSError, OSError),
    ],
)
def test_le_classi_restano_cio_che_erano(cls, base):
    """I rami `except` del worker discriminano fatale / abbandono / ritenta
    proprio su queste classi: cambiarne la parentela cambierebbe il
    comportamento del motore senza cambiare un solo testo."""
    assert issubclass(cls, base)
    assert issubclass(cls, UserFacingError)


def test_ordine_dei_rami_except_del_worker_invariato():
    """La matrice comportamentale, per costruzione e non a campione: si
    riproduce l'ordine reale dei rami di `_run_cycle_until_success`."""
    def ramo(exc):
        try:
            raise exc
        except (MegaCryptoDependencyError, ImportError):
            return "fatale"
        except InsufficientDiskSpaceError:
            return "abbandono"
        except Exception:
            return "ritenta"

    casi = [
        (MegaCryptoDependencyError("crypto_missing", error="x"), "fatale"),
        (ImportError("No module named 'Crypto'"), "fatale"),
        (InsufficientDiskSpaceError(
            "disk_full", path="D:/x", required=2, needed_bytes=1,
            margin_bytes=1, free=0), "abbandono"),
        (MegaApiError("url_not_parsable", url="x"), "ritenta"),
        (MegaFolderError("folder_no_nodes"), "ritenta"),
        (UserFacingRuntimeError("chunk_cancelled", chunk=1), "ritenta"),
        (UserFacingValueError("crypto_file_key_short", words=2), "ritenta"),
        (RuntimeError("boom"), "ritenta"),
        (OSError("disco staccato"), "ritenta"),
    ]
    for exc, atteso in casi:
        assert ramo(exc) == atteso, type(exc).__name__


def test_le_chiavi_di_nodo_illeggibili_restano_saltabili():
    """`mega_folder` salta le voci di `k` non decifrabili con
    `except (ValueError, TypeError)`. Se le eccezioni di `mega_crypto`
    smettessero di essere ValueError, un file con piu' chiavi candidate
    verrebbe scartato invece che recuperato."""
    from src.downloader.mega_crypto import decrypt_key

    with pytest.raises(ValueError):
        decrypt_key((1, 2, 3), (1, 2, 3, 4))          # chiave a 3 word


def test_insufficient_disk_space_resta_costruibile_e_leggibile():
    exc = InsufficientDiskSpaceError(
        "disk_full", path="D:/scaricati", required=1048576,
        needed_bytes=1000000, margin_bytes=48576, free=4096,
    )
    assert isinstance(exc, OSError)
    assert exc.errno is None            # come prima: un solo argomento, nessun errno
    assert str(exc) == (
        "spazio su disco insufficiente in 'D:/scaricati': "
        "servono 1,048,576 B (file 1,000,000 + margine 48,576), liberi 4,096 B"
    )


# ---- 5. i log restano italiani --------------------------------------------

def test_core_non_importa_la_gui():
    """La garanzia strutturale che tiene i log in italiano: il motore non ha
    modo di chiedere alla GUI in che lingua stia parlando."""
    colpevoli = []
    for modulo, tree in _moduli():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src.gui"):
                colpevoli.append((modulo, node.lineno))
            elif isinstance(node, ast.Import):
                colpevoli += [
                    (modulo, node.lineno) for a in node.names
                    if a.name.startswith("src.gui")
                ]
    assert not colpevoli, colpevoli


def test_il_testo_degli_errori_resta_italiano_con_la_gui_in_inglese():
    pytest.importorskip("PyQt6.QtWidgets")
    from src.gui.i18n import TR

    pref, lang = TR.preference(), TR.language()
    TR._preference, TR._language = "en", "en"
    try:
        assert format_it("folder_no_nodes", {}) == "la cartella non ha restituito alcun nodo"
        assert str(MegaApiError("url_not_parsable", url="x")) == "URL Mega non parsabile: x"
    finally:
        TR._preference, TR._language = pref, lang


def test_failed_links_log_scrive_italiano_con_la_gui_in_inglese(tmp_path, monkeypatch):
    """Il vincolo principale della fase, verificato sul file vero: un abbandono
    con l'interfaccia in inglese lascia in `failed_links.log` la frase italiana."""
    pytest.importorskip("PyQt6.QtWidgets")
    import logging

    from src.core import failed_log
    from src.gui.i18n import TR

    # Log isolato in tmp_path: nessuna scrittura in logs/ del progetto.
    logger = logging.getLogger("failed_links")
    vecchi = list(logger.handlers)
    for h in vecchi:
        logger.removeHandler(h)
    monkeypatch.setattr(failed_log, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(failed_log, "_initialized", False)

    pref, lang = TR.preference(), TR.language()
    TR._preference, TR._language = "en", "en"
    try:
        # Il testo che il worker produce quando abbandona dopo il cap.
        last_error = format_it(
            "download_failed",
            {"error": format_it("chunks_failed", {
                "failed": 2, "total": 57,
                "detail": format_it("chunk_too_slow", {
                    "chunk": 12, "kbps": 98.3, "min_kbps": 200.0, "window_s": 15.0,
                }),
            })},
        )
        failed_log.log_failed_link(0, "https://mega.nz/file/AAA#k", 25, last_error)
        for h in logging.getLogger("failed_links").handlers:
            h.flush()
        righe = (tmp_path / "failed_links.log").read_text(encoding="utf-8").splitlines()
    finally:
        TR._preference, TR._language = pref, lang
        for h in list(logging.getLogger("failed_links").handlers):
            logging.getLogger("failed_links").removeHandler(h)
            h.close()
        for h in vecchi:
            logger.addHandler(h)

    assert len(righe) == 1
    record = json.loads(righe[0])
    assert record["attempts"] == 25
    assert record["last_error"] == (
        "download fallito: 2/57 chunk falliti: "
        "chunk 12: proxy troppo lento (98.3 KB/s < 200 KB/s per 15s)"
    )


# ---- 6. il catalogo e' ben formato ----------------------------------------

def test_nessun_segnaposto_posizionale_nel_catalogo():
    """Come per i dizionari della GUI: i parametri sono sempre nominati,
    altrimenti in inglese non si potrebbe riordinare la frase."""
    import re

    for code, template in ERROR_TEXTS_IT.items():
        assert "{}" not in template, code
        assert not re.search(r"\{\d", template), code
