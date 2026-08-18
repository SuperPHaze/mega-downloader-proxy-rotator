# Storico persistente dei download completati: file rotante JSONL
# (una riga = un download andato a buon fine). Stesso stile di failed_log.py.
# La GUI lo interroga (load_history) per avvisare l'utente quando reinserisce
# un link gia' scaricato in passato; l'orchestrator vi appende (record_completed)
# all'evento all_done. Dedup per handle Mega, non per stringa URL.
from __future__ import annotations

import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import (
    DOWNLOAD_HISTORY_LOG,
    DOWNLOAD_HISTORY_LOG_BACKUPS,
    DOWNLOAD_HISTORY_LOG_MAX_BYTES,
    LOGS_DIR,
)
from src.core.mega_links import extract_handle as _extract_handle

_LOGGER_NAME = "download_history"
_initialized = False


def extract_handle(url: str) -> str | None:
    """Estrae l'handle Mega da un link pubblico SENZA rete.

    Ritorna None se l'URL non e' in un formato file riconosciuto (es. link a
    cartella non ancora espanso): in quel caso il chiamante salta il check
    storico. Per i job generati espandendo una cartella ritorna l'handle del
    nodo, cosi' il dedup dello storico resta per-file.

    Delega a core.mega_links, unica fonte di verita' per le forme di URL Mega
    (prima le regex erano duplicate qui: core/ non puo' importare da
    src.downloader, ma mega_links vive in core/).
    """
    return _extract_handle(url)


def _path() -> Path:
    return LOGS_DIR / DOWNLOAD_HISTORY_LOG


def download_history_path() -> Path:
    return _path()


def _setup_logger() -> logging.Logger:
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False  # niente eco sul root logger
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        _path(),
        maxBytes=DOWNLOAD_HISTORY_LOG_MAX_BYTES,
        backupCount=DOWNLOAD_HISTORY_LOG_BACKUPS,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    _initialized = True
    return logger


def record_completed(
    handle: str,
    url: str,
    file_name: str,
    file_size: int,
    path: str,
) -> None:
    logger = _setup_logger()
    payload = {
        "handle": handle,
        "url": url,
        "file_name": file_name,
        "file_size": file_size,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "path": path,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def load_history() -> dict[str, dict]:
    """Rilegge il log corrente (NON i backup ruotati) e ritorna un dict
    handle -> record. A parita' di handle l'ultimo record vince."""
    p = _path()
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                handle = rec.get("handle")
                if isinstance(handle, str) and handle:
                    out[handle] = rec
    except OSError:
        pass
    return out
