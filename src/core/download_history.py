# Storico persistente dei download completati: file rotante JSONL
# (una riga = un download andato a buon fine). Stesso stile di failed_log.py.
# La GUI lo interroga (load_history) per avvisare l'utente quando reinserisce
# un link gia' scaricato in passato; l'orchestrator vi appende (record_completed)
# all'evento all_done. Dedup per handle Mega, non per stringa URL.
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
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
from src.core.maintenance import history_paths

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
    disk_signature: tuple[int, int, int, int] | None = None,
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
    if disk_signature is not None:
        payload["disk_signature"] = disk_signature
    logger.info(json.dumps(payload, ensure_ascii=False))


def _records(path: Path) -> Iterator[dict]:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("handle"), str) and rec["handle"]:
                    yield rec
    except FileNotFoundError:
        pass
    except OSError as exc:
        logging.getLogger(__name__).warning("Lettura storico %s: %s", path, exc)


def load_history() -> dict[str, dict]:
    """Indice del registro corrente per l'avviso sui duplicati. Vince l'ultima voce."""
    return {rec["handle"]: rec for rec in _records(_path())}


def completion_records() -> Iterator[dict]:
    """Completamenti dal più recente, inclusi i registri ruotati."""
    for path in history_paths(LOGS_DIR):
        yield from reversed(list(_records(path)))


@dataclass(frozen=True)
class HistoryEntry:
    name: str
    completed_at: str
    size: int
    path: str


def history_entries() -> list[HistoryEntry]:
    """Tutti i completamenti conservati, dal più recente, inclusi i download ripetuti."""
    entries = []
    for rec in completion_records():
        name, date = rec.get("file_name"), rec.get("completed_at")
        size, destination = rec.get("file_size"), rec.get("path")
        entries.append(HistoryEntry(
            name if isinstance(name, str) and name else rec["handle"],
            date if isinstance(date, str) else "",
            size if isinstance(size, int) else -1,
            destination if isinstance(destination, str) else "",
        ))
    return entries
