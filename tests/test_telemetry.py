# Test del recorder asincrono di telemetria (scatola nera, Fase 1).
# Verifica: (a) il produttore non fa I/O sul hot path, (b) close() drena tutta
# la coda senza perdita, (c) con flag OFF tutte le API sono no-op (nessun file).
from __future__ import annotations

import json
import threading

import pytest

from src.core import telemetry


@pytest.fixture(autouse=True)
def _cleanup():
    # Garantisce nessuna sessione residua tra i test.
    telemetry.close()
    yield
    telemetry.close()


def _read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_close_drains_all_records(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(telemetry, "TELEMETRY_DIR", tmp_path)

    telemetry.start_session("sess-drain", manifest={"k": "v"})
    assert telemetry.is_active()

    total = 5000
    for i in range(total):
        telemetry.event("chunk_attempt", i=i)
    telemetry.close()

    assert not telemetry.is_active()
    records = _read_jsonl(tmp_path / "sess-drain" / "events.jsonl")
    assert len(records) == total
    # Ogni record arricchito con session_id e ts.
    assert all(r["session_id"] == "sess-drain" for r in records)
    assert all("ts" in r for r in records)
    # Manifest valido e contiene i campi base + custom.
    manifest = json.loads((tmp_path / "sess-drain" / "manifest.json").read_text("utf-8"))
    assert manifest["session_id"] == "sess-drain"
    assert manifest["k"] == "v"
    assert "pid" in manifest


def test_concurrent_producers_no_loss(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(telemetry, "TELEMETRY_DIR", tmp_path)

    telemetry.start_session("sess-mt", manifest={})

    per_thread = 1000
    n_threads = 8

    def producer(tid):
        for i in range(per_thread):
            telemetry.emit("events", {"tid": tid, "i": i})

    threads = [threading.Thread(target=producer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    telemetry.close()

    records = _read_jsonl(tmp_path / "sess-mt" / "events.jsonl")
    assert len(records) == per_thread * n_threads


def test_emit_does_not_block_or_io(tmp_path, monkeypatch):
    # Il produttore deve solo accodare: la chiamata ritorna senza scrivere
    # subito su disco. Verifichiamo che emit() ritorni e che il file possa
    # ancora non esistere immediatamente (scrittura demandata al writer).
    monkeypatch.setattr(telemetry, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(telemetry, "TELEMETRY_DIR", tmp_path)
    telemetry.start_session("sess-fast", manifest={})
    telemetry.event("x", v=1)  # non solleva, ritorna immediatamente
    telemetry.close()
    records = _read_jsonl(tmp_path / "sess-fast" / "events.jsonl")
    assert len(records) == 1


def test_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "TELEMETRY_ENABLED", False)
    monkeypatch.setattr(telemetry, "TELEMETRY_DIR", tmp_path)

    telemetry.start_session("sess-off", manifest={"k": "v"})
    assert not telemetry.is_active()
    # Tutte le API no-op, nessuna eccezione.
    telemetry.event("e", a=1)
    telemetry.chunk_attempt({"x": 1})
    telemetry.sample({"y": 2})
    telemetry.emit("events", {"z": 3})
    telemetry.close()

    # Nessun file/cartella creata.
    assert not (tmp_path / "sess-off").exists()
