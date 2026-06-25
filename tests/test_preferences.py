# Test puri per le preferenze utente (connections_per_file). Reindirizza
# _PREFS_PATH su tmp_path: nessun file reale persistente nel progetto.
from src.core.config import PARALLEL_CONNECTIONS_PER_FILE
from src.gui import preferences


def test_load_connections_per_file_default_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    assert preferences.load_connections_per_file() == PARALLEL_CONNECTIONS_PER_FILE


def test_save_then_load_connections_per_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_connections_per_file(6)
    assert preferences.load_connections_per_file() == 6
