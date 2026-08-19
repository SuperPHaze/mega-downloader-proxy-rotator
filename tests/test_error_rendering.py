# Test della resa degli errori e della cronologia nella GUI (E2).
#
# Quattro garanzie, in ordine di importanza:
#
#   1. **Fedelta' lato italiano.** Con la lingua su italiano, ogni testo reso
#      coincide con quello che il motore produce da se' (`format_it`, cioe'
#      `str(exc)`). E' il controllo che dimostra che la traduzione non ha
#      cambiato una virgola di cio' che l'utente leggeva prima.
#   2. **La trappola dell'abbandono.** Il worker usa due formulazioni per la
#      stessa causa — «IP check fallito (…)» per il tentativo, «IP check
#      fallito: …» per l'abbandono — ma il canale `abandoned_detail` porta il
#      codice della PRIMA. Senza l'alias, l'abbandono cambierebbe forma.
#   3. **Annidamento.** Aggregato dei chunk e causa del download vengono resi
#      in profondita': in inglese non deve restare italiano dentro le
#      parentesi (tranne il testo delle librerie di terze parti, che e' gia'
#      inglese anche per un utente italiano).
#   4. **I log restano italiani** anche con l'interfaccia in inglese.
#
# Tutto offline: nessuna rete, nessuna scrittura nel progetto.
import os
import pathlib
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from src.core.error_catalog import ERROR_TEXTS_IT
from src.core.errors import UserFacingRuntimeError, error_payload, format_it
from src.gui import preferences
from src.gui.error_render import (
    ABANDON_ALIASES,
    _COUNT_PARAM,
    render_error,
    resolve_payloads,
)
from src.gui.i18n import TR
from src.gui.jobs_model import JobsModel

ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLACEHOLDER = re.compile(r"\{(\w+)(:[^{}]*)?\}")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _lingua_ripristinata():
    """Il singleton TR e' condiviso: ogni test lo rimette com'era."""
    pref, lang = TR.preference(), TR.language()
    yield
    TR._preference, TR._language = pref, lang


@pytest.fixture
def in_italiano(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    TR._preference, TR._language = "it", "it"


@pytest.fixture
def in_inglese(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    TR._preference, TR._language = "en", "en"


def _parametri_finti(template: str) -> dict:
    """Parametri plausibili per un template del catalogo.

    Gli specificatori di formato contano: `{required:,}` vuole un intero e
    `{kbps:.1f}` un float — passare una stringa solleverebbe, e il ripiego di
    `format_it` restituirebbe il template grezzo nascondendo il problema.
    """
    conteggi = set(_COUNT_PARAM.values())
    params: dict = {}
    for nome, spec in _PLACEHOLDER.findall(template):
        if nome in conteggi:
            params[nome] = 3
        elif not spec:
            params[nome] = f"<{nome}>"
        elif "," in spec:
            params[nome] = 1234567
        else:
            params[nome] = 12.5
    return params


# ---- 1. fedelta': l'italiano reso e' quello del motore ---------------------

@pytest.mark.parametrize("code", sorted(ERROR_TEXTS_IT))
def test_ogni_codice_reso_in_italiano_e_identico_al_motore(code, in_italiano):
    """Per OGNI codice del catalogo: quello che la GUI mostra in italiano e'
    esattamente quello che finisce nei log. Se qualcuno ritocca il testo in un
    solo posto, qui si vede."""
    params = _parametri_finti(ERROR_TEXTS_IT[code])
    assert render_error(code, params) == format_it(code, params)


@pytest.mark.parametrize("code", sorted(ERROR_TEXTS_IT))
def test_ogni_codice_si_rende_in_inglese_senza_segnaposto(code, in_inglese):
    reso = render_error(code, _parametri_finti(ERROR_TEXTS_IT[code]))
    assert "{" not in reso and "}" not in reso, code
    assert reso.strip(), code


# ---- 2. la trappola dell'abbandono ----------------------------------------

_SORGENTE_WORKER = (ROOT / "src" / "downloader" / "worker.py").read_text(
    encoding="utf-8"
)


def _codici_del_worker(pattern: str) -> set[str]:
    return set(re.findall(pattern, _SORGENTE_WORKER, re.S))


def _codici_emit_failed() -> set[str]:
    """Tutti i codici che il worker manda sul canale `failed`/`failed_detail`."""
    return _codici_del_worker(r"_emit_failed\(\s*[^)]*?\"(\w+)\"")


def _codici_last_error() -> set[str]:
    """Tutti i codici che il worker usa per `_last_error_msg`, cioe' per la
    frase dell'ABBANDONO.

    Due forme: diretta (`_last_error_msg = format_it("x", ...)`) e indiretta
    (`msg = format_it("x", ...)` seguito da `self._last_error_msg = msg`, come
    nel ramo del disco pieno). Guardarne una sola lascerebbe scoperto proprio
    il caso che si presenta scrivendo un ramo nuovo sul modello di quello.
    """
    codici = _codici_del_worker(r"_last_error_msg = format_it\(\"(\w+)\"")
    righe = _SORGENTE_WORKER.splitlines()
    for i, riga in enumerate(righe):
        m = re.search(r"\bmsg = format_it\(\"(\w+)\"", riga)
        if m is None:
            continue
        # Solo se quel `msg` finisce davvero in `_last_error_msg`: lo stesso
        # nome lo usano anche il ramo fatale e quello del limite di tempo, che
        # sui due canali mandano gia' lo stesso codice.
        if re.search(r"_last_error_msg = msg\b", "\n".join(righe[i:i + 8])):
            codici.add(m.group(1))
    return codici


def test_ogni_codice_di_tentativo_ha_la_sua_frase_di_abbandono():
    """L'invariante su cui poggia `ABANDON_ALIASES`: ogni codice che il worker
    manda su `failed_detail`, passato per l'alias, deve essere uno dei codici
    che il worker usa per la frase dell'abbandono. Se qualcuno aggiunge un ramo
    con una formulazione nuova, qui si vede — invece di scoprirlo a video."""
    emessi = _codici_emit_failed()
    abbandono = _codici_last_error()
    assert emessi, "nessun _emit_failed trovato: la regex non regge piu'"
    assert abbandono, "nessun _last_error_msg trovato: la regex non regge piu'"
    assert {ABANDON_ALIASES.get(c, c) for c in emessi} <= abbandono
    # E nessun codice d'abbandono resta senza un tentativo che lo produca,
    # tranne quelli emessi direttamente (limite di tempo, motivo sconosciuto).
    assert abbandono - {ABANDON_ALIASES.get(c, c) for c in emessi} == set()


def test_alias_abbandono_riporta_la_formulazione_del_worker(in_italiano):
    """IL test della trappola: il codice del canale `failed`, passato per
    l'alias, deve rendere ESATTAMENTE la frase che il worker mette in
    `_last_error_msg` — quella coi due punti, non quella fra parentesi."""
    coppie = {
        "pool_empty_short": "pool_empty",
        "ip_check_failed_paren": "ip_check_failed",
        "download_failed_paren": "download_failed",
        "disk_full_short": "disk_full_short",     # stesso codice sui due canali
    }
    assert coppie.keys() == _codici_emit_failed()
    for codice_detail, codice_msg in coppie.items():
        assert ABANDON_ALIASES.get(codice_detail, codice_detail) == codice_msg
        params = _parametri_finti(ERROR_TEXTS_IT[codice_detail])
        atteso = format_it(codice_msg, params)
        assert render_error(
            ABANDON_ALIASES.get(codice_detail, codice_detail), params
        ) == atteso


def test_nessun_alias_orfano():
    """Un alias che non corrisponde piu' a un codice emesso dal worker e'
    codice morto che nasconde un cambio di comportamento."""
    assert set(ABANDON_ALIASES) <= _codici_emit_failed()


@pytest.mark.parametrize("code", ["disk_full_short", "time_limit_exceeded"])
def test_i_codici_emessi_direttamente_non_hanno_alias(code):
    """Disco pieno e limite di tempo emettono lo STESSO codice sui due canali:
    aliasarli cambierebbe la frase invece di conservarla."""
    assert code not in ABANDON_ALIASES


def test_abbandono_reso_dal_modello_e_identico_a_prima(in_italiano):
    """Fine a fine: il payload che arriva dal canale, passato per l'alias e
    memorizzato nel modello, produce la frase italiana di sempre."""
    params = {"error": "HTTPSConnectionPool(...): timeout"}
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#k"])
    model.mark_abandoned(
        0, 25, ABANDON_ALIASES["ip_check_failed_paren"], params,
    )
    job = model.get_job(0)
    assert render_error(*job.last_error) == (
        "IP check fallito: HTTPSConnectionPool(...): timeout"
    )


# ---- 3. annidamento --------------------------------------------------------

def _errore_annidato() -> Exception:
    """Un fallimento realistico: cornice del download -> aggregato dei chunk
    -> errore del singolo chunk (i tre livelli di §1.3 del progetto)."""
    figli = [
        UserFacingRuntimeError(
            "chunk_too_slow",
            chunk=12, kbps=98.3, min_kbps=200.0, window_s=15.0,
        ),
        UserFacingRuntimeError(
            "chunk_retries_exhausted",
            chunk=30, attempts=3, error="HTTPSConnectionPool(...)",
        ),
    ]
    return UserFacingRuntimeError(
        "chunks_failed",
        failed=len(figli),
        total=57,
        detail="; ".join(str(f) for f in figli),
        children=[error_payload(f) for f in figli],
    )


def test_aggregato_dei_chunk_in_italiano_e_identico_a_str_exc(in_italiano):
    exc = _errore_annidato()
    assert render_error(**error_payload(exc)) == str(exc)


def test_aggregato_dei_chunk_in_inglese_non_lascia_italiano(in_inglese):
    reso = render_error(**error_payload(_errore_annidato()))
    assert "chunk falliti" not in reso
    assert "troppo lento" not in reso
    assert "tentativi" not in reso
    assert reso.startswith("2/57 chunks failed:")
    assert "proxy too slow" in reso


def test_cornice_del_download_in_italiano_e_identica_a_str_exc(in_italiano):
    """La cornice «download fallito (…)» del worker: `cause` porta il payload,
    `error` la stringa. In italiano i due devono coincidere."""
    exc = _errore_annidato()
    params = {"error": str(exc), "cause": error_payload(exc)}
    assert render_error("download_failed_paren", params) == format_it(
        "download_failed_paren", {"error": str(exc)}
    )


def test_cornice_del_download_in_inglese_rende_anche_la_causa(in_inglese):
    exc = _errore_annidato()
    reso = render_error(
        "download_failed_paren", {"error": str(exc), "cause": error_payload(exc)}
    )
    assert reso.startswith("download failed (2/57 chunks failed:")
    assert "chunk falliti" not in reso


def test_il_testo_delle_librerie_resta_com_e(in_inglese):
    """Un'eccezione non nostra ricade su `unexpected`: il suo testo (gia'
    inglese) passa invariato, come passa oggi anche in italiano."""
    payload = error_payload(ValueError("Max retries exceeded with url: /x"))
    assert render_error(**payload) == "Max retries exceeded with url: /x"


def test_payload_malformato_non_solleva(in_italiano):
    """La resa gira dentro la gestione degli errori: qualunque schifezza
    arrivi, deve uscire una stringa."""
    assert isinstance(render_error("codice_inventato", {"a": 1}), str)
    assert isinstance(render_error("chunks_failed", {"children": "non una lista"}), str)
    assert isinstance(render_error("download_failed_paren", {"cause": 42}), str)
    assert isinstance(render_error("attempt_frame", {}), str)


def test_la_ricorsione_e_limitata(in_italiano):
    """Un payload che si annida all'infinito non deve mandare in ricorsione la
    GUI mentre sta gia' mostrando un errore."""
    payload: dict = {"code": "unexpected", "params": {"error": "fondo"}}
    for _ in range(50):
        payload = {"code": "download_failed_paren", "params": {"cause": payload}}
    assert isinstance(render_error(**payload), str)


# ---- 4. i parametri della riga di stato si rendono al disegno --------------

def test_resolve_payloads_rende_solo_i_payload(in_italiano):
    reso = resolve_payloads({
        "file": 3,
        "error": {"code": "pool_empty", "params": {}},
        "nome": "gia' testo",
    })
    assert reso == {
        "file": 3,
        "error": "pool proxy vuoto, refill in attesa",
        "nome": "gia' testo",
    }


def test_resolve_payloads_segue_la_lingua(in_inglese):
    reso = resolve_payloads({"error": {"code": "pool_empty", "params": {}}})
    assert reso["error"] == "proxy pool empty, refill pending"


# ---- 5. la cronologia del job ---------------------------------------------

def _modello_con_storia() -> JobsModel:
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#k"])
    model.set_progress(0, 1)
    model.set_ip(0, "1.2.3.4")
    model.add_failure(0, "ip_check_failed_paren", {"error": "timeout"})
    return model


def test_il_modello_non_memorizza_testo():
    """`jobs_model` e' un modello di dati: nel log ci sono chiavi e parametri,
    mai frasi gia' composte (e' il motivo per cui non ha `retranslate()`)."""
    job = _modello_con_storia().get_job(0)
    chiavi = [voce[2] for voce in job.all_attempts_log]
    assert chiavi == ["job_log.started", "job_log.ip", "job_log.attempt"]
    assert job.last_error[0] == "attempt_frame"
    assert not hasattr(JobsModel, "retranslate")


def test_le_voci_di_cronologia_in_italiano(in_italiano):
    from src.gui.job_detail_dialog import _render_log

    model = _modello_con_storia()
    model.mark_abandoned(0, 25, "ip_check_failed", {"error": "timeout"})
    righe = [_render_log(voce[2], voce[3]) for voce in model.get_job(0).all_attempts_log]
    assert righe == [
        "Download avviato",
        "IP uscente: 1.2.3.4",
        # Una sola cornice «Tentativo N: ». Prima di E2 ce n'erano DUE, perche'
        # il worker la metteva nella stringa e il modello la rimetteva sopra
        # («Tentativo 1: Tentativo 1: …»): il canale tipato porta il codice
        # nudo e la cornice la mette solo chi disegna.
        "Tentativo 1: IP check fallito (timeout)",
        "Link abbandonato dopo 25 tentativi: IP check fallito: timeout",
    ]


def test_le_voci_di_cronologia_in_inglese(in_inglese):
    from src.gui.job_detail_dialog import _render_log

    model = _modello_con_storia()
    model.mark_abandoned(0, 25, "ip_check_failed", {"error": "timeout"})
    righe = [_render_log(voce[2], voce[3]) for voce in model.get_job(0).all_attempts_log]
    assert righe == [
        "Download started",
        "Egress IP: 1.2.3.4",
        "Attempt 1: IP check failed (timeout)",
        "Link abandoned after 25 attempts: IP check failed: timeout",
    ]


def test_le_altre_voci_di_cronologia_in_italiano(in_italiano):
    from src.gui.job_detail_dialog import _render_log

    model = JobsModel()
    model.reset(["u1", "u2", "u3"])
    model.set_progress(0, 5)
    model.mark_completed(0)
    model.set_progress(1, 5)
    model.mark_failed_fatal(1, "config_error", {"error": "pycryptodome mancante"})
    model.set_progress(2, 5)
    model.mark_cancelled(2)
    model.restart_job(2)
    testi = {
        job.file_id: [_render_log(v[2], v[3]) for v in job.all_attempts_log]
        for job in model.jobs_iter()
    }
    assert testi[0] == ["Download avviato", "Download completato"]
    assert testi[1] == [
        "Download avviato",
        "Errore fatale: Errore di configurazione: pycryptodome mancante",
    ]
    assert testi[2] == [
        "Download avviato",
        "Cancellato dall'utente",
        "----- Riavvio richiesto -----",
    ]


def test_il_livello_del_log_non_si_traduce(in_inglese):
    job = _modello_con_storia().get_job(0)
    assert [voce[1] for voce in job.all_attempts_log] == ["INFO", "INFO", "WARN"]


# ---- 6. la riga di stato del setup ----------------------------------------

def test_le_righe_di_stato_del_setup_hanno_lo_stesso_italiano():
    """Il testo italiano del setup esiste in due copie — nell'orchestrator (per
    log e CLI) e nei dizionari (per la GUI) — perche' `downloader` non puo'
    importare `gui`. Qui si verifica che non divergano."""
    from src.downloader.orchestrator import SETUP_TEXTS_IT
    from src.gui.strings_it import STRINGS

    for code, testo in SETUP_TEXTS_IT.items():
        assert STRINGS[f"setup.{code}"] == testo, code


def test_ogni_riga_di_stato_emessa_dal_setup_ha_la_sua_chiave():
    """Un codice emesso e non tradotto mostrerebbe lo slug a video."""
    from src.downloader import orchestrator as orch
    from src.gui.strings_it import STRINGS

    sorgente = (ROOT / "src" / "downloader" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    emessi = set(re.findall(r"self\._(?:status|fail)\(\"(\w+)\"", sorgente))
    emessi |= set(re.findall(r"setup_text_it\(\"(\w+)\"", sorgente))
    assert emessi
    for code in emessi:
        assert code in orch.SETUP_TEXTS_IT, code
        assert f"setup.{code}" in STRINGS, code


def test_setup_text_it_non_solleva():
    from src.downloader.orchestrator import setup_text_it

    assert setup_text_it("codice_inventato", {}) == "codice_inventato"
    assert setup_text_it("validating", {}) == "Validazione di {n} proxy contro Mega..."
    assert setup_text_it("validating", {"n": 7}) == "Validazione di 7 proxy contro Mega..."


# ---- 7. il payload sopravvive al viaggio fra i thread ----------------------
#
# `pyqtSignal(..., dict)` marshalla il dizionario attraverso QVariant quando la
# connessione e' in coda (worker -> GUI). Un payload annidato — dict dentro
# dict, lista di dict — e' proprio il caso in cui un appiattimento passerebbe
# inosservato nei test in-process e romperebbe solo a video, in produzione.

def test_il_payload_annidato_sopravvive_a_una_connessione_in_coda(qapp):
    from PyQt6.QtCore import QObject, Qt, pyqtSignal

    class Sorgente(QObject):
        detail = pyqtSignal(int, int, str, dict)

    ricevuti: list[tuple] = []
    sorgente = Sorgente()
    sorgente.detail.connect(
        lambda fid, ciclo, code, params: ricevuti.append((fid, ciclo, code, params)),
        Qt.ConnectionType.QueuedConnection,
    )
    exc = _errore_annidato()
    payload = {"error": str(exc), "cause": error_payload(exc)}
    sorgente.detail.emit(0, 1, "download_failed_paren", payload)
    qapp.processEvents()

    assert len(ricevuti) == 1
    _, _, code, params = ricevuti[0]
    assert code == "download_failed_paren"
    assert isinstance(params["cause"], dict)
    assert isinstance(params["cause"]["params"]["children"], (list, tuple))
    assert params["cause"]["params"]["children"][0]["code"] == "chunk_too_slow"
    # I numeri devono restare numeri: `{kbps:.1f}` su una stringa solleverebbe.
    assert params["cause"]["params"]["children"][0]["params"]["kbps"] == 98.3


def test_il_payload_marshallato_si_rende_come_l_originale(qapp, in_italiano):
    from PyQt6.QtCore import QObject, Qt, pyqtSignal

    class Sorgente(QObject):
        detail = pyqtSignal(str, dict)

    resi: list[str] = []
    sorgente = Sorgente()
    sorgente.detail.connect(
        lambda code, params: resi.append(render_error(code, params)),
        Qt.ConnectionType.QueuedConnection,
    )
    exc = _errore_annidato()
    sorgente.detail.emit(
        "download_failed_paren", {"error": str(exc), "cause": error_payload(exc)}
    )
    qapp.processEvents()
    assert resi == [format_it("download_failed_paren", {"error": str(exc)})]


# ---- 8. il cablaggio orchestrator -> GUI regge le firme -------------------

def test_i_canali_tipati_arrivano_al_pannello(qapp, in_italiano):
    """Una firma sbagliata non si vede alla `connect()` ma all'emissione: qui
    i tre canali dell'orchestrator vengono davvero percorsi fino al modello."""
    from PyQt6.QtCore import Qt

    from src.core.state import SessionState
    from src.downloader.orchestrator import DownloadOrchestrator
    from src.gui.jobs_panel import JobsPanel

    orch = DownloadOrchestrator(SessionState())
    panel = JobsPanel()
    panel.reset(["u1", "u2", "u3"])
    qc = Qt.ConnectionType.QueuedConnection
    orch.failed_detail.connect(panel.on_failed, qc)
    orch.fatal_detail.connect(panel.on_fatal, qc)
    orch.abandoned_detail.connect(panel.on_abandoned, qc)

    orch.failed_detail.emit(0, 1, "pool_empty_short", {})
    orch.fatal_detail.emit(1, "config_error", {"error": "pycryptodome mancante"})
    orch.abandoned_detail.emit(
        2, "u3", 25, "download_failed_paren", {"error": "boom"},
    )
    qapp.processEvents()

    assert render_error(*panel.model.get_job(0).last_error) == (
        "Tentativo 1: pool vuoto, attendo refill"
    )
    assert render_error(*panel.model.get_job(1).last_error) == (
        "Errore di configurazione: pycryptodome mancante"
    )
    # L'alias in azione: il codice arriva con le parentesi, la frase esce coi
    # due punti — identica a quella che il worker scrive in failed_links.log.
    assert render_error(*panel.model.get_job(2).last_error) == (
        "download fallito: boom"
    )


def test_i_segnali_stringa_restano_al_loro_posto():
    """I canali che portano la frase italiana non spariscono: li usano i log,
    `failed_links.log`, la telemetria e la CLI."""
    from src.downloader.orchestrator import DownloadOrchestrator
    from src.downloader.worker import DownloadWorker

    for classe in (DownloadWorker, DownloadOrchestrator):
        for nome in ("failed", "fatal_error", "abandoned"):
            assert hasattr(classe, nome), (classe.__name__, nome)
    assert hasattr(DownloadOrchestrator, "setup_status")
    assert hasattr(DownloadOrchestrator, "pool_failed")


# ---- 9. i due contratti impliciti del rendering ---------------------------

def test_nessun_codice_del_catalogo_contiene_un_punto():
    """`_key_for` distingue lo slug del motore (-> `err.<slug>`) dalla chiave
    i18n intera guardando SOLO il punto. Un codice namespaced nel catalogo
    (`"folder.key_invalid"`) verrebbe scambiato per una chiave e mostrerebbe lo
    slug a video: e' un contratto fra `core/error_catalog.py` e questo modulo,
    e va asserito, non sperato."""
    con_punto = [code for code in ERROR_TEXTS_IT if "." in code]
    assert con_punto == []


def test_i_codici_i18n_che_nascono_nella_gui_si_rendono(in_italiano, in_inglese):
    """I due errori che `main_window` passa a `mark_failed_fatal` sono l'unico
    esercizio reale del ramo «codice col punto»: senza un test, una rinomina
    nei dizionari non farebbe fallire nulla e l'utente vedrebbe lo slug."""
    import re as _re

    sorgente = (ROOT / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")
    codici = _re.findall(
        r"mark_failed_fatal\(\s*\n?\s*file_id,\s*\"([\w.]+)\"", sorgente
    )
    assert set(codici) == {
        "main_window.restart_no_orchestrator",
        "main_window.restart_refused",
    }, codici
    for code in codici:
        assert "." in code                       # e' una chiave, non uno slug
        reso = render_error(code, {})
        assert reso != code, code                # la chiave esiste davvero
        assert "{" not in reso, code


def test_un_codice_sconosciuto_si_mostra_nudo(in_italiano):
    """Ripiego identico a quello del motore (`format_it`): si mostra il codice,
    non `err.<codice>`, che sarebbe rumore nostro sopra un messaggio gia'
    degradato."""
    assert render_error("codice_inventato", {}) == "codice_inventato"
    assert render_error("una frase libera rimasta in giro", {}) == (
        "una frase libera rimasta in giro"
    )


# ---- 10. le voci con forme plurali ----------------------------------------

def test_le_forme_plurali_sono_esattamente_quelle_dichiarate():
    """`_COUNT_PARAM` e i due dizionari devono dire la stessa cosa: una voce
    plurale che il renderer non conosce resterebbe sempre al plurale, e un
    codice dichiarato senza forme farebbe scattare il ripiego di `t()`."""
    from src.gui.strings_en import STRINGS as EN
    from src.gui.strings_it import STRINGS as IT

    dichiarati = {f"err.{code}" for code in _COUNT_PARAM}
    for tabella in (IT, EN):
        con_forme = {
            k for k, v in tabella.items()
            if k.startswith("err.") and isinstance(v, dict)
        }
        assert con_forme == dichiarati


def test_il_parametro_del_conteggio_esiste_nel_template():
    """Se il parametro dichiarato non compare nel testo, la forma verrebbe
    scelta su un numero che l'utente non vede."""
    for code, nome in _COUNT_PARAM.items():
        assert "{" + nome in ERROR_TEXTS_IT[code], code


@pytest.mark.parametrize("code", sorted(_COUNT_PARAM))
def test_le_voci_plurali_in_italiano_restano_il_testo_del_catalogo(code, in_italiano):
    """L'italiano non declina: le due forme sono la frase di sempre. Il test
    lo verifica a n=1 e n=2, che e' dove una svista si vedrebbe."""
    params = _parametri_finti(ERROR_TEXTS_IT[code])
    for n in (1, 2):
        params[_COUNT_PARAM[code]] = n
        assert render_error(code, params) == format_it(code, params)


@pytest.mark.parametrize("code", sorted(_COUNT_PARAM))
def test_le_voci_plurali_in_inglese_declinano(code, in_inglese):
    params = _parametri_finti(ERROR_TEXTS_IT[code])
    params[_COUNT_PARAM[code]] = 1
    uno = render_error(code, params)
    params[_COUNT_PARAM[code]] = 2
    due = render_error(code, params)
    assert uno != due, code
    assert "{" not in uno and "{" not in due, code


def test_time_limit_a_un_minuto(in_inglese):
    """Il caso concreto: il limite di tempo si imposta a partire da 1 minuto
    (`controls.time_limit_spin.setRange(1, 600)`), quindi «1 minutes» sarebbe
    un errore che l'utente vede davvero."""
    assert render_error("time_limit_exceeded", {"minutes": 1}) == (
        "time limit of 1 minute exceeded"
    )
    assert render_error("time_limit_exceeded", {"minutes": 30}) == (
        "time limit of 30 minutes exceeded"
    )


# ---- 11. le cause NOSTRE viaggiano come payload, non come frase ------------
#
# `config_error` e `disk_full_short` incorporano un'eccezione che e' NOSTRA
# (`MegaCryptoDependencyError`, `InsufficientDiskSpaceError`): il loro
# `str(exc)` e' italiano. Se il worker mandasse solo quello, in inglese si
# vedrebbe una cornice inglese attorno a un errore italiano. Il payload viaggia
# quindi accanto al testo, esattamente come per «download fallito».

def _params_worker(code: str, exc: Exception) -> dict:
    """Gli stessi parametri che costruisce `worker.py` per quel codice."""
    return {"error": str(exc), "cause": error_payload(exc)}


def _eccezioni_incorporate():
    from src.core.disk import InsufficientDiskSpaceError
    from src.downloader.mega_client import MegaCryptoDependencyError

    return [
        ("disk_full_short", InsufficientDiskSpaceError(
            "disk_full", path="D:/dl", required=100, needed_bytes=90,
            margin_bytes=10, free=5,
        )),
        ("config_error", MegaCryptoDependencyError(
            "crypto_not_importable", error="No module named 'Crypto'",
        )),
    ]


def test_le_cause_nostre_in_italiano_restano_identiche(in_italiano):
    for code, exc in _eccezioni_incorporate():
        params = _params_worker(code, exc)
        assert render_error(code, params) == format_it(code, {"error": str(exc)})


def test_le_cause_nostre_si_traducono(in_inglese):
    for code, exc in _eccezioni_incorporate():
        reso = render_error(code, _params_worker(code, exc))
        assert str(exc) not in reso, code       # niente italiano incastonato
        assert "spazio su disco" not in reso
        assert "non importabile" not in reso
        assert "{" not in reso


def test_il_worker_manda_la_causa_dove_l_errore_e_nostro():
    """Guardia sul sorgente: i due rami che incorporano un'eccezione NOSTRA
    devono passare anche `cause`. Senza, la traduzione si ferma alla cornice e
    nessun test lo noterebbe (in italiano il testo e' identico comunque)."""
    for code in ("config_error", "disk_full_short"):
        m = re.search(
            r"params = \{[^}]*\}\s*\n\s*msg = format_it\(\"" + code + r"\"",
            _SORGENTE_WORKER,
        )
        assert m is not None, code
        assert '"cause": error_payload(exc)' in m.group(0), code
