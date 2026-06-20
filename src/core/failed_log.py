# Logger separato per i link abbandonati: file rotante in formato JSONL
# (una riga = un evento). Pensato per essere riletto da script di analisi
# o ri-importato in app per retry manuale.
from __future__ import annotations

import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import (
    FAILED_LINKS_LOG,
    FAILED_LINKS_LOG_BACKUPS,
    FAILED_LINKS_LOG_MAX_BYTES,
)

_LOGGER_NAME = "failed_links"
_initialized = False


def _path() -> Path:
    return Path(__file__).resolve().parents[2] / FAILED_LINKS_LOG


def failed_log_path() -> Path:
    return _path()


def setup_failed_links_logger() -> logging.Logger:
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False  # niente eco sul root logger
    fh = RotatingFileHandler(
        _path(),
        maxBytes=FAILED_LINKS_LOG_MAX_BYTES,
        backupCount=FAILED_LINKS_LOG_BACKUPS,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    _initialized = True
    return logger


def log_failed_link(file_id: int, url: str, attempts: int, last_error: str) -> None:
    logger = setup_failed_links_logger()
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "file_id": file_id,
        "url": url,
        "attempts": attempts,
        "last_error": last_error,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def read_failed_links() -> list[dict]:
    """Rilegge il log corrente (NON i backup ruotati) per popolare la GUI
    all'avvio o quando l'utente vuole riesaminare la lista."""
    p = _path()
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out
