# Persistenza leggera dei link non completati della sessione corrente, per
# riproporli all'avvio ("Riprendere la sessione precedente?"). I .part su disco
# fanno il resume a livello di byte: qui salviamo solo l'elenco dei link.
#
# Vincoli (come proxy_cache): solo stdlib, load/save/clear non sollevano MAI,
# scrittura atomica (tmp + os.replace).
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src.core.config import SESSION_STATE_PATH

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = 1


def _path() -> Path:
    return _PROJECT_ROOT / SESSION_STATE_PATH


def save(urls: list[str]) -> bool:
    """Scrive l'elenco dei link non completati. Mai solleva: ritorna False su errore."""
    target = _path()
    payload = {
        "schema": _SCHEMA,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "urls": list(urls),
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError as exc:
        log.warning("[session_store] save fallita: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def load() -> list[str]:
    """Elenco dei link salvati. Mai solleva: ritorna [] su qualunque errore o
    schema sconosciuto."""
    target = _path()
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("[session_store] load fallita, ignoro: %s", exc)
        return []
    if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
        return []
    urls = data.get("urls")
    if not isinstance(urls, list):
        return []
    return [u for u in urls if isinstance(u, str) and u]


def clear() -> None:
    """Rimuove il file di stato. Mai solleva."""
    try:
        _path().unlink(missing_ok=True)
    except OSError as exc:
        log.warning("[session_store] clear fallita: %s", exc)
