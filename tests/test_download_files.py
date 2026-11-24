"""The normal download entry points, using a small file and an offline transport."""
from pathlib import Path
from threading import Event, Thread

import pytest
from Crypto.Cipher import AES

from src.core.file_naming import final_output_dir
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
