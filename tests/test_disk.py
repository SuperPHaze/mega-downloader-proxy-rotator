# Test per il check dello spazio su disco (nessuna rete). Il free reale del
# volume viene monkeypatchato per testare le soglie in modo deterministico.
import pytest

from src.core import disk
from src.core.disk import InsufficientDiskSpaceError, ensure_free_space


def _patch_free(monkeypatch, free_bytes):
    monkeypatch.setattr(disk, "free_space_bytes", lambda _p: free_bytes)


def test_enough_space_does_not_raise(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 1_000)
    ensure_free_space(tmp_path, needed_bytes=500, margin_bytes=100)  # 600 <= 1000


def test_insufficient_space_raises(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 1_000)
    with pytest.raises(InsufficientDiskSpaceError):
        ensure_free_space(tmp_path, needed_bytes=950, margin_bytes=100)  # 1050 > 1000


def test_margin_pushes_over_the_limit(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 1_000)
    # Il file da solo entrerebbe, ma il margine lo fa sforare.
    with pytest.raises(InsufficientDiskSpaceError):
        ensure_free_space(tmp_path, needed_bytes=1_000, margin_bytes=1)


def test_zero_needed_is_noop(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 0)
    ensure_free_space(tmp_path, needed_bytes=0, margin_bytes=100)  # non solleva


def test_free_space_walks_up_to_existing_parent(tmp_path):
    # Un path inesistente non deve far fallire: si risale al primo antenato reale.
    missing = tmp_path / "a" / "b" / "c"
    assert disk.free_space_bytes(missing) > 0


def test_insufficient_error_is_oserror():
    # Deve essere catturabile come OSError (è un errore d'ambiente).
    assert issubclass(InsufficientDiskSpaceError, OSError)
