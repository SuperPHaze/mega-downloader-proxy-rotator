# Preferenze utente persistenti (tema chiaro/scuro, controllo aggiornamenti).
# File JSON accanto a proxy_cache.json nella root del progetto.
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.config import (
    PARALLEL_CONNECTIONS_PER_FILE,
    PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PREFS_PATH = _PROJECT_ROOT / "preferences.json"

log = logging.getLogger(__name__)


def _load_prefs() -> dict:
    try:
        return json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pref(key: str, value: object) -> None:
    try:
        data = _load_prefs()
        data[key] = value
        _PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        log.warning("Impossibile salvare preferenze in %s", _PREFS_PATH)


def load_dark_theme() -> bool:
    return bool(_load_prefs().get("dark_theme", False))


def save_dark_theme(dark: bool) -> None:
    _save_pref("dark_theme", dark)


def load_check_updates_on_startup() -> bool:
    return bool(_load_prefs().get("check_updates_on_startup", True))


def save_check_updates_on_startup(enabled: bool) -> None:
    _save_pref("check_updates_on_startup", enabled)


def load_connections_per_file() -> int:
    return int(_load_prefs().get("connections_per_file", PARALLEL_CONNECTIONS_PER_FILE))


def save_connections_per_file(value: int) -> None:
    _save_pref("connections_per_file", int(value))


def load_segment_max_duration_s() -> int:
    return int(_load_prefs().get("segment_max_duration_s", PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S))


def save_segment_max_duration_s(value: int) -> None:
    _save_pref("segment_max_duration_s", int(value))


def load_speed_selection_enabled() -> bool:
    return bool(_load_prefs().get("speed_selection_enabled", False))


def save_speed_selection_enabled(enabled: bool) -> None:
    _save_pref("speed_selection_enabled", enabled)


def load_speed_selection_min_kbps() -> int:
    """Soglia preferenza in KB/s (la GUI mostra KB/s, il motore usa B/s)."""
    from src.core.config import SPEED_SELECTION_MIN_BPS
    return int(_load_prefs().get("speed_selection_min_kbps", SPEED_SELECTION_MIN_BPS // 1024))


def save_speed_selection_min_kbps(value: int) -> None:
    _save_pref("speed_selection_min_kbps", int(value))


def load_stats_panel_expanded() -> bool:
    return bool(_load_prefs().get("stats_panel_expanded", True))


def save_stats_panel_expanded(expanded: bool) -> None:
    _save_pref("stats_panel_expanded", bool(expanded))
