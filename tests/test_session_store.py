# Test per il ripristino sessione (2.7). Il path del file è monkeypatchato su
# tmp_path per non toccare la root del progetto. Nessuna rete, nessuna GUI.
import json

from src.core import session_store


def _use_tmp(monkeypatch, tmp_path):
    target = tmp_path / "session_state.json"
    monkeypatch.setattr(session_store, "_path", lambda: target)
    return target


def test_load_empty_when_absent(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert session_store.load() == []


def test_save_load_roundtrip(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert session_store.save(["a", "b"]) is True
    assert session_store.load() == ["a", "b"]


def test_clear_removes_state(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    session_store.save(["x"])
    session_store.clear()
    assert session_store.load() == []


def test_bad_json_returns_empty(monkeypatch, tmp_path):
    target = _use_tmp(monkeypatch, tmp_path)
    target.write_text("{not json", encoding="utf-8")
    assert session_store.load() == []


def test_unknown_schema_returns_empty(monkeypatch, tmp_path):
    target = _use_tmp(monkeypatch, tmp_path)
    target.write_text(json.dumps({"schema": 999, "urls": ["a"]}), encoding="utf-8")
    assert session_store.load() == []


def test_load_filters_non_string_entries(monkeypatch, tmp_path):
    target = _use_tmp(monkeypatch, tmp_path)
    target.write_text(
        json.dumps({"schema": 1, "urls": ["a", 5, "", None, "b"]}), encoding="utf-8"
    )
    assert session_store.load() == ["a", "b"]
