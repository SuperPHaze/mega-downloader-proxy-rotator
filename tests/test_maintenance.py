# Test del modulo di manutenzione (core/maintenance.py) e del troncamento dei
# log aperti (core/logging_setup.reset_log_file).
#
# Tutto gira su cartelle temporanee: la suite NON deve toccare i log veri del
# progetto (il difetto per cui alcuni test scrivono in `logs/` e' noto e
# ancora aperto — qui non si peggiora).
import json
import logging
import shutil
from logging.handlers import RotatingFileHandler

import pytest

from src.core import logging_setup, maintenance


# ---- impalcatura: un finto albero di lavoro su tmp_path --------------------

def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Radice finta con `logs/`, `downloads/` e lo stato di sessione.

    Il modulo risolve i percorsi dai propri globali a ogni chiamata, quindi
    sostituirli basta a spostare l'intero modulo su tmp_path."""
    logs = tmp_path / "logs"
    downloads = tmp_path / "downloads"
    logs.mkdir()
    downloads.mkdir()
    monkeypatch.setattr(maintenance, "LOGS_DIR", logs)
    monkeypatch.setattr(maintenance, "OUTPUT_DIR", downloads)
    monkeypatch.setattr(maintenance, "_PROJECT_ROOT", tmp_path)

    # Storico: 3 voci nel log corrente + un archivio ruotato.
    _write(
        logs / "download_history.log",
        "".join(json.dumps({"handle": f"h{i}"}) + "\n" for i in range(3)),
    )
    _write(logs / "download_history.log.1", '{"handle": "vecchio"}\n')

    # Stato della sessione: 2 link in sospeso.
    _write(
        tmp_path / "session_state.json",
        json.dumps({"schema": 1, "urls": ["https://mega.nz/file/A#k",
                                          "https://mega.nz/file/B#k"]}),
    )

    # Log applicativi e statistiche delle fonti.
    _write(logs / "app.log", "riga\n")
    _write(logs / "app.log.1", "vecchia\n")
    _write(logs / "events.jsonl", '{"msg": "x"}\n')
    _write(logs / "terminal-log.txt", "stdout\n")
    _write(logs / "proxy_sources_stats.log", "{}\n")
    _write(logs / "failed_links.log", "{}\n")
    # Diagnostica che NON deve sparire.
    _write(logs / "crash.log", "traccia\n")
    _write(logs / "telemetry" / "sess" / "samples.jsonl", "{}\n")

    # Cartella dei download: 2 file finiti, 1 frammento, in un sottoalbero.
    _write(downloads / "primo_0" / "ciclo_1" / "video.mp4", "x" * 10)
    _write(downloads / "primo_0" / "ciclo_1" / "video2.mp4.part", "y" * 5)
    _write(downloads / "Cartella Mega" / "sub" / "doc.pdf", "z" * 7)
    return tmp_path


# ---- misura ----------------------------------------------------------------

def test_survey_history_counts_records_not_files(workspace):
    survey = maintenance.survey(maintenance.ITEM_HISTORY)
    # 3 voci nel log CORRENTE (gli archivi non li rilegge nessuno)...
    assert survey.count == 3
    # ...ma l'archivio ruotato sparisce insieme, quindi e' nell'elenco.
    assert {p.name for p in survey.paths} == {
        "download_history.log", "download_history.log.1",
    }


def test_survey_session_counts_pending_links(workspace):
    survey = maintenance.survey(maintenance.ITEM_SESSION)
    assert survey.count == 2
    assert [p.name for p in survey.paths] == ["session_state.json"]


def test_survey_downloads_counts_files_parts_and_bytes(workspace):
    survey = maintenance.survey(maintenance.ITEM_DOWNLOADS)
    assert survey.count == 3          # due file finiti + un .part
    assert survey.extra_count == 1    # solo il .part
    assert survey.total_bytes == 10 + 5 + 7
    # I percorsi mostrati sono i figli di primo livello: e' cio' che verra'
    # rimosso, non l'albero intero (sarebbero migliaia di righe a video).
    assert [p.name for p in survey.paths] == ["Cartella Mega", "primo_0"]


def test_survey_logs_excludes_crash_log_and_telemetry(workspace):
    survey = maintenance.survey(maintenance.ITEM_LOGS)
    names = {p.name for p in survey.paths}
    assert "app.log" in names and "app.log.1" in names
    assert "events.jsonl" in names and "terminal-log.txt" in names
    assert "proxy_sources_stats.log" in names and "failed_links.log" in names
    # Diagnostica e storico restano fuori: sono un'altra voce (o non sono
    # dati dell'utente).
    assert "crash.log" not in names
    assert "download_history.log" not in names


def test_survey_is_empty_when_there_is_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(maintenance, "OUTPUT_DIR", tmp_path / "downloads")
    monkeypatch.setattr(maintenance, "_PROJECT_ROOT", tmp_path)
    for key in maintenance.ITEMS:
        assert maintenance.survey(key).is_empty, key


def test_survey_rejects_an_unknown_item():
    with pytest.raises(ValueError):
        maintenance.survey("cartella_dei_gatti")


def test_rotated_siblings_only_matches_numeric_suffixes(tmp_path):
    base = _write(tmp_path / "app.log")
    _write(tmp_path / "app.log.1")
    _write(tmp_path / "app.log.2")
    _write(tmp_path / "app.log.tmp")      # non e' un archivio ruotato
    _write(tmp_path / "app.logging")      # nemmeno questo
    assert [p.name for p in maintenance._rotated_siblings(base)] == [
        "app.log.1", "app.log.2",
    ]


# ---- cancellazione: cancella cio' che deve e NIENT'ALTRO -------------------

def test_clear_history_touches_only_the_history(workspace):
    survey = maintenance.survey(maintenance.ITEM_HISTORY)
    result = maintenance.clear(maintenance.ITEM_HISTORY)

    assert result.ok
    assert result.freed_bytes == survey.total_bytes
    logs = workspace / "logs"
    # Il log corrente resta ma vuoto (nessuno lo tiene aperto qui: viene
    # rimosso); gli archivi spariscono.
    assert not (logs / "download_history.log.1").exists()
    assert maintenance.survey(maintenance.ITEM_HISTORY).count == 0
    # Tutto il resto e' intatto.
    assert (logs / "app.log").exists()
    assert (workspace / "session_state.json").exists()
    assert (workspace / "downloads" / "primo_0").exists()


def test_clear_session_touches_only_the_session_state(workspace):
    result = maintenance.clear(maintenance.ITEM_SESSION)
    assert result.ok
    assert not (workspace / "session_state.json").exists()
    assert (workspace / "logs" / "app.log").exists()
    assert (workspace / "downloads" / "primo_0").exists()


def test_clear_downloads_empties_the_root_but_keeps_it(workspace):
    survey = maintenance.survey(maintenance.ITEM_DOWNLOADS)
    result = maintenance.clear(maintenance.ITEM_DOWNLOADS)

    assert result.ok
    assert result.freed_bytes == survey.total_bytes
    downloads = workspace / "downloads"
    assert downloads.is_dir()             # la cartella resta: la si aspetta
    assert list(downloads.iterdir()) == []
    assert (workspace / "logs" / "app.log").exists()


def test_clear_logs_leaves_crash_log_and_telemetry_alone(workspace):
    result = maintenance.clear(maintenance.ITEM_LOGS)
    assert result.ok
    logs = workspace / "logs"
    assert not (logs / "app.log.1").exists()
    assert maintenance.survey(maintenance.ITEM_LOGS).total_bytes == 0
    assert (logs / "crash.log").read_text(encoding="utf-8") == "traccia\n"
    assert (logs / "telemetry" / "sess" / "samples.jsonl").exists()
    # Lo storico e' una voce a se': non lo porta via il gruppo dei log.
    assert (logs / "download_history.log").exists()


def test_clear_items_runs_only_the_selected_ones(workspace):
    results = maintenance.clear_items(
        [maintenance.ITEM_HISTORY, maintenance.ITEM_SESSION]
    )
    assert [r.key for r in results] == [
        maintenance.ITEM_HISTORY, maintenance.ITEM_SESSION,
    ]
    assert all(r.ok for r in results)
    assert (workspace / "downloads" / "primo_0").exists()
    assert (workspace / "logs" / "app.log").exists()


def test_a_failure_on_one_item_does_not_stop_the_others(workspace, monkeypatch):
    """Requisito esplicito: se una voce fallisce, le altre proseguono e il
    resoconto dice quale non e' riuscita."""
    def _esplode(path, *a, **kw):
        raise OSError("cartella occupata")

    monkeypatch.setattr(shutil, "rmtree", _esplode)
    results = maintenance.clear_items(
        [maintenance.ITEM_DOWNLOADS, maintenance.ITEM_SESSION]
    )
    per_key = {r.key: r for r in results}
    assert not per_key[maintenance.ITEM_DOWNLOADS].ok
    assert "cartella occupata" in per_key[maintenance.ITEM_DOWNLOADS].error
    assert per_key[maintenance.ITEM_SESSION].ok
    assert not (workspace / "session_state.json").exists()


def test_clear_items_ignores_unknown_keys_in_the_selection(workspace):
    """`clear_items` filtra sulla costante ITEMS: una chiave di troppo non
    fa esplodere l'intera operazione."""
    results = maintenance.clear_items(["history", "non_esiste"])
    assert [r.key for r in results] == [maintenance.ITEM_HISTORY]


def test_session_locked_items_are_the_two_destructive_ones():
    assert maintenance.SESSION_LOCKED_ITEMS == {
        maintenance.ITEM_DOWNLOADS, maintenance.ITEM_LOGS,
    }
    # La cache dei proxy NON e' gestita qui (vive in src/proxy/): il modulo di
    # core non puo' importarla.
    assert maintenance.ITEM_PROXY_CACHE not in maintenance.ITEMS


# ---- troncamento dei log APERTI -------------------------------------------

def test_truncating_a_log_held_by_a_live_handler(tmp_path):
    """Il caso vero: su Windows `unlink` su un file aperto fallisce. Il file
    deve ripartire da zero e l'applicazione continuare a scriverci."""
    target = tmp_path / "app.log"
    logger = logging.getLogger("test_manutenzione_troncamento")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(target, maxBytes=5_000_000, backupCount=1,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    try:
        logger.info("prima del troncamento")
        handler.flush()
        assert target.stat().st_size > 0
        freed = logging_setup.reset_log_file(target)

        assert freed > 0
        assert target.exists()                 # troncato, non cancellato
        assert target.stat().st_size == 0
        # E il canale e' ancora vivo: la riga dopo arriva, e da sola.
        logger.info("dopo il troncamento")
        handler.flush()
        contenuto = target.read_text(encoding="utf-8")
        assert contenuto == "dopo il troncamento\n"
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_truncating_a_log_held_by_the_ROOT_logger(tmp_path):
    """Nell'app vera app.log ed events.jsonl stanno sul logger ROOT, non su uno
    con nome: e' il ramo che conta di piu' e va percorso da un test."""
    target = tmp_path / "app.log"
    root = logging.getLogger()
    handler = RotatingFileHandler(target, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    livello = root.level
    root.setLevel(logging.INFO)
    try:
        root.info("prima")
        handler.flush()
        assert target.stat().st_size > 0

        assert logging_setup.reset_log_file(target) > 0
        assert target.stat().st_size == 0

        root.info("dopo")
        handler.flush()
        assert "dopo" in target.read_text(encoding="utf-8")
        assert "prima" not in target.read_text(encoding="utf-8")
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(livello)


def test_clearing_the_history_while_its_own_logger_holds_it(tmp_path, monkeypatch):
    """`logs/download_history.log` e' tenuto aperto dal logger dedicato non
    appena un download si completa: la trappola di Windows vale anche qui, non
    solo per app.log."""
    from src.core import download_history

    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(maintenance, "LOGS_DIR", logs)
    monkeypatch.setattr(download_history, "LOGS_DIR", logs)
    monkeypatch.setattr(download_history, "_initialized", False)
    monkeypatch.setattr(download_history, "_LOGGER_NAME", "download_history_test")
    logger = download_history._setup_logger()
    try:
        download_history.record_completed("h1", "url", "f.bin", 10, "p")
        for h in logger.handlers:
            h.flush()
        assert download_history.load_history()      # c'e' una voce

        result = maintenance.clear(maintenance.ITEM_HISTORY)
        assert result.ok, result.error
        assert download_history.load_history() == {}

        # E il canale scrive ancora: il prossimo download finisce nello storico.
        download_history.record_completed("h2", "url2", "g.bin", 20, "p2")
        for h in logger.handlers:
            h.flush()
        assert list(download_history.load_history()) == ["h2"]
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
            h.close()


def test_reset_log_file_deletes_a_file_nobody_holds_open(tmp_path):
    archivio = _write(tmp_path / "app.log.1", "vecchia riga\n")
    atteso = archivio.stat().st_size     # non len(): su Windows \n diventa \r\n
    freed = logging_setup.reset_log_file(archivio)
    assert freed == atteso > 0
    assert not archivio.exists()


def test_reset_log_file_on_a_missing_file_is_a_no_op(tmp_path):
    assert logging_setup.reset_log_file(tmp_path / "mai-esistito.log") == 0


def test_clearing_logs_keeps_the_live_channel_writable(tmp_path, monkeypatch):
    """Il percorso completo: `clear(ITEM_LOGS)` su un app.log tenuto aperto da
    un handler installato davvero."""
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(maintenance, "LOGS_DIR", logs)
    logger = logging.getLogger("test_manutenzione_clear_logs")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(logs / "app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    try:
        logger.info("prima")
        handler.flush()
        result = maintenance.clear(maintenance.ITEM_LOGS)
        assert result.ok
        assert (logs / "app.log").stat().st_size == 0
        logger.info("dopo")
        handler.flush()
        assert (logs / "app.log").read_text(encoding="utf-8") == "dopo\n"
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_truncating_the_terminal_log_keeps_the_tee_alive(tmp_path, monkeypatch):
    """`terminal-log.txt` non e' un canale di logging: lo tiene un handle di
    modulo, catturato da `_TeeStream`. Va troncato IN POSTO, altrimenti il tee
    resterebbe a scrivere su un file chiuso per il resto della sessione."""
    target = tmp_path / "terminal-log.txt"
    handle = open(target, "w", encoding="utf-8", buffering=1)
    monkeypatch.setattr(logging_setup, "_TERMINAL_LOG_FILE", target)
    monkeypatch.setattr(logging_setup, "_terminal_log_file_handle", handle)
    tee = logging_setup._TeeStream(None, handle)
    try:
        tee.write("prima del troncamento\n")
        assert target.stat().st_size > 0

        logging_setup.reset_log_file(target)
        assert target.stat().st_size == 0
        assert not handle.closed          # il tee scrive ancora su QUESTO file

        tee.write("dopo\n")
        assert target.read_text(encoding="utf-8") == "dopo\n"
    finally:
        handle.close()


# ---- lo storico azzerato non fa esplodere il controllo «gia' scaricato» ----

def test_history_check_survives_a_missing_history_file(tmp_path, monkeypatch):
    from src.core import download_history

    mancante = tmp_path / "logs" / "download_history.log"
    monkeypatch.setattr(download_history, "_path", lambda: mancante)
    # Niente file: nessuna eccezione, e nessun link risulta gia' scaricato.
    assert download_history.load_history() == {}

    # E con il file appena troncato (esiste, ma vuoto) idem.
    mancante.parent.mkdir(parents=True, exist_ok=True)
    mancante.write_text("", encoding="utf-8")
    assert download_history.load_history() == {}
