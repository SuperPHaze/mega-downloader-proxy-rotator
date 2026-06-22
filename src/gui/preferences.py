# Preferenze utente persistenti (tema chiaro/scuro, controllo aggiornamenti).
# File JSON accanto a proxy_cache.json nella root del progetto.
from __future__ import annotations

import json
import logging
from pathlib import Path

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
