# Test puri per le preferenze utente (connections_per_file, segment_max_duration_s).
# Reindirizza _PREFS_PATH su tmp_path: nessun file reale persistente nel progetto.
from src.core.config import (
    PARALLEL_CONNECTIONS_PER_FILE,
    PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S,
)
from src.gui import preferences


def test_load_connections_per_file_default_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    assert preferences.load_connections_per_file() == PARALLEL_CONNECTIONS_PER_FILE


def test_save_then_load_connections_per_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_connections_per_file(6)
    assert preferences.load_connections_per_file() == 6


def test_load_segment_max_duration_s_default_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    assert preferences.load_segment_max_duration_s() == PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S


def test_save_then_load_segment_max_duration_s_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    preferences.save_segment_max_duration_s(300)
    assert preferences.load_segment_max_duration_s() == 300
