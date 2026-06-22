# Storico persistente dei download completati: file rotante JSONL
# (una riga = un download andato a buon fine). Stesso stile di failed_log.py.
# La GUI lo interroga (load_history) per avvisare l'utente quando reinserisce
# un link gia' scaricato in passato; l'orchestrator vi appende (record_completed)
# all'evento all_done. Dedup per handle Mega, non per stringa URL.
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import (
    DOWNLOAD_HISTORY_LOG,
    DOWNLOAD_HISTORY_LOG_BACKUPS,
    DOWNLOAD_HISTORY_LOG_MAX_BYTES,
    LOGS_DIR,
)

_LOGGER_NAME = "download_history"
_initialized = False

# Stessi pattern di mega_api._parse_url, duplicati qui perche' core/ non puo'
# importare da src.downloader (vedi rules/core.md). L'estrazione e' puramente
# testuale: nessuna chiamata di rete, il check e' istantaneo.
# Formato corrente: https://mega.nz/file/<handle>#<key> (la key puo' mancare).
_FILE_HANDLE_RE = re.compile(r"/file/([A-Za-z0-9_-]+)")
# Formato legacy: https://mega.nz/#!<handle>!<key>
_LEGACY_HANDLE_RE = re.compile(r"#!([A-Za-z0-9_-]+)!")


def extract_handle(url: str) -> str | None:
    """Estrae l'handle Mega da un link pubblico SENZA rete.

    Ritorna None se l'URL non e' in un formato file riconosciuto (es. link
    a cartelle): in quel caso il chiamante salta il check storico.
    """
    m = _FILE_HANDLE_RE.search(url)
    if m:
        return m.group(1)
    m = _LEGACY_HANDLE_RE.search(url)
    if m:
        return m.group(1)
    return None


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
