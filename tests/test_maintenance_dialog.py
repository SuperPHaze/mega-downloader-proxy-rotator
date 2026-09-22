# Test della finestra Manutenzione (gui/maintenance_dialog.py).
#
# Le tre regole della superficie, quelle che il test deve sorvegliare perche'
# qui si cancellano dati dell'utente:
#   1. nessuna casella spuntata all'apertura;
#   2. l'elenco mostrato prima di cancellare coincide con cio' che sparisce;
#   3. a sessione in corso le due voci distruttive sono RIFIUTATE, non solo
#      sconsigliate.
#
# Tutto su cartelle temporanee: i log e i download veri non si toccano.
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from src.core import maintenance
from src.core.maintenance import (
    ITEM_DOWNLOADS,
    ITEM_HISTORY,
    ITEM_LOGS,
    ITEM_PROXY_CACHE,
    ITEM_SESSION,
)
from src.gui import maintenance_dialog as md
from src.gui.i18n import TR
from src.gui.maintenance_dialog import MaintenanceDialog
from src.proxy import proxy_cache


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Radice finta: log, download, stato di sessione e cache proxy."""
    logs = tmp_path / "logs"
    downloads = tmp_path / "downloads"
    logs.mkdir()
    downloads.mkdir()
    monkeypatch.setattr(maintenance, "LOGS_DIR", logs)
    monkeypatch.setattr(maintenance, "OUTPUT_DIR", downloads)
    monkeypatch.setattr(maintenance, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(proxy_cache, "_PROJECT_ROOT", tmp_path)

    (logs / "download_history.log").write_text(
        json.dumps({"handle": "h1"}) + "\n", encoding="utf-8",
    )
    (tmp_path / "session_state.json").write_text(
        json.dumps({"schema": 1, "urls": ["https://mega.nz/file/A#k"]}),
        encoding="utf-8",
    )
    (logs / "app.log").write_text("riga\n", encoding="utf-8")
    (downloads / "primo_0").mkdir()
    (downloads / "primo_0" / "video.mp4").write_text("x" * 10, encoding="utf-8")
    (tmp_path / "proxy_cache.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _dialog(workspace, **kwargs) -> MaintenanceDialog:
    dlg = MaintenanceDialog(**kwargs)
    return dlg


# ---- regola 1: niente e' pre-selezionato ----------------------------------

def test_nothing_is_checked_when_the_window_opens(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace)
    assert not any(c.isChecked() for c in dlg._checks.values())
    # E senza selezione il pulsante distruttivo e' spento.
    assert not dlg.confirm_btn.isEnabled()
    # Il predefinito e' USCIRE, non cancellare.
    assert dlg.cancel_btn.isDefault()
    assert not dlg.confirm_btn.isDefault()


def test_the_confirm_button_follows_the_selection(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace)
    dlg._checks[ITEM_HISTORY].setChecked(True)
    assert dlg.confirm_btn.isEnabled()
    dlg._checks[ITEM_HISTORY].setChecked(False)
    assert not dlg.confirm_btn.isEnabled()


# ---- regola 3: rifiuto a sessione in corso --------------------------------

def test_a_running_session_disables_the_two_destructive_entries(
    qt_app, italian_ui, workspace,
):
    dlg = _dialog(workspace, session_running=True)
    assert not dlg._checks[ITEM_DOWNLOADS].isEnabled()
    assert not dlg._checks[ITEM_LOGS].isEnabled()
    # Storico e stato della sessione restano azzerabili anche a sessione viva.
    assert dlg._checks[ITEM_HISTORY].isEnabled()
    assert dlg._checks[ITEM_SESSION].isEnabled()
    assert dlg._checks[ITEM_PROXY_CACHE].isEnabled()
    # E la finestra dice PERCHE': il motivo e' scritto, non solo il grigio.
    assert "sessione di download in corso" in dlg._checks[ITEM_DOWNLOADS].toolTip()


def test_a_locked_entry_cannot_be_selected_by_force(qt_app, italian_ui, workspace):
    """Anche marcandola a mano, una voce bloccata non entra nella selezione:
    il filtro guarda l'abilitazione, non solo la spunta."""
    dlg = _dialog(workspace, session_running=True)
    dlg._checks[ITEM_DOWNLOADS].setChecked(True)
    assert dlg._selected_keys() == []
    dlg._run(dlg._selected_keys())
    assert (workspace / "downloads" / "primo_0").exists()


def test_without_a_session_everything_is_available(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace, session_running=False)
    assert all(c.isEnabled() for c in dlg._checks.values())


# ---- regola 2: cio' che si legge e' cio' che sparisce ---------------------

def test_the_details_show_the_real_counts(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace)
    assert "1 voce" in dlg._details[ITEM_HISTORY].text()
    assert "1 link in sospeso" in dlg._details[ITEM_SESSION].text()
    assert "1 file" in dlg._details[ITEM_DOWNLOADS].text()
    assert "0 frammenti .part" in dlg._details[ITEM_DOWNLOADS].text()


def test_the_confirm_list_names_every_file_that_goes(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace)
    righe = "\n".join(dlg.confirm_lines([ITEM_HISTORY, ITEM_SESSION]))
    assert "Storico dei download" in righe
    assert "download_history.log" in righe
    assert "Stato della sessione" in righe
    assert "session_state.json" in righe
    # La cartella dei download si mostra per PATH, non file per file.
    righe_dl = "\n".join(dlg.confirm_lines([ITEM_DOWNLOADS]))
    assert str(workspace / "downloads") in righe_dl
    assert "video.mp4" not in righe_dl


def test_an_empty_entry_says_so(qt_app, italian_ui, tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(maintenance, "OUTPUT_DIR", tmp_path / "downloads")
    monkeypatch.setattr(maintenance, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(proxy_cache, "_PROJECT_ROOT", tmp_path)
    dlg = MaintenanceDialog()
    assert dlg._details[ITEM_HISTORY].text() == "niente da cancellare"


# ---- esecuzione e resoconto ----------------------------------------------

def test_running_clears_only_the_selected_entries(qt_app, italian_ui, workspace):
    dlg = _dialog(workspace)
    dlg._run([ITEM_HISTORY])

    assert maintenance.survey(ITEM_HISTORY).count == 0
    assert (workspace / "session_state.json").exists()
    assert (workspace / "downloads" / "primo_0" / "video.mp4").exists()
    assert (workspace / "proxy_cache.json").exists()


def test_the_report_stays_in_the_window_and_the_boxes_clear(
    qt_app, italian_ui, workspace,
):
    dlg = _dialog(workspace)
    dlg._checks[ITEM_SESSION].setChecked(True)
    dlg._run([ITEM_SESSION])

    assert dlg._report.isVisible() or dlg._report.text()   # offscreen: basta il testo
    assert "Stato della sessione" in dlg._report.text()
    assert "Spazio liberato in tutto" in dlg._report.text()
    # Niente resta spuntato: la prossima conferma riparte da zero.
    assert not any(c.isChecked() for c in dlg._checks.values())
    # E i dettagli sono stati rimisurati.
    assert dlg._details[ITEM_SESSION].text() == "niente da cancellare"


def test_the_proxy_cache_goes_through_the_function_that_already_exists(
    qt_app, italian_ui, workspace, monkeypatch,
):
    chiamate = []

    def _finta():
        chiamate.append(True)
        return True

    monkeypatch.setattr(md, "delete_proxy_cache", _finta)
    dlg = _dialog(workspace)
    dlg._run([ITEM_PROXY_CACHE])
    assert chiamate == [True]


def test_a_failed_entry_is_reported_and_the_others_go_on(
    qt_app, italian_ui, workspace, monkeypatch,
):
    import shutil

    monkeypatch.setattr(md.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(OSError("occupata"))
    )
    dlg = _dialog(workspace)
    dlg._run([ITEM_DOWNLOADS, ITEM_SESSION])

    testo = dlg._report.text()
    assert "non riuscito" in testo and "occupata" in testo
    assert "Stato della sessione: azzerato" in testo
    assert not (workspace / "session_state.json").exists()


# ---- il gate della finestra principale ------------------------------------

class _FintaFinestra:
    """Solo cio' che i due metodi sotto test leggono: costruire una MainWindow
    vera monterebbe tutta l'interfaccia e farebbe partire controllo
    aggiornamenti e misura della banda (stesso espediente di
    `tests/test_hot_add_links.py`)."""

    from src.gui.main_window import MainWindow as _MW

    _session_is_open = _MW._session_is_open
    _session_queue_drained = _MW._session_queue_drained
    _session_is_running = _MW._session_is_running
    _open_maintenance_dialog = _MW._open_maintenance_dialog


class _FakeControls:
    def __init__(self, download_dir: str = "") -> None:
        self._dir = download_dir

    def get_download_dir(self) -> str:
        return self._dir


class _FakeModel:
    def __init__(self, total: int, all_terminated: bool) -> None:
        self._agg = {"total": total, "all_terminated": all_terminated}

    def aggregates(self) -> dict:
        return self._agg


class _FakePanel:
    def __init__(self, model) -> None:
        self.model = model


class _FakeOrchestrator:
    def __init__(self, active_workers: bool = False) -> None:
        self._active = active_workers

    def has_active_workers(self) -> bool:
        return self._active


def _finta_finestra(*, total=1, all_terminated=False, no_orchestrator=False,
                    download_dir="", active_workers=False):
    win = _FintaFinestra()
    win.orchestrator = (
        None if no_orchestrator else _FakeOrchestrator(active_workers)
    )
    win.jobs_panel = _FakePanel(_FakeModel(total, all_terminated))
    win.controls = _FakeControls(download_dir)
    return win


def test_session_is_running_only_while_someone_is_writing(qt_app):
    from src.gui.main_window import MainWindow

    # Sessione viva, job non ancora terminati.
    assert MainWindow._session_is_running(_finta_finestra()) is True
    # Coda esaurita: la sessione esiste ancora, ma nessuno scrive piu'.
    assert MainWindow._session_is_running(
        _finta_finestra(all_terminated=True)
    ) is False
    # Nessuna sessione.
    assert MainWindow._session_is_running(
        _finta_finestra(no_orchestrator=True)
    ) is False


def test_after_a_global_cancel_the_live_workers_still_count(qt_app):
    """L'annullo globale marca TUTTI i job come annullati all'istante, ma i
    thread escono al checkpoint successivo: finche' sono vivi stanno ancora
    scrivendo sui `.part` e la manutenzione deve rifiutare."""
    from src.gui.main_window import MainWindow

    finestra = _finta_finestra(all_terminated=True, active_workers=True)
    assert MainWindow._session_is_running(finestra) is True


def test_the_settings_entry_passes_session_state_and_download_folder(
    qt_app, tmp_path, monkeypatch,
):
    """Il gate della finestra principale deve passare le DUE cose che solo lei
    sa: se c'e' una sessione viva e quale cartella di download e' configurata."""
    from src.gui import main_window as mw

    visti = {}

    class _FintoDialogo:
        def __init__(self, parent, *, session_running, output_root):
            visti["session_running"] = session_running
            visti["output_root"] = output_root

        def exec(self):
            return 0

    monkeypatch.setattr(mw, "MaintenanceDialog", _FintoDialogo)
    mw.MainWindow._open_maintenance_dialog(
        _finta_finestra(download_dir=str(tmp_path))
    )
    assert visti == {"session_running": True, "output_root": tmp_path}

    # Cartella predefinita: si passa None, non una stringa vuota.
    mw.MainWindow._open_maintenance_dialog(_finta_finestra(all_terminated=True))
    assert visti == {"session_running": False, "output_root": None}


# ---- i18n ------------------------------------------------------------------

def test_the_window_follows_the_language(qt_app, workspace, monkeypatch):
    """Dialogo modale creato su richiesta: legge il dizionario alla
    costruzione, quindi non serve `retranslate()` — ma la lingua deve essere
    quella corrente, non l'italiano cotto nel codice."""
    pref, lang = TR.preference(), TR.language()
    TR._preference, TR._language = "en", "en"
    try:
        dlg = MaintenanceDialog()
        assert dlg.windowTitle() == "Maintenance"
        assert dlg._checks[ITEM_DOWNLOADS].text() == "Download folder"
        assert dlg.confirm_btn.text() == "Clear"
    finally:
        TR._preference, TR._language = pref, lang
