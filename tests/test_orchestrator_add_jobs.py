# Aggiunta di link a una sessione gia' avviata: coda, identificativi,
# riaccensione del ricaricatore.
#
# Niente rete e nessun thread vero: il thread di setup e' sostituito da un
# finto che non parte, `_launch_worker` da una registrazione. Restano pero' i
# metodi VERI dell'orchestrator (`start`, `_spawn_workers`, `_fill_slots`,
# `add_jobs`, `_on_slot_freed`, `restart_job`): e' li' che vive la logica di
# coda che questi test devono sorvegliare.
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from src.core.state import SessionState  # noqa: E402
from src.downloader import orchestrator as orch_mod  # noqa: E402
from src.downloader.orchestrator import DownloadOrchestrator  # noqa: E402
from src.downloader.worker import job_output_dir  # noqa: E402


class _FakeSetupThread(QObject):
    """Stessa superficie di `_SetupThread` vista da `start()`, ma inerte:
    nessuna rete, nessun thread. Il test decide quando (e se) il setup
    "finisce", chiamando direttamente `_spawn_workers()`."""

    setup_status = pyqtSignal(str)
    setup_status_t = pyqtSignal(str, dict)
    setup_progress = pyqtSignal(int, int, int)
    finished_ok = pyqtSignal(list)
    hot_started = pyqtSignal()
    failed = pyqtSignal(str)
    failed_t = pyqtSignal(str, dict)

    def __init__(self, **_kwargs) -> None:
        super().__init__()
        self.started_count = 0

    def start(self) -> None:
        self.started_count += 1

    def isRunning(self) -> bool:  # noqa: N802 (superficie QThread)
        return False

    def wait(self, _ms: int = 0) -> bool:
        return True


class _FakeRefresher:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.running = False

    def start(self, initial_force: bool = False) -> None:
        self.starts += 1
        self.running = True

    def stop(self) -> None:
        self.stops += 1
        self.running = False

    def update_thresholds(self, low: int, high: int) -> None:
        pass


def _make(monkeypatch, links, concurrency=1):
    """Orchestrator a sessione avviata ma con il setup ancora in corso:
    e' la finestra temporale in cui la coda non esiste ancora."""
    monkeypatch.setattr(orch_mod, "_SetupThread", _FakeSetupThread)
    monkeypatch.setattr(orch_mod.telemetry, "start_session", lambda *a, **k: None)
    orch = DownloadOrchestrator(SessionState())
    orch._refresher = _FakeRefresher()
    launched: list[tuple[int, str]] = []

    def fake_launch(file_id: int, link: str) -> None:
        launched.append((file_id, link))
        orch._active_count += 1

    monkeypatch.setattr(orch, "_launch_worker", fake_launch)
    orch.start(links, concurrency=concurrency)
    return orch, launched


def _queue_ids(orch) -> list[int]:
    return [fid for fid, _ in orch._queue]


# ---- aggiunta a sessione in corso ----------------------------------------

def test_add_jobs_entra_in_coda_e_parte_quando_si_libera_uno_slot(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0", "u1"], concurrency=1)
    orch._spawn_workers()
    assert launched == [(0, "u0")]

    added = orch.add_jobs(["u2"])
    assert added == [2]
    # In coda dietro a u1, non avviato: lo slot e' occupato.
    assert _queue_ids(orch) == [1, 2]
    assert len(launched) == 1

    orch._on_slot_freed(0)
    assert launched[-1] == (1, "u1")
    orch._on_slot_freed(1)
    assert launched[-1] == (2, "u2")


def test_add_jobs_parte_subito_se_uno_slot_e_libero(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0"], concurrency=2)
    orch._spawn_workers()
    assert launched == [(0, "u0")]
    orch.add_jobs(["u1"])
    # Secondo slot libero: parte senza aspettare nessuno.
    assert launched == [(0, "u0"), (1, "u1")]


# ---- la trappola principale: aggiunta mentre si raccolgono i proxy --------

def test_add_jobs_durante_la_raccolta_sopravvive_a_spawn_workers(qt_app, monkeypatch):
    """Il difetto piu' probabile di tutto il lavoro: `_spawn_workers` COSTRUISCE
    la coda: un link aggiunto prima sparirebbe senza lasciare traccia."""
    orch, launched = _make(monkeypatch, ["u0", "u1"], concurrency=1)
    assert orch._workers_spawned is False
    assert orch._queue == []

    added = orch.add_jobs(["u2"])
    assert added == [2]

    orch._spawn_workers()
    # Il link aggiunto e' nella coda costruita dal setup, con il SUO id.
    assert _queue_ids(orch) == [1, 2]
    orch._on_slot_freed(0)
    orch._on_slot_freed(1)
    assert launched[-1] == (2, "u2")


def test_add_jobs_durante_la_raccolta_rispetta_la_posizione(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0", "u1"], concurrency=1)
    orch.add_jobs(["u2"], at_top=True)
    orch._spawn_workers()
    # In testa a tutto: parte per primo.
    assert launched == [(2, "u2")]
    assert _queue_ids(orch) == [0, 1]


# ---- coda esaurita: ricaricatore e timer tornano attivi -------------------

def test_add_jobs_a_coda_esaurita_riaccende_ricaricatore_e_timer(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0"], concurrency=1)
    orch._spawn_workers()
    orch._refresher.running = True
    orch._pool_size_timer.start()
    orch._cache_save_timer.start()

    orch._on_slot_freed(0)
    # Niente attivi e niente in coda: tutto spento.
    assert orch._refresher.running is False
    assert orch._pool_size_timer.isActive() is False
    assert orch._cache_save_timer.isActive() is False

    starts_before = orch._refresher.starts
    assert orch.add_jobs(["u1"]) == [1]
    assert orch._refresher.starts == starts_before + 1
    assert orch._pool_size_timer.isActive() is True
    assert orch._cache_save_timer.isActive() is True
    assert launched[-1] == (1, "u1")


def test_add_jobs_riattiva_la_sessione_annullata(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0"], concurrency=1)
    orch._spawn_workers()
    # Annullo globale: il worker esce e libera lo slot a sessione morta.
    orch.session_state.cancel()
    orch._on_slot_freed(0)
    assert orch._refresher.running is False

    orch.add_jobs(["u1"])
    assert orch.session_state.is_cancelled() is False
    assert orch._refresher.running is True
    assert launched[-1] == (1, "u1")


# ---- identificativi -------------------------------------------------------

def test_identificativi_mai_riusati_dopo_annullamenti_e_riavvii(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0", "u1", "u2"], concurrency=1)
    orch._spawn_workers()
    visti = set(_queue_ids(orch)) | {fid for fid, _ in launched}
    assert visti == {0, 1, 2}

    # Annullamento di un job in coda: il suo id non torna disponibile.
    assert orch.cancel_job(2) == "queued"
    # Riavvio: riusa il PROPRIO id (stesso job, stessa cartella), non ne chiede
    # uno nuovo.
    assert orch.restart_job(2, "u2") is True
    assert 2 in _queue_ids(orch)

    primi = orch.add_jobs(["u3"])
    secondi = orch.add_jobs(["u4", "u5"])
    assert primi == [3]
    assert secondi == [4, 5]
    assert not (set(primi) | set(secondi)) & visti


def test_identificativi_partono_da_zero_a_ogni_sessione(qt_app, monkeypatch):
    orch, _ = _make(monkeypatch, ["u0", "u1"], concurrency=1)
    orch._spawn_workers()
    assert orch.add_jobs(["u2"]) == [2]
    # Sessione nuova: la GUI ricrea le righe da zero, gli id pure.
    orch.start(["v0", "v1"], concurrency=1)
    assert [fid for fid, _ in orch._pending_jobs] == [0, 1]
    assert orch.add_jobs(["v2"]) == [2]


def test_cartelle_di_destinazione_distinte_per_id(qt_app, monkeypatch):
    """L'identificativo entra nel nome della cartella: due job non devono mai
    scrivere nello stesso posto, nemmeno con lo STESSO url."""
    orch, _ = _make(monkeypatch, ["https://mega.nz/file/aaa#k"], concurrency=1)
    orch._spawn_workers()
    aggiunti = orch.add_jobs(["https://mega.nz/file/aaa#k"])
    tutti = [0] + aggiunti
    cartelle = {str(job_output_dir("https://mega.nz/file/aaa#k", fid)) for fid in tutti}
    assert len(cartelle) == len(tutti)


# ---- posizione ------------------------------------------------------------

def test_posizione_in_testa_e_in_fondo(qt_app, monkeypatch):
    orch, _ = _make(monkeypatch, ["u0", "u1", "u2"], concurrency=1)
    orch._spawn_workers()
    assert _queue_ids(orch) == [1, 2]

    orch.add_jobs(["coda"])            # in fondo (default)
    orch.add_jobs(["testa"], at_top=True)
    assert [url for _, url in orch._queue] == ["testa", "u1", "u2", "coda"]


def test_posizione_in_testa_non_ferma_i_download_in_corso(qt_app, monkeypatch):
    orch, launched = _make(monkeypatch, ["u0", "u1"], concurrency=1)
    orch._spawn_workers()
    avviati_prima = list(launched)
    orch.add_jobs(["urgente"], at_top=True)
    # Nessun worker nuovo e nessuno tolto: il file in corso resta in corso.
    assert launched == avviati_prima
    assert orch._active_count == 1


# ---- rifiuti --------------------------------------------------------------

def test_add_jobs_senza_link_non_assegna_identificativi(qt_app, monkeypatch):
    orch, _ = _make(monkeypatch, ["u0"], concurrency=1)
    orch._spawn_workers()
    prima = orch._next_file_id
    assert orch.add_jobs([]) == []
    assert orch._next_file_id == prima


def test_add_jobs_rifiutato_se_il_setup_non_ha_trovato_proxy(qt_app, monkeypatch):
    orch, _ = _make(monkeypatch, ["u0"], concurrency=1)
    orch._on_setup_ok([])  # nessun proxy vivo
    assert orch.add_jobs(["u1"]) == []


def test_add_jobs_rifiutato_durante_la_chiusura(qt_app, monkeypatch):
    orch, _ = _make(monkeypatch, ["u0"], concurrency=1)
    orch._spawn_workers()
    orch._shutdown_requested = True
    assert orch.add_jobs(["u1"]) == []
