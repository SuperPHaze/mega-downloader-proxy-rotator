import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from src.gui.jobs_model import JobsModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _start_job(model: JobsModel, file_id: int, seconds_ago: float = 10.0, bytes_downloaded: int = 0) -> None:
    """Avvia un job e backdates started_at per simulare una durata realistica."""
    model.set_progress(file_id, 1)
    if bytes_downloaded:
        model.set_throughput(file_id, 0.0, bytes_downloaded, bytes_downloaded * 10)
    job = model.get_job(file_id)
    assert job is not None
    job.started_at = time.time() - seconds_ago


# ---- total_downloaded_bytes ----------------------------------------------

def test_total_downloaded_bytes_sums_all_states(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb", "https://mega.nz/file/CCC#ddd"])
    # Job 0: running con 5 MB
    model.set_progress(0, 50)
    model.set_throughput(0, 1_000_000, 5_000_000, 100_000_000)
    # Job 1: completato con 8 MB
    _start_job(model, 1, seconds_ago=10, bytes_downloaded=8_000_000)
    model.mark_completed(1)
    agg = model.aggregates()
    assert agg["total_downloaded_bytes"] == 5_000_000 + 8_000_000


def test_total_downloaded_bytes_includes_partial_from_failed(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=10, bytes_downloaded=3_000_000)
    model.mark_failed_fatal(0, "errore test")
    agg = model.aggregates()
    assert agg["total_downloaded_bytes"] == 3_000_000


def test_total_downloaded_bytes_zero_on_empty(qapp):
    model = JobsModel()
    model.reset([])
    assert model.aggregates()["total_downloaded_bytes"] == 0


# ---- all_terminated ------------------------------------------------------

def test_all_terminated_false_while_job_queued(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb", "https://mega.nz/file/CCC#ddd"])
    _start_job(model, 0)
    model.mark_completed(0)
    # Job 1 ancora in coda
    assert model.aggregates()["all_terminated"] is False


def test_all_terminated_false_while_job_running(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    model.set_progress(0, 50)
    assert model.aggregates()["all_terminated"] is False


def test_all_terminated_true_when_all_completed(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb", "https://mega.nz/file/CCC#ddd"])
    _start_job(model, 0)
    model.mark_completed(0)
    _start_job(model, 1)
    model.mark_completed(1)
    assert model.aggregates()["all_terminated"] is True


def test_all_terminated_true_mixed_terminal_states(qapp):
    model = JobsModel()
    model.reset([
        "https://mega.nz/file/AAA#bbb",
        "https://mega.nz/file/CCC#ddd",
        "https://mega.nz/file/EEE#fff",
    ])
    _start_job(model, 0)
    model.mark_completed(0)
    model.mark_failed_fatal(1, "errore")
    _start_job(model, 2)
    model.mark_cancelled(2)
    assert model.aggregates()["all_terminated"] is True


def test_all_terminated_false_on_empty_model(qapp):
    model = JobsModel()
    model.reset([])
    assert model.aggregates()["all_terminated"] is False


# ---- arithmetic_avg_bps --------------------------------------------------

def test_arithmetic_avg_bps_none_before_any_termination(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    model.set_progress(0, 50)
    assert model.aggregates()["arithmetic_avg_bps"] is None


def test_arithmetic_avg_bps_computed_from_two_jobs(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb", "https://mega.nz/file/CCC#ddd"])
    _start_job(model, 0)
    model.mark_completed(0)
    _start_job(model, 1)
    model.mark_completed(1)
    # Impostare valori noti direttamente per evitare incertezza sul timing
    model.get_job(0).average_bps_final = 10 * 1_048_576.0  # 10 MB/s
    model.get_job(1).average_bps_final = 20 * 1_048_576.0  # 20 MB/s
    agg = model.aggregates()
    assert agg["arithmetic_avg_bps"] == pytest.approx(15 * 1_048_576.0)


def test_arithmetic_avg_bps_none_if_no_bytes(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    # Job termina senza aver scaricato nulla → average_bps_final = None
    model.mark_failed_fatal(0, "errore immediato")
    assert model.aggregates()["arithmetic_avg_bps"] is None


# ---- freeze average_bps_final in marker methods -------------------------

def test_mark_completed_freezes_average_bps(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=10, bytes_downloaded=10_000_000)
    model.mark_completed(0)
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is not None
    assert job.average_bps_final > 0


def test_mark_failed_fatal_freezes_average_bps(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=5, bytes_downloaded=2_000_000)
    model.mark_failed_fatal(0, "errore test")
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is not None


def test_mark_abandoned_freezes_average_bps(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=5, bytes_downloaded=1_000_000)
    model.mark_abandoned(0, 15, "troppi errori")
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is not None


def test_mark_cancelled_freezes_average_bps(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=3, bytes_downloaded=500_000)
    model.mark_cancelled(0)
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is not None


def test_average_bps_none_if_zero_duration(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    # Nessun started_at → duration_s() == 0 → average_bps_final = None
    model.mark_failed_fatal(0, "errore immediato")
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is None


def test_average_bps_none_if_zero_bytes(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    # Job avviato ma nessun byte scaricato
    _start_job(model, 0, seconds_ago=10, bytes_downloaded=0)
    model.mark_completed(0)
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is None


# ---- restart_job ---------------------------------------------------------

def test_restart_job_resets_average_bps_final(qapp):
    model = JobsModel()
    model.reset(["https://mega.nz/file/AAA#bbb"])
    _start_job(model, 0, seconds_ago=10, bytes_downloaded=5_000_000)
    model.mark_failed_fatal(0, "errore test")
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is not None
    model.restart_job(0)
    job = model.get_job(0)
    assert job is not None
    assert job.average_bps_final is None
