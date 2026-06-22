# Test puri per tools/report.py: nessuna rete, file su tmp_path. Il modulo
# legge events.jsonl (+ rotazioni) e crash.log in streaming, senza modificarli.
import json

from tools import report as rpt

SAMPLE_EVENTS = [
    {
        "ts": "2026-06-22T10:00:00.000", "level": "INFO", "logger": "diagnostics",
        "thread": "MainThread", "msg": "SESSION START v1.8.3 pid=1234",
        "event_type": "session_start", "app_version": "1.8.3", "pid": 1234,
    },
    {
        "ts": "2026-06-22T10:00:05.000", "level": "INFO", "logger": "diagnostics",
        "thread": "MainThread", "msg": "HEARTBEAT mem_rss=120.0 threads=8 download_attivi=1 pool_vivi=60",
        "event_type": "heartbeat", "mem_rss_mb": 120.0, "threads": 8,
        "download_attivi": 1, "pool_vivi": 60,
    },
    {
        "ts": "2026-06-22T10:01:05.000", "level": "INFO", "logger": "diagnostics",
        "thread": "MainThread", "msg": "HEARTBEAT mem_rss=150.0 threads=9 download_attivi=1 pool_vivi=55",
        "event_type": "heartbeat", "mem_rss_mb": 150.0, "threads": 9,
        "download_attivi": 1, "pool_vivi": 55,
    },
    {
        "ts": "2026-06-22T10:01:10.000", "level": "WARNING", "logger": "src.downloader.parallel_client",
        "thread": "ParallelChunk_0", "msg": "[parallel] chunk fallito: esauriti 8 tentativi (boom)",
    },
    {
        "ts": "2026-06-22T10:01:30.000", "level": "INFO", "logger": "src.downloader.orchestrator",
        "thread": "MainThread", "msg": "Download completato file_id=3 file_name=test.bin",
        "event_type": "download_completed", "file_id": 3,
        "url": "https://mega.nz/file/AAA#BBB", "file_name": "test.bin", "file_size": 1024,
    },
    {
        "ts": "2026-06-22T10:01:31.000", "level": "INFO", "logger": "diagnostics",
        "thread": "MainThread", "msg": "SESSION CLEAN EXIT", "event_type": "session_clean_exit",
    },
]

SAMPLE_CRASH_LOG = """\
2026-06-22T10:01:10 [THREAD-EXC] ParallelChunk_0
Traceback (most recent call last):
  File "parallel_client.py", line 50, in run
    raise RuntimeError("kaboom")
RuntimeError: kaboom

"""


def _write_jsonl(path, records, extra_malformed_lines=0):
    lines = [json.dumps(r) for r in records]
    for _ in range(extra_malformed_lines):
        lines.append("{questo non e' json valido")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# === find_events_log_files =================================================

def test_find_events_log_files_orders_chronologically(tmp_path, monkeypatch):
    monkeypatch.setattr(rpt, "EVENTS_LOG_BACKUPS", 2)
    (tmp_path / "events.jsonl.2").write_text("old\n", encoding="utf-8")
    (tmp_path / "events.jsonl.1").write_text("mid\n", encoding="utf-8")
    (tmp_path / "events.jsonl").write_text("current\n", encoding="utf-8")
    files = rpt.find_events_log_files(tmp_path)
    assert [f.name for f in files] == ["events.jsonl.2", "events.jsonl.1", "events.jsonl"]


def test_find_events_log_files_skips_missing(tmp_path):
    (tmp_path / "events.jsonl").write_text("current\n", encoding="utf-8")
    files = rpt.find_events_log_files(tmp_path)
    assert [f.name for f in files] == ["events.jsonl"]


# === stream_records ==========================================================

def test_stream_records_counts_malformed_lines(tmp_path):
    p = tmp_path / "events.jsonl"
    _write_jsonl(p, SAMPLE_EVENTS[:2], extra_malformed_lines=2)
    malformed = [0]
    records = list(rpt.stream_records([p], malformed))
    assert len(records) == 2
    assert malformed[0] == 2


# === build_sessions ===========================================================

def test_build_sessions_reconstructs_single_clean_session():
    sessions, orphan_errors, orphan_downloads = rpt.build_sessions(SAMPLE_EVENTS)
    assert len(sessions) == 1
    assert orphan_errors == []
    assert orphan_downloads == []

    s = sessions[0]
    assert s.version == "1.8.3"
    assert s.pid == 1234
    assert s.clean_exit is True
    assert s.outcome == "CLEAN"
    assert len(s.heartbeats) == 2
    assert [h.mem_rss_mb for h in s.heartbeats] == [120.0, 150.0]
    assert len(s.errors) == 1
    assert s.errors[0].level == "WARNING"
    assert len(s.downloads) == 1
    assert s.downloads[0].event_type == "download_completed"
    assert s.downloads[0].file_name == "test.bin"
    assert s.downloads[0].file_id == 3


def test_build_sessions_without_clean_exit_is_truncated():
    records = SAMPLE_EVENTS[:3]  # session_start + 2 heartbeat, niente clean_exit
    sessions, _, _ = rpt.build_sessions(records)
    assert len(sessions) == 1
    assert sessions[0].clean_exit is False
    assert sessions[0].outcome == "TRONCATA"


def test_build_sessions_records_without_session_go_to_orphans():
    records = SAMPLE_EVENTS[3:5]  # warning + download_completed, nessun session_start prima
    sessions, orphan_errors, orphan_downloads = rpt.build_sessions(records)
    assert sessions == []
    assert len(orphan_errors) == 1
    assert len(orphan_downloads) == 1


# === parse_crash_log / attribute_crashes =====================================

def test_parse_crash_log_thread_exc_entry():
    entries = rpt.parse_crash_log(SAMPLE_CRASH_LOG)
    assert len(entries) == 1
    assert entries[0].kind == "THREAD-EXC"
    assert entries[0].timestamp == "2026-06-22T10:01:10"
    assert "RuntimeError: kaboom" in entries[0].text


def test_parse_crash_log_native_fault_has_no_timestamp():
    text = "Fatal Python error: Segmentation fault\n\nCurrent thread ...\n"
    entries = rpt.parse_crash_log(text)
    assert len(entries) == 1
    assert entries[0].kind == "NATIVE"
    assert entries[0].timestamp is None


def test_attribute_crashes_assigns_to_session_by_time_window():
    sessions, _, _ = rpt.build_sessions(SAMPLE_EVENTS)
    crashes = rpt.parse_crash_log(SAMPLE_CRASH_LOG)
    unattributed = rpt.attribute_crashes(sessions, crashes)
    assert unattributed == []
    assert len(sessions[0].crashes) == 1
    # outcome resta CLEAN: la sessione ha chiuso con SESSION CLEAN EXIT anche
    # se un crash.log transitorio le e' stato attribuito (worker secondario).
    assert sessions[0].outcome == "CLEAN"


# === main() end-to-end =========================================================

def test_main_writes_html_report_and_tolerates_malformed_lines(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_jsonl(events_path, SAMPLE_EVENTS, extra_malformed_lines=3)
    (tmp_path / "crash.log").write_text(SAMPLE_CRASH_LOG, encoding="utf-8")

    out_path = tmp_path / "report.html"
    rc = rpt.main(["--logs", str(tmp_path), "--out", str(out_path)])

    assert rc == 0
    assert out_path.exists()
    html_text = out_path.read_text(encoding="utf-8")
    assert "Report diagnostico" in html_text
    assert "test.bin" in html_text
    assert "Righe malformate" in html_text
