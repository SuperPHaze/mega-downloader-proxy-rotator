# Controllo dello spazio su disco prima di iniziare un download.
# Solo stdlib: il core non dipende da proxy/downloader/gui.
from __future__ import annotations

import shutil
from pathlib import Path

from src.core.errors import UserFacingOSError


class InsufficientDiskSpaceError(UserFacingOSError):
    """Spazio su disco insufficiente per il file richiesto.

    Why: è un errore d'AMBIENTE (permanente), non transitorio. Ritentare con un
    altro proxy non libera spazio: il worker deve abbandonare subito il file con
    un messaggio chiaro, invece di bruciare tutti i tentativi con un OSError
    grezzo a metà pre-allocazione.
    """


def free_space_bytes(path: str | Path) -> int:
    """Byte liberi sul volume che contiene `path`.

    `path` può non esistere ancora (la cartella del download viene creata dopo):
    si risale al primo antenato esistente per interrogare il volume corretto.
    """
    p = Path(path)
    while not p.exists():
        parent = p.parent
        if parent == p:
            break
        p = parent
    return shutil.disk_usage(p).free


def ensure_free_space(
    path: str | Path, needed_bytes: int, margin_bytes: int = 0
) -> None:
    """Solleva InsufficientDiskSpaceError se sul volume di `path` non c'è spazio
    per `needed_bytes` più `margin_bytes` di margine di sicurezza."""
    if needed_bytes <= 0:
        return
    required = needed_bytes + max(0, margin_bytes)
    free = free_space_bytes(path)
    if free < required:
        raise InsufficientDiskSpaceError(
            "disk_full",
            path=path,
            required=required,
            needed_bytes=needed_bytes,
            margin_bytes=margin_bytes,
            free=free,
        )
