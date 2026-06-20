# Test puri per il sidecar di resume (_save_progress/_load_progress).
# Usa tmp_path di pytest: nessun file reale persistente nel progetto.
from src.downloader.parallel_client import _load_progress, _save_progress


def test_save_and_load_roundtrip(tmp_path):
    target = tmp_path / "file.bin.part"
    done = {(0, 15), (16, 31)}
    _save_progress(target, "HANDLE1", 100, done, chunk_size=16)
    loaded = _load_progress(target, "HANDLE1", 100, chunk_size=16)
    assert loaded == done


def test_missing_sidecar_returns_empty(tmp_path):
    target = tmp_path / "file.bin.part"
    assert _load_progress(target, "HANDLE1", 100, chunk_size=16) == set()


def test_invalidated_on_handle_change(tmp_path):
    target = tmp_path / "file.bin.part"
    _save_progress(target, "HANDLE1", 100, {(0, 15)}, chunk_size=16)
    loaded = _load_progress(target, "HANDLE2", 100, chunk_size=16)
    assert loaded == set()


def test_invalidated_on_file_size_change(tmp_path):
    target = tmp_path / "file.bin.part"
    _save_progress(target, "HANDLE1", 100, {(0, 15)}, chunk_size=16)
    loaded = _load_progress(target, "HANDLE1", 200, chunk_size=16)
    assert loaded == set()


def test_invalidated_on_chunk_size_change(tmp_path):
    target = tmp_path / "file.bin.part"
    _save_progress(target, "HANDLE1", 100, {(0, 15)}, chunk_size=16)
    loaded = _load_progress(target, "HANDLE1", 100, chunk_size=32)
    assert loaded == set()


def test_corrupted_sidecar_returns_empty_without_raising(tmp_path):
    target = tmp_path / "file.bin.part"
    sidecar = tmp_path / "file.bin.part.progress.json"
    sidecar.write_text("{not valid json", encoding="utf-8")
    assert _load_progress(target, "HANDLE1", 100, chunk_size=16) == set()


def test_completed_chunks_recognized_and_filtered(tmp_path):
    target = tmp_path / "file.bin.part"
    all_chunks = [(0, 15), (16, 31), (32, 47)]
    completed = {(0, 15), (32, 47)}
    _save_progress(target, "HANDLE1", 48, completed, chunk_size=16)
    loaded = _load_progress(target, "HANDLE1", 48, chunk_size=16)
    remaining = [c for c in all_chunks if c not in loaded]
    assert remaining == [(16, 31)]
