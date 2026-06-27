"""Helper di formattazione condivisi (bytes, velocita', durata)."""
from __future__ import annotations


def fmt_speed(bps: float) -> str:
    if bps < 1:
        return "—"
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


def fmt_mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_hhmmss(seconds: float) -> str:
    s = int(seconds)
    if s < 3600:
        return f"{s // 60:02d}:{s % 60:02d}"
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def fmt_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def build_header_summary(
    elapsed_s: float,
    total_bytes: int,
    throughput_eff_bps: float,
    totals_dict: dict,
    all_terminated: bool,
) -> str:
    """Riassunto compatto per l'header del widget Statistiche (puro, senza Qt)."""
    time_str = fmt_hhmmss(elapsed_s)
    if all_terminated:
        time_str += " (completata)"
    vol_str = fmt_bytes(total_bytes)
    thr_str = fmt_speed(throughput_eff_bps)
    total = totals_dict.get("total", 0)
    ok = totals_dict.get("ok", 0)
    fallen = totals_dict.get("fallen", 0)
    return f"{time_str} · {vol_str} · {thr_str} · {total} tot · {ok} ok · {fallen} fall."
