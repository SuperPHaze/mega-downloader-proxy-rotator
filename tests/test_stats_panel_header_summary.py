# Test puri per build_header_summary (nessuna dipendenza Qt).
from src.gui.format_helpers import build_header_summary


def test_elapsed_zero_throughput_dash():
    result = build_header_summary(0, 0, 0.0, {"total": 0, "ok": 0, "fallen": 0}, False)
    assert "—" in result


def test_typical_values_segments():
    # 222s = 03:42 ; 4.9 GB ; 22 MB/s ; 5 tot / 3 ok / 1 fall.
    result = build_header_summary(
        222, 4_900_000_000, 22_000_000.0,
        {"total": 5, "ok": 3, "fallen": 1}, False,
    )
    assert "03:42" in result
    assert "4.6 GB" in result
    assert "21.0 MB/s" in result
    assert "5 tot" in result
    assert "3 ok" in result
    assert "1 fall." in result
    assert " · " in result


def test_all_terminated_suffix_present():
    result = build_header_summary(60, 0, 0.0, {"total": 1, "ok": 1, "fallen": 0}, True)
    assert "(completata)" in result


def test_all_terminated_false_no_suffix():
    result = build_header_summary(60, 0, 0.0, {"total": 1, "ok": 1, "fallen": 0}, False)
    assert "(completata)" not in result


def test_volume_and_speed_formatted():
    # 50 MB volume, 5 MB/s throughput
    result = build_header_summary(
        10, 52_428_800, 5_242_880.0,
        {"total": 2, "ok": 2, "fallen": 0}, False,
    )
    assert "50.0 MB" in result
    assert "5.0 MB/s" in result
