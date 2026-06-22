# Test puri per la suite di diagnostica crash: nessuna rete, nessuna GUI.
import logging
import sys

import pytest

from src.core import diagnostics


def test_format_heartbeat_with_known_memory():
    line = diagnostics.format_heartbeat(123.456, threads=7, download_attivi=2, pool_vivi=80)
    assert line == "HEARTBEAT mem_rss=123.5 threads=7 download_attivi=2 pool_vivi=80"


def test_format_heartbeat_memory_unavailable():
    line = diagnostics.format_heartbeat(None, threads=3, download_attivi=0, pool_vivi=0)
    assert "mem_rss=n/d" in line
    assert "threads=3" in line
    assert "download_attivi=0" in line
    assert "pool_vivi=0" in line


def test_get_process_memory_mb_never_raises():
    # Su Windows deve risolvere via ctypes/psapi; su altre piattaforme senza
    # psutil deve ritornare None senza eccezioni.
    result = diagnostics.get_process_memory_mb()
    assert result is None or isinstance(result, float)


@pytest.mark.skipif(sys.platform != "win32", reason="fallback ctypes/psapi solo su Windows")
def test_get_process_memory_mb_resolves_a_real_value_on_windows():
    # Regressione: senza restype/argtypes espliciti su GetCurrentProcess /
    # GetProcessMemoryInfo, ctypes troncava lo pseudo-handle a 64 bit e la
    # chiamata falliva con ERROR_INVALID_HANDLE, facendo tornare sempre None
    # (l'heartbeat mostrava sempre "mem_rss=n/d"). Un processo Python in
    # esecuzione occupa sicuramente piu' di 1 MB di working set.
    result = diagnostics.get_process_memory_mb()
    assert result is not None
    assert result > 1.0


def test_log_session_start_writes_pid_and_version(caplog):
    with caplog.at_level(logging.INFO, logger="diagnostics"):
        diagnostics.log_session_start("1.8.3")
    assert any("SESSION START v1.8.3" in r.message for r in caplog.records)


def test_log_session_clean_exit_writes_marker(caplog):
    with caplog.at_level(logging.INFO, logger="diagnostics"):
        diagnostics.log_session_clean_exit()
    assert any("SESSION CLEAN EXIT" in r.message for r in caplog.records)


def test_log_heartbeat_writes_heartbeat_line(caplog):
    with caplog.at_level(logging.INFO, logger="diagnostics"):
        diagnostics.log_heartbeat(download_attivi=1, pool_vivi=42)
    assert any(r.message.startswith("HEARTBEAT ") for r in caplog.records)
