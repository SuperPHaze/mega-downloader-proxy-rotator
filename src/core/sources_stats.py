# Logger isolato per metriche per-fonte (scraping + survival post-validazione).
# File rotante in formato JSONL accanto a app.log e failed_links.log.
# Pensato per essere riletto post-sessione per identificare fonti morte da disattivare.
from __future__ import annotations

import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import (
    SOURCES_STATS_LOG,
    SOURCES_STATS_LOG_BACKUPS,
    SOURCES_STATS_LOG_MAX_BYTES,
)

_LOGGER_NAME = "proxy_sources_stats"
_initialized = False


def _path() -> Path:
    return Path(__file__).resolve().parents[2] / SOURCES_STATS_LOG


def sources_stats_path() -> Path:
    return _path()


def _setup_logger() -> logging.Logger:
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fh = RotatingFileHandler(
        _path(),
        maxBytes=SOURCES_STATS_LOG_MAX_BYTES,
        backupCount=SOURCES_STATS_LOG_BACKUPS,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    _initialized = True
    return logger


def log_source_event(
    source_name: str,
    outcome: str,
    raw_count: int,
    dedup_added: int,
    error: str | None = None,
) -> None:
    """Registra un evento di scraping per una singola fonte."""
    logger = _setup_logger()
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "scrape",
        "source": source_name,
        "outcome": outcome,
        "raw_count": raw_count,
        "dedup_added": dedup_added,
        "error": error,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def log_validation_result(
    source_name: str,
    survived_stage1: int,
    survived_stage2: int,
    total_from_source: int,
) -> None:
    """Registra il survival rate post-validazione per una fonte."""
    logger = _setup_logger()
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": "validation",
        "source": source_name,
        "survived_stage1": survived_stage1,
        "survived_stage2": survived_stage2,
        "total_from_source": total_from_source,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))
