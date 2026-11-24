"""The normal download entry points, using a small file and an offline transport."""
from pathlib import Path
from threading import Event, Thread
from concurrent.futures import CancelledError

import pytest
from Crypto.Cipher import AES

from src.core import session_store
from src.core.file_naming import final_output_dir
from src.core.mega_links import build_folder_job_url
from src.downloader.file_integrity import FileIntegrityError
from src.core.state import SessionState
from src.downloader import mega_client, worker
from src.downloader.mega_api import MegaPublicClient
from src.downloader.parallel_client import ParallelMegaDownloader, _progress_path, _save_progress
from src.proxy.pool import ProxyPool


CONTENTS = b"A sample document for a local transfer."
URL = "https://mega.nz/file/EXAMPLE1#test"
FILE_NAME = "Sample document.txt"
TEST_PROXY = {"host": "localhost", "port": 1, "protocol": "http"}


@pytest.fixture
def offline_file(monkeypatch):
    info = dict(handle="EXAMPLE1", k=(0, 0, 0, 0), iv=(0, 0, 0, 0),
                file_size=len(CONTENTS), file_name=FILE_NAME, cdn_url="https://example.invalid/file")
    info["meta_mac"] = bytes.fromhex("4bf6115a60abb5b1")
    monkeypatch.setattr(MegaPublicClient, "resolve_public_url", lambda *args: info)
    monkeypatch.setattr(mega_client.MegaClient, "get_egress_ip", lambda self: "local")
    encrypted = AES.new(bytes(16), AES.MODE_CTR, nonce=b"", initial_value=0).encrypt(CONTENTS)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield encrypted

    response = Response()
    response.info = info
    monkeypatch.setattr(mega_client.requests, "get", lambda *args, **kwargs: response)

    def write_chunk(self, idx, start, end, cdn, key, counter, part, *args):
        with part.open("r+b") as stream:
            stream.seek(start)
            stream.write(CONTENTS[start:end + 1])

    monkeypatch.setattr(ParallelMegaDownloader, "_download_chunk", write_chunk)
    return response


@pytest.mark.parametrize("connections", [1, 2])
@pytest.mark.parametrize("existing_destination", [False, True])
def test_first_transfer_and_reported_paths(tmp_path, monkeypatch, offline_file, connections, existing_destination):
    named = final_output_dir(FILE_NAME, 0, tmp_path)
    if existing_destination:
        named.mkdir()
        (named / "keep.txt").write_bytes(b"existing")
    task = worker.DownloadWorker(0, URL, ProxyPool(), SessionState(),
                                 output_root=tmp_path, connections_per_file=connections)
    monkeypatch.setattr(task, "_get_proxy_blocking", lambda: TEST_PROXY)
    monkeypatch.setattr(worker, "MAX_ATTEMPTS_PER_FILE", 1)
    resolved, completed, failures = [], [], []
    task.file_resolved.connect(lambda fid, name, size, path: resolved.append(Path(path).parent.is_dir()))
    task.completed_info.connect(lambda fid, url, name, size, path: completed.append(Path(path)))
    task.failed.connect(lambda fid, cycle, error: failures.append(error))
    task.run()
    assert not failures
    assert resolved == [True]
    destination = worker.job_output_dir(URL, 0, tmp_path) if existing_destination else named
    assert completed == [destination / "ciclo_1" / FILE_NAME]
    assert completed[0].read_bytes() == CONTENTS
    if existing_destination:
        assert (named / "keep.txt").read_bytes() == b"existing"


@pytest.mark.parametrize("connections", [1, 2])
@pytest.mark.parametrize("exists", [False, True])
def test_resume_identifies_the_expected_file(tmp_path, monkeypatch, offline_file, connections, exists):
    task = worker.DownloadWorker(0, URL, ProxyPool(), SessionState(),
                                 output_root=tmp_path, connections_per_file=connections)
    cycle = worker.job_output_dir(URL, 0, tmp_path) / "ciclo_1"
    cycle.mkdir(parents=True)
    (cycle / ".DS_Store").write_bytes(b"Finder metadata")
    if exists:
        (cycle / FILE_NAME).write_bytes(CONTENTS)
        def unexpected(*args, **kwargs):
            pytest.fail("downloaded the body of an existing complete file")
        monkeypatch.setattr(mega_client.requests, "get", unexpected)
        monkeypatch.setattr(ParallelMegaDownloader, "_download_chunk", unexpected)
    monkeypatch.setattr(task, "_get_proxy_blocking", lambda: TEST_PROXY)
    completed = []
    task.completed_info.connect(lambda fid, url, name, size, path: completed.append(Path(path)))
    task.run()
    expected = final_output_dir(FILE_NAME, 0, tmp_path) / "ciclo_1" / FILE_NAME
    assert completed == [expected]
    assert expected.read_bytes() == CONTENTS


@pytest.mark.parametrize("partial", [None, b"short", CONTENTS])
def test_resume_only_skips_data_present_on_disk(tmp_path, offline_file, monkeypatch, partial):
    part = tmp_path / (FILE_NAME + ".part")
    downloader = ParallelMegaDownloader(ProxyPool(), 2)
    if partial is not None:
        part.write_bytes(partial)
    _save_progress(part, "EXAMPLE1", len(CONTENTS), {(0, len(CONTENTS) - 1)}, downloader.chunk_size)
    if partial == CONTENTS:
        monkeypatch.setattr(downloader, "_download_chunk", lambda *args: pytest.fail("valid resume re-fetched"))
    final = downloader.download(URL, tmp_path, {})
    assert final.read_bytes() == CONTENTS
    assert not _progress_path(part).exists()


def test_failed_final_rename_keeps_the_checkpoint(tmp_path, offline_file):
    part = tmp_path / (FILE_NAME + ".part")
    part.write_bytes(CONTENTS)
    downloader = ParallelMegaDownloader(ProxyPool(), 2)
    _save_progress(part, "EXAMPLE1", len(CONTENTS), {(0, len(CONTENTS) - 1)}, downloader.chunk_size)
    # An existing directory with the final file's name prevents promotion.
    (tmp_path / FILE_NAME).mkdir()
    with pytest.raises(OSError):
        downloader.download(URL, tmp_path, {})
    assert part.read_bytes() == CONTENTS
    assert _progress_path(part).is_file()


def test_serial_cancel_during_the_response_leaves_only_a_partial(tmp_path, offline_file, monkeypatch):
    task = worker.DownloadWorker(0, URL, ProxyPool(), SessionState(),
                                 output_root=tmp_path, connections_per_file=1)
    monkeypatch.setattr(task, "_get_proxy_blocking", lambda: TEST_PROXY)
    response = offline_file
    original_stream = response.iter_content

    def interrupted_stream(chunk_size):
        data = next(original_stream(chunk_size))
        yield data[:16]
        task.request_cancel()
        yield data[16:]

    monkeypatch.setattr(response, "iter_content", interrupted_stream)
    completed, cancelled, errors = [], [], []
    task.all_done.connect(completed.append)
    task.cancelled.connect(cancelled.append)
    task.failed.connect(lambda *args: errors.append(args))
    task.run()
    assert cancelled == [0] and not completed and not errors
    assert not list(tmp_path.rglob(FILE_NAME))
    assert next(tmp_path.rglob("*.part")).read_bytes() == CONTENTS[:16]


def test_cancelling_a_paused_file_releases_only_its_waiter(tmp_path):
    state = SessionState()
    state.start()
    state.pause()
    task = worker.DownloadWorker(0, URL, ProxyPool(), state, output_root=tmp_path)
    entered = Event()
    stopped = Event()

    def wait_for_transfer():
        entered.set()
        if task._effective_state.should_abort_transfer():
            stopped.set()

    thread = Thread(target=wait_for_transfer)
    thread.start()
    try:
        assert entered.wait(2)
        task.request_cancel()
        assert stopped.wait(2)
        assert state.is_paused() and not state.is_cancelled()
    finally:
        state.resume()
        thread.join(2)


@pytest.mark.parametrize("connections", [1, 2])
def test_wrong_mac_never_completes_and_restart_gets_clean_bytes(
    tmp_path, monkeypatch, offline_file, connections,
):
    cycle = worker.job_output_dir(URL, 4, tmp_path) / "ciclo_1"
    cycle.mkdir(parents=True)
    previous = cycle / FILE_NAME
    previous.write_bytes(b"previous copy")
    part = cycle / (FILE_NAME + ".part")

    def run():
        task = worker.DownloadWorker(4, URL, ProxyPool(), SessionState(),
                                     output_root=tmp_path, connections_per_file=connections)
        monkeypatch.setattr(task, "_get_proxy_blocking", lambda: TEST_PROXY)
        complete, abandoned, history, progress = [], [], [], []
        task.all_done.connect(complete.append)
        task.abandoned_detail.connect(lambda fid, url, attempts, code, params: abandoned.append(code))
        task.completed_info.connect(lambda fid, url, name, size, path: history.append(Path(path)))
        task.progress.connect(lambda fid, cycle, pct: progress.append(pct))
        task.run()
        return complete, abandoned, history, progress

    with monkeypatch.context() as broken:
        if connections == 1:
            encrypted = next(offline_file.iter_content(1024))
            broken.setattr(offline_file, "iter_content",
                           lambda chunk_size: [bytes([encrypted[0] ^ 1]) + encrypted[1:]])
        else:
            part.write_bytes(b"?" * len(CONTENTS))
            chunk_size = ParallelMegaDownloader(ProxyPool(), connections).chunk_size
            _save_progress(part, "EXAMPLE1", len(CONTENTS), {(0, len(CONTENTS) - 1)}, chunk_size)
            broken.setattr(ParallelMegaDownloader, "_download_chunk",
                           lambda *args: pytest.fail("expected a full checkpoint"))
        done, abandoned, history, progress = run()
    assert not done and not history and 100 not in progress
    assert abandoned == ["file_mac_mismatch"]
    assert previous.read_bytes() == b"previous copy"
    assert not part.exists() and not _progress_path(part).exists()

    done, abandoned, history, progress = run()
    assert done == [4] and not abandoned and progress[-1] == 100
    assert history[0].read_bytes() == CONTENTS


@pytest.mark.parametrize("connections", [1, 2])
def test_same_length_existing_output_is_verified_and_replaced(tmp_path, offline_file, connections):
    (tmp_path / FILE_NAME).write_bytes(b"?" * len(CONTENTS))
    if connections == 1:
        final = mega_client.MegaClient(TEST_PROXY).download(URL, tmp_path, reuse_existing=True)
    else:
        final = ParallelMegaDownloader(ProxyPool(), 2).download(URL, tmp_path, {}, reuse_existing=True)
    assert final.read_bytes() == CONTENTS


@pytest.mark.parametrize("connections", [1, 2])
@pytest.mark.parametrize("valid", [True, False])
def test_empty_files_require_the_empty_mac(tmp_path, monkeypatch, offline_file, connections, valid):
    offline_file.info.update(file_size=0, meta_mac=bytes(8) if valid else bytes([1]) * 8)
    monkeypatch.setattr(offline_file, "iter_content", lambda chunk_size: [])
    final = tmp_path / FILE_NAME
    final.write_bytes(b"previous")
    def download():
        if connections == 1:
            return mega_client.MegaClient(TEST_PROXY).download(URL, tmp_path)
        return ParallelMegaDownloader(ProxyPool(), 2).download(URL, tmp_path, {})

    if valid:
        assert download().read_bytes() == b""
    else:
        with pytest.raises(FileIntegrityError):
            download()
        assert final.read_bytes() == b"previous"


def test_cancelled_verification_keeps_the_resumable_checkpoint(tmp_path, monkeypatch, offline_file):
    part = tmp_path / (FILE_NAME + ".part")
    part.write_bytes(CONTENTS)
    client = ParallelMegaDownloader(ProxyPool(), 2)
    _save_progress(part, "EXAMPLE1", len(CONTENTS), {(0, len(CONTENTS) - 1)}, client.chunk_size)
    monkeypatch.setattr(client, "_verification_cancelled", lambda: True)
    with pytest.raises(CancelledError):
        client.download(URL, tmp_path, {})
    assert not (tmp_path / FILE_NAME).exists()
    assert part.read_bytes() == CONTENTS and _progress_path(part).exists()
    monkeypatch.setattr(client, "_verification_cancelled", lambda: False)
    assert client.download(URL, tmp_path, {}).read_bytes() == CONTENTS


@pytest.mark.parametrize("connections", [1, 2])
def test_legacy_folder_file_resolves_length_and_reuses_verified_bytes(
    tmp_path, monkeypatch, offline_file, connections,
):
    target = tmp_path / "Tree" / FILE_NAME
    target.parent.mkdir()
    target.write_bytes(CONTENTS)
    url = build_folder_job_url("FOLDER", "EXAMPLE1", "test", ("Tree", FILE_NAME))
    task = worker.DownloadWorker(4, url, ProxyPool(), SessionState(), output_root=tmp_path,
                                 connections_per_file=connections)
    monkeypatch.setattr(task, "_get_proxy_blocking", lambda: TEST_PROXY)
    monkeypatch.setattr(mega_client.requests, "get", lambda *a, **kw: pytest.fail("network read"))
    monkeypatch.setattr(ParallelMegaDownloader, "_download_chunk", lambda *a: pytest.fail("network read"))
    complete = []
    task.all_done.connect(complete.append)
    task.run()
    assert complete == [4] and target.read_bytes() == CONTENTS


def test_restored_draft_starts_the_same_worker_and_reuses_its_checkpoint(
    qt_app, tmp_path, monkeypatch, offline_file,
):
    from PyQt6.QtWidgets import QMessageBox
    from src.downloader import orchestrator as engine
    from src.gui import main_window, preferences

    root = tmp_path / "chosen destination"
    part = worker.job_output_dir(URL, 4, root) / "ciclo_1" / (FILE_NAME + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(CONTENTS)
    chunk_size = ParallelMegaDownloader(ProxyPool(), 2).chunk_size
    _save_progress(part, "EXAMPLE1", len(CONTENTS), {(0, len(CONTENTS) - 1)}, chunk_size)

    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(session_store, "_path", lambda: tmp_path / "session_state.json")
    session_store.save({4: URL}, next_id=9)
    for method in ("_run_speedtest", "_maybe_check_updates_on_startup"):
        monkeypatch.setattr(main_window.MainWindow, method, lambda self: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(main_window, "confirm_already_downloaded", lambda links, parent: links)
    monkeypatch.setattr(engine._SetupThread, "start", lambda self: None)
    monkeypatch.setattr(engine.telemetry, "start_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker.DownloadWorker, "_get_proxy_blocking", lambda self: TEST_PROXY)
    monkeypatch.setattr(ParallelMegaDownloader, "_download_chunk", lambda *args: pytest.fail("refetched bytes"))

    window = main_window.MainWindow()
    try:
        qt_app.processEvents()
        assert window.link_panel.get_links() == [URL]
        window.controls.set_download_dir(str(root))
        new_url = "https://mega.nz/file/EXAMPLE2#test"
        window.link_panel.set_links([new_url, URL])
        window._on_start()
        assert list(window._links_by_id.items()) == [(9, new_url), (4, URL)]
        assert list(window.jobs_panel._cards) == [9, 4]
        orchestrator = window.orchestrator
        assert orchestrator._pending_jobs == [(9, new_url), (4, URL)]
        assert orchestrator.add_jobs([URL]) == [10]
        fid, url = orchestrator._pending_jobs[1]
        task = worker.DownloadWorker(fid, url, ProxyPool(), SessionState(), output_root=orchestrator.output_root,
                                     connections_per_file=2)
        complete = []
        task.all_done.connect(complete.append)
        task.run()
        assert complete == [4]
        assert (final_output_dir(FILE_NAME, 4, root) / "ciclo_1" / FILE_NAME).read_bytes() == CONTENTS
    finally:
        window.close()
        window.deleteLater()
