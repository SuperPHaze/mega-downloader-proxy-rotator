import json
from unittest.mock import Mock

import pytest
from requests import Response

pytest.importorskip("PyQt6.QtCore")

from src.core import partial_downloads as partials
from src.core.state import SessionState
from src.downloader import parallel_client as parallel
from src.downloader.target_file import target_lock
from src.downloader.worker import DownloadWorker


URL = "https://mega.nz/file/Example1#test-key"
BLOCK = 1024 * 1024


@pytest.fixture
def folder(tmp_path, monkeypatch):
    root = tmp_path / "downloads"
    root.mkdir()
    monkeypatch.setattr(partials, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(partials, "completion_records", lambda: [])
    monkeypatch.setattr(partials, "read_failed_links", lambda: [])
    monkeypatch.setattr(partials.session_store, "load", lambda: [])
    return root


def make_part(root, data, name="Film.mkv", done=None, legacy=False):
    directory = root / "Film.mkv_6" / "ciclo_1"
    directory.mkdir(parents=True, exist_ok=True)
    part = directory / (name if legacy else name + ".part")
    part.write_bytes(data)
    if done is not None:
        parallel._save_progress(part, "Example1", len(data), done, BLOCK)
    return part


def test_inventory_requires_real_files_and_real_ranges(folder, monkeypatch):
    data = bytes(2 * BLOCK)
    part = make_part(folder, data, done={(BLOCK, len(data)-1)})
    other = make_part(folder, data, "Altro.mkv")
    record = {"file_name": "Film.mkv", "file_size": len(data), "handle": "Example1", "url": URL}
    monkeypatch.setattr(partials, "completion_records", lambda: [record])
    (folder / "browser.part").touch()
    fresh, resume = partials.scan_partials(folder)
    assert (resume.saved, resume.url, resume.in_history) == (BLOCK, URL, True)
    assert fresh.saved == 0 and not fresh.url
    assert fresh.part == other
    for invalid in ({"done": [[1, BLOCK]]}, {"done": [[0, len(data) * 2]]}, {"file_size": 1}):
        parallel._save_progress(part, "Example1", len(data), {(0, BLOCK-1)}, BLOCK)
        checkpoint = parallel._progress_path(part)
        checkpoint.write_text(json.dumps(json.loads(checkpoint.read_text()) | invalid))
        assert partials.scan_partials(folder)[1].saved == 0
    assert part.read_bytes() == other.read_bytes() == data


def test_does_not_follow_linked_files_or_directories(folder):
    part = make_part(folder, bytes(32), done={(0, 31)})
    outside = folder.parent / "external"
    make_part(outside, bytes(32), done={(0, 31)})
    try:
        (part.parent / "Alias.mkv.part").symlink_to(part)
        (folder / "alias").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Cannot create a symbolic link on this volume: {exc}")
    entry, = partials.scan_partials(folder)
    assert entry.part == part


def test_old_link_lookup_requires_unique_name_and_size(folder, monkeypatch):
    make_part(folder, bytes(64))
    base = dict(file_name="Film.mkv", file_size=64, handle="Example1", url=URL)
    monkeypatch.setattr(partials, "completion_records", lambda: [base])
    entry, = partials.scan_partials(folder)
    assert (entry.url, entry.saved, entry.expected_size) == (URL, 0, 64)
    ambiguous = dict(base, handle="Example2", url=URL.replace("Example1", "Example2"))
    monkeypatch.setattr(partials, "completion_records", lambda: [base, ambiguous])
    assert not partials.scan_partials(folder)[0].url


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("occupied", [False, True])
def test_legacy_recovery_fetches_only_missing_bytes_and_publishes_in_root(folder, monkeypatch, legacy, occupied):
    from Crypto.Cipher import AES

    plain = b"A" * BLOCK + b"B" * BLOCK + b"original ending"
    disk = plain[:BLOCK] + bytes(BLOCK) + plain[2 * BLOCK:]
    part = make_part(folder, disk, done={(0, BLOCK-1), (2*BLOCK, len(plain)-1)}, legacy=legacy)
    unrelated = folder / "Film.mkv" if occupied else part.parent / "keep.txt"
    unrelated.write_text("keep")
    entry, = partials.scan_partials(folder, [URL])
    encrypted = AES.new(bytes(16), AES.MODE_CTR, nonce=b"", initial_value=0).encrypt(plain)
    requested = []
    def local_range(url, *, headers, **kwargs):
        assert url == "https://example.invalid/offline"
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        requested.append((start, end))
        response = Response()
        response.status_code = 206
        response._content_consumed = True
        response._content = encrypted[start:end+1]
        return response
    monkeypatch.setattr(parallel.requests, "get", local_range)
    monkeypatch.setattr(parallel.ParallelMegaDownloader, "_resolve_cdn", lambda *args:
                        ("Example1", (0,)*4, (0, 0), "https://example.invalid/offline", len(plain), "Film.mkv"))
    monkeypatch.setattr("src.downloader.worker.MegaClient.get_egress_ip", lambda self: "offline")
    pool = Mock()
    pool.get_next.return_value = {"host": "localhost", "port": 1}
    pool.score_of.return_value = 1
    # Nuova sessione, ID 0 e impostazione a connessione singola. Il parziale era del job 6.
    worker = DownloadWorker(0, URL, pool, SessionState(), connections_per_file=1,
                            chunk_size_bytes=4 * BLOCK, output_root=folder, recovery=entry)
    completed = []
    worker.all_done.connect(completed.append)
    worker.run()
    assert completed == [0]
    assert requested == [(BLOCK, 2*BLOCK-1)]
    final = folder / ("Film (2).mkv" if occupied else "Film.mkv")
    assert final.read_bytes() == plain
    assert not entry.target.exists()
    assert unrelated.read_text() == "keep"
    assert not entry.part.exists() and not parallel._progress_path(entry.part).exists()
    assert partials.scan_partials(folder) == []
    if occupied:
        assert set(folder.iterdir()) == {unrelated, final}
    else:
        assert set(folder.iterdir()) == {part.parent.parent, final}


@pytest.mark.parametrize("change", ["handle", "name", "size", "moved", "destination", "locked"])
def test_changed_file_never_gets_written(folder, monkeypatch, change):
    part = make_part(folder, b"original", done={(0, 7)})
    entry, = partials.scan_partials(folder, [URL])
    client = parallel.ParallelMegaDownloader(Mock(), 1, chunk_size=BLOCK)
    handle = "Example2" if change == "handle" else "Example1"
    name = "Other.mkv" if change == "name" else "Film.mkv"
    size = 15 if change == "size" else 8
    monkeypatch.setattr(client, "_resolve_cdn", lambda *args: (handle, (0,)*4, (0, 0), "local", size, name))
    if change == "moved":
        part.rename(part.with_suffix(".backup"))
        part.write_bytes(b"replaced")
    if change == "destination":
        entry.target.write_bytes(b"complete")
    def download():
        client.download(URL, part.parent, {}, recovery=entry)
    with pytest.raises(partials.RecoveryChanged):
        if change == "locked":
            with target_lock(entry.target):
                download()
        else:
            download()
    assert part.read_bytes() == (b"replaced" if change == "moved" else b"original")
    if change == "destination":
        assert entry.target.read_bytes() == b"complete"


def test_recovery_of_short_serial_file_and_private_source(folder, monkeypatch):
    part = make_part(folder, b"abc")
    partials.remember_source(part, URL, 7)
    assert not list(folder.rglob("*source*"))
    entry, = partials.scan_partials(folder)
    assert (entry.saved, entry.size, entry.expected_size, entry.url) == (0, 3, 7, URL)
    client = parallel.ParallelMegaDownloader(Mock(), 1)
    monkeypatch.setattr(client, "_resolve_cdn", lambda *args: ("Example1", (0,)*4, (0, 0), "local", 7, "Film.mkv"))
    def receive(index, start, end, cdn, key, counter, path, *args):
        assert (start, end) == (0, 6)
        with path.open("r+b") as stream:
            stream.write(b"newfilm")
    monkeypatch.setattr(client, "_download_chunk", receive)
    assert client.download(URL, part.parent, {}, recovery=entry).read_bytes() == b"newfilm"
    assert not list((folder.parent / "logs").rglob("*.json"))


def test_destination_created_during_transfer_is_preserved(folder, monkeypatch):
    part = make_part(folder, bytes(8))
    entry, = partials.scan_partials(folder)
    client = parallel.ParallelMegaDownloader(Mock(), 1)
    monkeypatch.setattr(client, "_resolve_cdn", lambda *args: ("Example1", (0,)*4, (0, 0), "local", 8, "Film.mkv"))
    def receive(*args):
        entry.target.write_bytes(b"another completed file")
        part.write_bytes(b"recovery")
        parallel._save_progress(part, "Example1", 8, {(0, 7)}, BLOCK)
    monkeypatch.setattr(client, "_download_chunk", receive)
    with pytest.raises(partials.RecoveryChanged):
        client.download(URL, part.parent, {}, recovery=entry)
    assert entry.target.read_bytes() == b"another completed file"
    assert part.read_bytes() == b"recovery"
    assert parallel._progress_path(part).is_file()


def test_removing_one_recovered_file_preserves_its_neighbours(folder):
    part = make_part(folder, b"original", done={(0, 7)})
    entry, = partials.scan_partials(folder)
    neighbour = part.parent / "another.mkv"
    neighbour.write_text("keep")
    partials.remember_source(part, URL, 8)
    entry.remove()
    assert not part.exists() and not parallel._progress_path(part).exists()
    assert not list((folder.parent / "logs").rglob("*.json"))
    assert neighbour.read_text() == "keep"
