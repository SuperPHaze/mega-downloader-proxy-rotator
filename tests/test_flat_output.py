"""Destinazioni condivise, nomi occupati e proprietà dei file del singolo download."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from Crypto.Cipher import AES
from requests import Response

from src.core import partial_downloads as partials
from src.core.mega_links import build_folder_job_url
from src.core.state import SessionState
from src.downloader import mega_client, parallel_client
from src.downloader.target_file import JobFiles
from src.downloader.worker import DownloadWorker

URL = "https://mega.nz/file/Example1#test-key"
NAME = "Film.mkv"


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(partials, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(partials, "completion_records", lambda: [])
    monkeypatch.setattr(partials, "read_failed_links", lambda: [])
    monkeypatch.setattr(partials.session_store, "load", lambda: [])
    path = tmp_path / "downloads"
    path.mkdir()
    return path


def offline_worker(url, root, monkeypatch, data, connections, cycles=1):
    handle = partials.link_handle(url)
    cdn = "https://example.invalid/offline"
    encrypted = AES.new(bytes(16), AES.MODE_CTR, nonce=b"", initial_value=0).encrypt(data)
    info = dict(handle=handle, k=(0,) * 4, iv=(0, 0), cdn_url=cdn, file_size=len(data), file_name=NAME)
    monkeypatch.setattr(mega_client.MegaPublicClient, "resolve_public_url", lambda *args: info)
    monkeypatch.setattr(parallel_client.ParallelMegaDownloader, "_resolve_cdn",
                        lambda *args: (handle, info["k"], info["iv"], cdn, len(data), NAME))
    requests = []

    def get(address, *, headers, **kwargs):
        assert address == cdn
        response = Response()
        response._content_consumed = True
        if "Range" in headers:
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
            response.status_code = 206
            response._content = encrypted[start:end + 1]
            requests.append((start, end))
        else:
            response.status_code = 200
            response._content = encrypted
            requests.append(None)
        return response

    monkeypatch.setattr(mega_client.requests, "get", get)
    monkeypatch.setattr(mega_client.MegaClient, "get_egress_ip", lambda self: "offline")
    monkeypatch.setattr("src.downloader.worker.DOWNLOAD_CYCLES", cycles)
    pool = Mock()
    pool.get_next.return_value = {"protocol": "http", "host": "localhost", "port": 1}
    pool.score_of.return_value = 1
    worker = DownloadWorker(3, url, pool, SessionState(), output_root=root, connections_per_file=connections)
    # Un errore nei test deve uscire al primo tentativo, senza aprire connessioni o attendere.
    monkeypatch.setattr("src.downloader.worker.MAX_ATTEMPTS_PER_FILE", cycles + 1)
    worker._sleep_interruptible = lambda _: True
    return worker, requests


@pytest.mark.parametrize("connections", [1, 2])
@pytest.mark.parametrize("data", [b"sample film", b""])
def test_single_file_uses_root_without_disturbing_other_downloads(root, monkeypatch, connections, data):
    existing = root / "megapy_other.tmp"
    existing.write_bytes(b"keep")
    worker, _ = offline_worker(URL, root, monkeypatch, data, connections)
    paths = []
    worker.file_resolved.connect(lambda fid, name, size, path: paths.append(Path(path)))
    worker.run()
    assert paths == [root / NAME]
    assert (root / NAME).read_bytes() == data
    assert existing.read_bytes() == b"keep"
    assert set(root.iterdir()) == {root / NAME, existing}


@pytest.mark.parametrize("connections", [1, 2])
def test_repeated_single_file_uses_numbered_names_and_exact_deletion(root, monkeypatch, connections):
    original = root / NAME
    original.write_bytes(b"previous")
    worker, _ = offline_worker(URL, root, monkeypatch, b"new", connections, cycles=2)
    worker.run()
    copies = [root / "Film (2).mkv", root / "Film (3).mkv"]
    assert [p.read_bytes() for p in copies] == [b"new", b"new"]
    assert worker.files.discard() == []
    assert set(worker.files.discard(include_completed=True)) == set(copies)
    assert list(root.iterdir()) == [original]
    assert original.read_bytes() == b"previous"


@pytest.mark.parametrize("connections", [1, 2])
def test_folder_keeps_only_its_real_directories(root, monkeypatch, connections):
    relative = ("Rassegna", "Interviste", NAME)
    url = build_folder_job_url("FolderID", "Example1", "S2VZ", relative, size=4)
    worker, _ = offline_worker(url, root, monkeypatch, b"film", connections)
    worker.run()
    assert (root.joinpath(*relative)).read_bytes() == b"film"
    assert sorted(path.relative_to(root).as_posix() for path in root.rglob("*")) == [
        "Rassegna", "Rassegna/Interviste", "Rassegna/Interviste/Film.mkv",
    ]


def test_concurrent_reservations_and_existing_partial_never_share_a_name(root):
    held = JobFiles(root)
    other = JobFiles(root)
    (root / "Film (2).mkv.part").write_bytes(b"pending")
    with held.destination(root, NAME) as first, other.destination(root, NAME) as second:
        assert first == root / NAME
        assert second == root / "Film (3).mkv"
        assert JobFiles(root).discard(include_completed=True) == []
    assert [p.name for p in root.iterdir()] == ["Film (2).mkv.part"]


def test_replaced_file_cannot_be_published_or_deleted(root):
    files = JobFiles(root)
    with files.destination(root, NAME) as final:
        part = root / (NAME + ".part")
        part.write_bytes(b"film")
        files.started(final, URL, 4, NAME)
        part.rename(root / "saved")
        part.write_bytes(b"keep")
        with pytest.raises(partials.RecoveryChanged):
            files.publish(final)
        with pytest.raises(partials.RecoveryChanged):
            files.discard()
    assert part.read_bytes() == b"keep"
    assert not final.exists()
    final.write_bytes(b"film")
    files.finished(final)
    final.rename(root / "moved")
    final.write_bytes(b"keep")
    with pytest.raises(partials.RecoveryChanged):
        files.discard(include_completed=True)
    assert final.read_bytes() == b"keep"


def test_numbered_partial_can_be_recovered_after_quitting(root, monkeypatch):
    original = root / NAME
    original.write_bytes(b"existing")
    files = JobFiles(root)
    block = 1024 * 1024
    data = b"A" * block + b"B" * 25
    with files.destination(root, NAME) as target:
        part = target.with_name(target.name + ".part")
        part.write_bytes(data[:block] + bytes(25))
        files.started(target, URL, len(data), NAME, block)
        parallel_client._save_progress(part, "Example1", len(data), {(0, block - 1)}, block)
    recovery, = partials.scan_partials(root)
    assert (recovery.target.name, recovery.source_name, recovery.saved) == ("Film (2).mkv", NAME, block)
    worker, requests = offline_worker(URL, root, monkeypatch, data, 1)
    restored = DownloadWorker(0, URL, worker.proxy_pool, SessionState(), output_root=root,
                              connections_per_file=1, recovery=recovery)
    restored.run()
    assert requests == [(block, len(data) - 1)]
    assert target.read_bytes() == data
    assert original.read_bytes() == b"existing"
    assert set(root.iterdir()) == {original, target}


def test_interrupted_serial_attempt_reuses_its_numbered_partial(root, monkeypatch):
    original = root / NAME
    original.write_bytes(b"existing")
    data = b"the complete video"
    worker, requests = offline_worker(URL, root, monkeypatch, data, 1)
    get = mega_client.requests.get

    def interrupt_serial(url, **kwargs):
        response = get(url, **kwargs)
        if "Range" not in kwargs["headers"]:
            response._content = response._content[:4]
        return response

    monkeypatch.setattr(mega_client.requests, "get", interrupt_serial)
    worker.run()
    target = root / "Film (2).mkv"
    assert requests == [None, (0, len(data) - 1)]
    assert target.read_bytes() == data
    assert original.read_bytes() == b"existing"
    assert set(root.iterdir()) == {original, target}


def test_working_names_do_not_overwrite_user_files(root):
    files = JobFiles(root)
    foreign_lock = root / (NAME + ".part.lock")
    foreign_lock.write_bytes(b"existing")
    with files.destination(root, NAME) as target:
        assert target.name == "Film (2).mkv"
        checkpoint = target.name + ".part.progress.json"
        with JobFiles(root).destination(root, checkpoint) as unrelated:
            assert unrelated.name == "Film (2).mkv.part.progress (2).json"
    assert foreign_lock.read_bytes() == b"existing"
