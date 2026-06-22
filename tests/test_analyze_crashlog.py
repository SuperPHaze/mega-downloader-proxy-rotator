# Test puri per il parser di tools/analyze_crashlog.py: nessuna rete, nessun
# file scritto su disco (le funzioni di parsing operano su stringhe/liste).
from tools import analyze_crashlog as ac

SAMPLE_APP_LOG = """\
10:00:00 [INFO] MainThread main: Avvio applicazione. Log: app.log
10:00:00 [INFO] diagnostics diagnostics: SESSION START v1.8.3 pid=1234
10:00:05 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=120.0 threads=8 download_attivi=1 pool_vivi=60
10:00:10 [WARNING] ParallelChunk_0 src.downloader.parallel_client: [parallel] chunk fallito: esauriti 8 tentativi (boom)
10:01:05 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=150.0 threads=9 download_attivi=1 pool_vivi=55
10:02:05 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=200.0 threads=9 download_attivi=1 pool_vivi=50
10:02:30 [ERROR] DownloadWorker src.downloader.worker: [file 3] eccezione non gestita nel worker, il thread termina
Traceback (most recent call last):
  File "worker.py", line 100, in run
    raise RuntimeError("kaboom")
RuntimeError: kaboom
10:02:31 [INFO] MainThread diagnostics: SESSION CLEAN EXIT
10:05:00 [INFO] diagnostics diagnostics: SESSION START v1.8.3 pid=5678
10:05:10 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=80.0 threads=6 download_attivi=0 pool_vivi=70
10:06:10 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=95.0 threads=6 download_attivi=0 pool_vivi=68
"""

SAMPLE_CRASH_LOG = """\
2026-06-21T10:02:30 [THREAD-EXC] DownloadWorker
Traceback (most recent call last):
  File "worker.py", line 100, in run
    raise RuntimeError("kaboom")
RuntimeError: kaboom

"""


def _parse(app_log_text: str):
    return ac.parse_app_log(app_log_text.splitlines())


def test_parses_two_sessions():
    sessions, orphans = _parse(SAMPLE_APP_LOG)
    assert len(sessions) == 2
    assert orphans == []


def test_first_session_is_clean_with_heartbeats_and_exception():
    sessions, _ = _parse(SAMPLE_APP_LOG)
    s1 = sessions[0]
    assert s1.start_time == "10:00:00"
    assert s1.clean_exit is True
    assert s1.outcome == "CLEAN"
    assert len(s1.heartbeats) == 3
    assert [h.mem_rss_mb for h in s1.heartbeats] == [120.0, 150.0, 200.0]
    assert len(s1.exceptions) == 1
    exc = s1.exceptions[0]
    assert exc.file_id == 3
    assert "RuntimeError: kaboom" in exc.traceback


def test_second_session_has_no_clean_exit_and_is_anomalous():
    sessions, _ = _parse(SAMPLE_APP_LOG)
    s2 = sessions[1]
    assert s2.start_time == "10:05:00"
    assert s2.clean_exit is False
    assert s2.outcome == "ANOMALA"
    assert len(s2.heartbeats) == 2


def test_heartbeat_with_mem_unavailable_is_none():
    log = (
        "10:00:00 [INFO] diagnostics diagnostics: SESSION START v1.8.3 pid=1\n"
        "10:00:01 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=n/d threads=4 "
        "download_attivi=0 pool_vivi=10\n"
    )
    sessions, _ = _parse(log)
    assert sessions[0].heartbeats[0].mem_rss_mb is None


def test_crash_log_parses_thread_exc_entry():
    entries = ac.parse_crash_log(SAMPLE_CRASH_LOG)
    assert len(entries) == 1
    assert entries[0].kind == "THREAD-EXC"
    assert entries[0].timestamp == "2026-06-21T10:02:30"
    assert "RuntimeError: kaboom" in entries[0].text


def test_native_fault_entry_has_no_timestamp():
    text = (
        "Fatal Python error: Segmentation fault\n\n"
        "Current thread 0x00001234 (most recent call first):\n"
        "  File \"x.py\", line 1 in foo\n"
    )
    entries = ac.parse_crash_log(text)
    assert len(entries) == 1
    assert entries[0].kind == "NATIVE"
    assert entries[0].timestamp is None
    assert "Segmentation fault" in entries[0].text


def test_attribute_crashes_assigns_thread_exc_to_session_by_time_window():
    sessions, _ = _parse(SAMPLE_APP_LOG)
    crashes = ac.parse_crash_log(SAMPLE_CRASH_LOG)
    unattributed = ac.attribute_crashes(sessions, crashes)
    assert unattributed == []
    # 10:02:30 cade nella finestra [10:00:00, 10:02:31] della prima sessione.
    assert len(sessions[0].crashes) == 1
    assert len(sessions[1].crashes) == 0
    # Una sessione con CLEAN EXIT resta CLEAN anche se le e' stato attribuito
    # un crash.log entry transitorio (es. un worker secondario e' morto ma
    # l'app e' uscita correttamente): la colonna esito ha priorita' sul clean exit.
    assert sessions[0].outcome == "CLEAN"


def test_build_verdict_no_anomalies():
    log = (
        "10:00:00 [INFO] diagnostics diagnostics: SESSION START v1.8.3 pid=1\n"
        "10:00:01 [INFO] MainThread diagnostics: SESSION CLEAN EXIT\n"
    )
    sessions, _ = _parse(log)
    verdict = ac.build_verdict(sessions)
    assert len(verdict) == 1
    assert "nessuna chiusura anomala" in verdict[0].lower()


def test_build_verdict_flags_native_crash():
    sessions, _ = _parse(SAMPLE_APP_LOG)
    sessions[1].crashes.append(ac.CrashEntry(kind="NATIVE", timestamp=None, text="boom"))
    verdict = ac.build_verdict(sessions)
    assert any("nativo" in v.lower() for v in verdict)


def test_build_verdict_flags_growing_memory_as_oom_suspect():
    sessions, _ = _parse(
        "10:00:00 [INFO] diagnostics diagnostics: SESSION START v1.8.3 pid=1\n"
        "10:00:01 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=100.0 threads=4 download_attivi=0 pool_vivi=10\n"
        "10:00:02 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=150.0 threads=4 download_attivi=0 pool_vivi=10\n"
        "10:00:03 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=220.0 threads=4 download_attivi=0 pool_vivi=10\n"
        "10:00:04 [INFO] MainThread diagnostics: HEARTBEAT mem_rss=300.0 threads=4 download_attivi=0 pool_vivi=10\n"
    )
    verdict = ac.build_verdict(sessions)
    assert any("oom" in v.lower() or "leak" in v.lower() for v in verdict)
