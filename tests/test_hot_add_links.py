# Lato interfaccia dell'aggiunta a caldo: riconoscimento dei doppioni nella
# sessione in corso, accodamento delle righe senza distruggere quelle
# esistenti, selettore di posizione e contabilita' della finestra.
#
# Nessuna rete. La parte che non richiede Qt (`find_session_duplicates`) e'
# testata da sola; il resto costruisce i widget veri sulla piattaforma
# offscreen della suite.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from src.core import session_store  # noqa: E402
from src.gui.jobs_model import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    JobsModel,
)
from src.gui.jobs_panel import JobsPanel  # noqa: E402
from src.gui.link_panel import dedup_key, find_session_duplicates  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402
from src.gui.paste_links_dialog import (  # noqa: E402
    POSITION_BOTTOM,
    POSITION_TOP,
    PasteLinksDialog,
)


FILE_A = "https://mega.nz/file/AAAAAAAA#chiave"
FILE_B = "https://mega.nz/file/BBBBBBBB#chiave"
FILE_C = "https://mega.nz/file/CCCCCCCC#chiave"
# Stesso file di FILE_A nella forma vecchia: stesso handle, URL diverso.
FILE_A_LEGACY = "https://mega.nz/#!AAAAAAAA!chiave"


# ---- doppioni nella sessione in corso ------------------------------------

def test_riconosce_i_tre_casi_in_coda_in_download_e_concluso():
    """I tre stati che il prompt chiede di riconoscere, in un colpo solo."""
    sessione = {
        dedup_key(FILE_A): "In coda",
        dedup_key(FILE_B): "In corso",
        dedup_key(FILE_C): "Completato",
    }
    trovati = find_session_duplicates([FILE_A, FILE_B, FILE_C], sessione)
    assert trovati == [(0, "In coda"), (1, "In corso"), (2, "Completato")]


def test_link_nuovo_non_e_un_doppione():
    sessione = {dedup_key(FILE_A): "In coda"}
    assert find_session_duplicates([FILE_B], sessione) == []


def test_doppione_riconosciuto_anche_con_url_di_forma_diversa():
    """Il confronto e' per handle Mega, come nello storico: lo stesso file
    incollato in due forme di URL resta un file solo."""
    sessione = {dedup_key(FILE_A): "In corso"}
    assert find_session_duplicates([FILE_A_LEGACY], sessione) == [(0, "In corso")]


def test_link_cartella_non_espanso_confrontato_per_url_esatto():
    """Senza handle di file da confrontare resta l'URL: due incollate della
    stessa cartella si riconoscono comunque."""
    cartella = "https://mega.nz/folder/FFFFFFFF#chiave"
    assert dedup_key(cartella) == cartella
    sessione = {dedup_key(cartella): "In coda"}
    assert find_session_duplicates([cartella], sessione) == [(0, "In coda")]


def test_lo_stato_del_job_arriva_dal_modello(qt_app, italian_ui):
    """La descrizione mostrata e' quella del job vero, non una costante."""
    model = JobsModel()
    model.reset([FILE_A, FILE_B])
    model._job(0).status = STATUS_RUNNING
    model._job(1).status = STATUS_COMPLETED

    finta = _FintaFinestra()
    finta.jobs_panel = type("P", (), {"model": model})()
    mappa = MainWindow._session_dup_map(finta)
    assert mappa[dedup_key(FILE_A)] == "In corso"
    assert mappa[dedup_key(FILE_B)] == "Completato"


# ---- accodare righe senza cancellare quelle esistenti --------------------

def test_append_jobs_non_cancella_le_righe_esistenti(qt_app, italian_ui):
    panel = JobsPanel()
    panel.reset([FILE_A, FILE_B])
    panel.model.set_progress(0, 42)
    panel.model._job(1).status = STATUS_RUNNING

    panel.append_jobs([(2, FILE_C)])

    assert [j.file_id for j in panel.model.jobs_iter()] == [0, 1, 2]
    assert sorted(panel._cards) == [0, 1, 2]
    # I dati di chi c'era gia' non sono stati toccati.
    assert panel.model.get_job(0).progress == 42
    assert panel.model.get_job(1).status == STATUS_RUNNING
    assert panel.model.get_job(2).status == STATUS_QUEUED
    assert panel.model.get_job(2).url == FILE_C


def test_append_jobs_aggiorna_il_totale_del_cruscotto(qt_app, italian_ui):
    panel = JobsPanel()
    panel.reset([FILE_A])
    assert panel.model.aggregates()["total"] == 1
    panel.append_jobs([(1, FILE_B), (2, FILE_C)])
    assert panel.model.aggregates()["total"] == 3
    assert panel.model.aggregates()["queued"] == 3


def test_append_jobs_ignora_un_identificativo_gia_noto(qt_app):
    """Difesa di ultima istanza: riusare un id sovrascriverebbe la storia di
    un job vivo. Gli id li assegna l'orchestrator e non li riusa mai."""
    model = JobsModel()
    model.reset([FILE_A])
    model.set_progress(0, 77)
    assert model.append_jobs([(0, FILE_B)]) == []
    assert model.get_job(0).url == FILE_A
    assert model.get_job(0).progress == 77


# ---- selettore di posizione ----------------------------------------------

def test_posizione_predefinita_in_fondo(qt_app, italian_ui):
    dlg = PasteLinksDialog([], allow_duplicates=False, show_position=True)
    assert dlg.selected_position() == POSITION_BOTTOM
    dlg.pos_top.setChecked(True)
    assert dlg.selected_position() == POSITION_TOP


def test_senza_selettore_la_posizione_e_in_fondo(qt_app, italian_ui):
    """Fuori sessione la coda non esiste: la domanda non viene nemmeno posta."""
    dlg = PasteLinksDialog([], allow_duplicates=False)
    assert dlg.pos_top is None
    assert dlg.selected_position() == POSITION_BOTTOM


# ---- contabilita' della finestra -----------------------------------------

class _FintaFinestra:
    """Solo i campi che i metodi sotto test leggono e scrivono.

    I metodi chiamati sono quelli VERI della classe, con questo oggetto al
    posto di `self`: costruire una MainWindow monterebbe tutta l'interfaccia e
    farebbe partire controllo aggiornamenti e misura della banda. Stesso
    espediente gia' usato in `tests/test_i18n.py` per la riga di stato.
    """

    _session_persist = MainWindow._session_persist


class _FakePanel:
    def __init__(self) -> None:
        self.appended: list[tuple[int, str]] = []

    def append_jobs(self, jobs):
        self.appended.extend(jobs)


class _FakeFlag:
    def __init__(self) -> None:
        self.running = None

    def set_running(self, running: bool) -> None:
        self.running = running


def _finta_finestra():
    win = _FintaFinestra()
    win.jobs_panel = _FakePanel()
    win.controls = _FakeFlag()
    win.link_panel = _FakeFlag()
    win._links_by_id = {0: FILE_A}
    win._session_incomplete = {0: FILE_A}
    win._expected_files = 1
    win._queue_done_notified = True
    return win


def test_registrazione_estende_la_contabilita_invece_di_ricrearla(
    qt_app, monkeypatch, tmp_path,
):
    monkeypatch.setattr(session_store, "_path", lambda: tmp_path / "s.json")
    win = _finta_finestra()

    MainWindow._register_added_jobs(win, [1, 2], [FILE_B, FILE_C])

    assert win.jobs_panel.appended == [(1, FILE_B), (2, FILE_C)]
    assert win._links_by_id == {0: FILE_A, 1: FILE_B, 2: FILE_C}
    assert win._expected_files == 3
    # La coda non e' piu' finita: l'avviso di fine coda deve poter tornare.
    assert win._queue_done_notified is False
    assert win.controls.running is True
    assert win.link_panel.running is True


def test_il_file_di_ripristino_contiene_anche_i_link_aggiunti(
    qt_app, monkeypatch, tmp_path,
):
    """Senza questo, un riavvio dopo un'aggiunta perde i link aggiunti."""
    monkeypatch.setattr(session_store, "_path", lambda: tmp_path / "s.json")
    win = _finta_finestra()

    MainWindow._register_added_jobs(win, [1], [FILE_B])

    assert session_store.load() == [FILE_A, FILE_B]
