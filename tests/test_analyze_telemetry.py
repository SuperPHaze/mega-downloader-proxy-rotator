# Test dell'analizzatore telemetria offline (Fase 3, tools/analyze_telemetry.py).
# Funzioni pure su fixture inline + end-to-end su sessione fittizia minima +
# caso degenere (riga corrotta / campi null) che non deve far crashare nulla.
from __future__ import annotations

import json

from tools import analyze_telemetry as at


# === Funzioni pure =========================================================

def test_pct_basic():
    assert at.pct([], 0.5) is None
    assert at.pct([10], 0.9) == 10
    xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert at.pct(xs, 0.5) == 6
    assert at.pct(xs, 0.9) == 10


def _ca(outcome, tp_bps=None, **extra):
    r = {"event_type": "chunk_attempt", "outcome": outcome,
         "proxy_host": "h", "proxy_port": "1", "proxy_source": "src",
         "proxy_protocol": "http", "egress_ip": "h:1", "t_total_ms": 1000}
    if tp_bps is not None:
        r["throughput_bps"] = tp_bps
    r.update(extra)
    return r


def test_rollup_percentiles_and_okrate():
    ca = [
        _ca("ok", 1024 * 1000),   # 1000 KB/s
        _ca("ok", 1024 * 500),    # 500 KB/s
        _ca("http_403"),
    ]
    out = at.rollup(ca, lambda r: r.get("proxy_source"))
    assert len(out) == 1
    row = out[0]
    assert row["attempts"] == 3
    assert row["ok"] == 2
    assert row["ok_rate"] == round(100 * 2 / 3)
    assert row["thr_kbs_p50"] in (500, 1000)
    assert row["thr_kbs_p99"] == 1000


def test_analyze_decomposition_and_outcomes():
    ca = [
        _ca("ok", 1024 * 800, t_transfer_ms=900),
        _ca("ok", 1024 * 900, t_transfer_ms=950),
        _ca("timeout_read", t_total_ms=2000),
    ]
    R = at.analyze([{"session_id": "s", "connections_per_file": 4}], ca, [], [])
    assert R["totals"]["chunk_attempts"] == 3
    assert R["totals"]["ok"] == 2
    assert R["outcomes"]["ok"] == 2
    assert R["outcomes"]["timeout_read"] == 1
    # Decomposizione: produttivo = somma t_transfer_ms degli ok.
    assert R["decomposition"]["productive_transfer_s"] == round((900 + 950) / 1000)
    # Spreco: il timeout contribuisce ai falliti.
    assert R["decomposition"]["failed_attempt_s"] == 2
    cats = {w["outcome"] for w in R["waste_by_category"]}
    assert "timeout_read" in cats


# === Classificatore del vincolo (C4) =======================================

def _smp(sec, bps, pa, pc):
    return {"ts": f"2026-01-01T00:{sec // 60:02d}:{sec % 60:02d}.000",
            "instant_bps": bps, "pool_alive": pa, "pool_cooldown": pc,
            "file_id": 0, "session_id": "s"}


def _att(sec, dur_ms):
    return {"event_type": "chunk_attempt", "outcome": "ok",
            "ts_start": f"2026-01-01T00:{sec // 60:02d}:{sec % 60:02d}.000",
            "t_total_ms": dur_ms, "file_id": 0, "session_id": "s"}


def test_binding_line_bound_when_saturated():
    # Capacita' 1000 B/s, throughput 950 -> util 0.95 >= 0.85 -> line_bound.
    sm = [_smp(10, 950, 10, 0)]
    bw = at._bandwidth_analysis(sm, [], link_capacity_bps=1000, connections=10)
    assert bw["available"] is True
    assert bw["dominant_binding"] == "line_bound"
    assert bw["util_p50"] == 0.95


def test_binding_rate_limit_when_cooldown_dominant():
    # cooldown 6 >= 0.5*(4+6)=5 -> rate_limit_bound (capacita' ignota).
    sm = [_smp(10, 100, 4, 6)]
    bw = at._bandwidth_analysis(sm, [], link_capacity_bps=None, connections=10)
    assert bw["dominant_binding"] == "rate_limit_bound"
    # Senza capacita': niente metriche di utilizzo.
    assert "util_p50" not in bw


def test_binding_pool_bound_when_few_alive():
    # pool_alive 3 < connections 10, niente cooldown -> pool_bound.
    sm = [_smp(10, 100, 3, 0)]
    bw = at._bandwidth_analysis(sm, [], link_capacity_bps=None, connections=10)
    assert bw["dominant_binding"] == "pool_bound"


def test_binding_lane_supply_vs_proxy_speed():
    # connections=4. Secondo 300: 4 corsie attive -> proxy_speed_bound.
    #                Secondo 400: 1 corsia attiva (<2.8) -> lane_supply_bound.
    ca = [_att(300, 1000), _att(300, 1000), _att(300, 1000), _att(300, 1000),
          _att(400, 1000)]
    sm = [_smp(300, 100, 10, 0), _smp(400, 100, 10, 0)]
    bw = at._bandwidth_analysis(sm, ca, link_capacity_bps=None, connections=4)
    states = bw["binding_states_pct"]
    assert "proxy_speed_bound" in states
    assert "lane_supply_bound" in states
    # Le due finestre hanno lo stesso peso (un secondo ciascuna).
    assert sum(states.values()) in (100, 101)


def test_binding_no_samples_unavailable():
    bw = at._bandwidth_analysis([], [], link_capacity_bps=300_000_000, connections=10)
    assert bw["available"] is False


# === Fixture sessione fittizia =============================================

def _make_session(d, sid="20260101-000000"):
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "session_id": sid, "app_version": "9.9.9",
        "connections_per_file": 2, "chunk_size_bytes": 8 * 1024 * 1024,
        "selection_mode": "score", "n_links": 1,
        "link_capacity_mbit": 100.0, "link_capacity_bps": 12_500_000,
        "config": {"PARALLEL_SEGMENT_RETRIES": 8},
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    events = [
        {"event_type": "file_started", "file_id": 0, "session_id": sid,
         "ts": "2026-01-01T00:00:00.000"},
        {"event_type": "file_plan", "file_id": 0, "n_chunks": 3,
         "file_size": 24 * 1024 * 1024, "resumed_chunks": 0, "session_id": sid,
         "ts": "2026-01-01T00:00:01.000"},
        {"event_type": "file_resolved", "file_id": 0, "resolve_ms": 120.0,
         "session_id": sid, "ts": "2026-01-01T00:00:00.500"},
        {"event_type": "chunk_attempt", "file_id": 0, "chunk_idx": 0, "attempt": 1,
         "outcome": "ok", "throughput_bps": 1024 * 1000, "t_total_ms": 8000,
         "t_transfer_ms": 7800, "proxy_host": "a", "proxy_port": "1",
         "proxy_source": "src1", "proxy_protocol": "http", "egress_ip": "1.1.1.1",
         "intra_samples": [[10, 65536], [20, 131072]], "ts_start": "2026-01-01T00:00:02.000",
         "session_id": sid, "ts": "2026-01-01T00:00:10.000"},
        {"event_type": "chunk_attempt", "file_id": 0, "chunk_idx": 1, "attempt": 1,
         "outcome": "http_509", "t_total_ms": 500, "backoff_s": 2,
         "proxy_host": "b", "proxy_port": "2", "proxy_source": "src2",
         "proxy_protocol": "socks5", "egress_ip": "2.2.2.2",
         "ts_start": "2026-01-01T00:00:03.000", "session_id": sid,
         "ts": "2026-01-01T00:00:03.600"},
        {"event_type": "chunk_attempt", "file_id": 0, "chunk_idx": 1, "attempt": 2,
         "outcome": "ok", "throughput_bps": 1024 * 400, "t_total_ms": 9000,
         "t_transfer_ms": 8800, "proxy_host": "c", "proxy_port": "3",
         "proxy_source": "src1", "proxy_protocol": "http", "egress_ip": "3.3.3.3",
         "intra_samples": [[10, 65536]], "ts_start": "2026-01-01T00:00:04.000",
         "session_id": sid, "ts": "2026-01-01T00:00:13.000"},
    ]
    with open(d / "events.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    samples = []
    for i in range(5):
        samples.append({
            "file_id": 0, "url_hash": "abc", "bytes_done": i * 1024 * 1024,
            "total_size": 24 * 1024 * 1024, "instant_bps": (i + 1) * 500 * 1024,
            "pool_alive": 50, "pool_cooldown": 1, "pool_discarded": 0,
            "refill_count": 0, "session_id": sid,
            "ts": f"2026-01-01T00:00:{10 + i:02d}.000",
        })
    with open(d / "samples.jsonl", "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
    return d


def test_end_to_end(tmp_path):
    sess = _make_session(tmp_path / "sess")
    out = tmp_path / "out"
    rc = at.main([str(sess), "--out", str(out), "--firehose"])
    assert rc == 0

    for name in ["chunk_attempts.csv", "samples.csv", "files.csv",
                 "sources.csv", "protocols.csv", "proxies.csv", "ips.csv",
                 "telemetry_report.html", "telemetry_report.md",
                 "telemetry_ai_export.json", "intra_samples_long.csv"]:
        assert (out / name).exists(), name

    # AI export: JSON valido < 15 KB.
    ai_path = out / "telemetry_ai_export.json"
    ai = json.loads(ai_path.read_text(encoding="utf-8"))
    assert ai_path.stat().st_size < 15000
    assert set(ai.keys()) == {"schema_hint", "summary", "examples"}
    assert ai["summary"]["totals"]["chunk_attempts"] == 3
    # Blocco bandwidth presente e con capacita' nota (dal manifest fixture).
    bw = ai["summary"]["bandwidth"]
    assert bw["available"] is True
    assert "util_p50" in bw
    assert bw["dominant_binding"] is not None

    # Firehose: 3 campioni intra totali (2 + 0 + 1).
    lines = (out / "intra_samples_long.csv").read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "session_id,file_id,chunk_idx,attempt,t_offset_ms,cum_bytes"
    assert len(lines) - 1 == 3


def test_degenerate_input_no_crash(tmp_path):
    sess = tmp_path / "bad"
    sess.mkdir()
    (sess / "manifest.json").write_text(
        json.dumps({"session_id": "bad", "connections_per_file": 2}), encoding="utf-8")
    # events.jsonl con riga corrotta, record non-dict e campi null.
    with open(sess / "events.jsonl", "w", encoding="utf-8") as f:
        f.write("{ this is not valid json\n")
        f.write(json.dumps([1, 2, 3]) + "\n")  # non-dict
        f.write(json.dumps({"event_type": "chunk_attempt", "outcome": None,
                            "throughput_bps": None, "t_total_ms": None,
                            "proxy_host": None, "proxy_port": None}) + "\n")
        f.write(json.dumps({"event_type": "chunk_attempt", "outcome": "ok",
                            "throughput_bps": 1024 * 100, "t_total_ms": 1000,
                            "t_transfer_ms": 900}) + "\n")
    (sess / "samples.jsonl").write_text("garbage line\n", encoding="utf-8")

    out = tmp_path / "out_bad"
    rc = at.main([str(sess), "--out", str(out)])
    assert rc == 0
    assert (out / "chunk_attempts.csv").exists()
    ai = json.loads((out / "telemetry_ai_export.json").read_text(encoding="utf-8"))
    assert ai["summary"]["totals"]["chunk_attempts"] == 2


def test_parent_folder_union(tmp_path):
    parent = tmp_path / "telemetry"
    _make_session(parent / "s1", sid="20260101-000001")
    _make_session(parent / "s2", sid="20260101-000002")
    out = tmp_path / "union_out"
    rc = at.main([str(parent), "--out", str(out)])
    assert rc == 0
    ai = json.loads((out / "telemetry_ai_export.json").read_text(encoding="utf-8"))
    assert ai["summary"]["n_sessions"] == 2
    # Unione: 3 + 3 tentativi-chunk.
    assert ai["summary"]["totals"]["chunk_attempts"] == 6
    # files.csv ha una riga per (sessione, file).
    import csv
    rows = list(csv.DictReader(open(out / "files.csv", encoding="utf-8")))
    assert len(rows) == 2
    assert {r["session_id"] for r in rows} == {"20260101-000001", "20260101-000002"}
