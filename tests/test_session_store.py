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


def test_restore_matches_individual_copies_and_reserves_removed_ids(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    session_store.save({4: "one", 11: "duplicate", 7: "duplicate", 12: "removed"}, next_id=19)
    jobs, following = session_store.restore_jobs(["duplicate", "new", "one", "duplicate", "duplicate"], tmp_path)
    assert list(jobs.items()) == [(11, "duplicate"), (19, "new"), (4, "one"),
                                  (7, "duplicate"), (20, "duplicate")]
    assert following == 21
    # Complete the highest ID and close again. Its number remains reserved.
    session_store.save({4: "one"}, next_id=following)
    assert session_store.restore_jobs(["one", "later"], tmp_path) == ({4: "one", 21: "later"}, 22)


def test_restore_legacy_partial_only_for_unique_directory(monkeypatch, tmp_path):
    from src.downloader.worker import job_output_dir

    _use_tmp(monkeypatch, tmp_path)
    session_store.save(["one", "many", "dup", "dup"])
    for url, fid in [("one", 4), ("many", 1), ("many", 2), ("dup", 6), ("dup", 7)]:
        cycle = job_output_dir(url, fid, tmp_path) / "ciclo_1"
        cycle.mkdir(parents=True)
        (cycle / "sample.part").write_bytes(b"partial")
    jobs, following = session_store.restore_jobs(["dup", "one", "many", "dup"], tmp_path)
    assert jobs == {8: "dup", 4: "one", 9: "many", 10: "dup"}
    assert following == 11
    assert (job_output_dir("one", 4, tmp_path) / "ciclo_1" / "sample.part").read_bytes() == b"partial"


def test_malformed_identity_metadata_preserves_legacy_urls(monkeypatch, tmp_path):
    path = _use_tmp(monkeypatch, tmp_path)
    for bad_ids in [[4, 4], [False, 2], [2**64, 8], [9], [[], 3]]:
        path.write_text(json.dumps({"schema": 1, "urls": ["a", "b"], "file_ids": bad_ids}))
        assert session_store.restore_jobs(["a", "b"], tmp_path) == ({0: "a", 1: "b"}, 2)
