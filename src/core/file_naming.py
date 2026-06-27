from __future__ import annotations

import re
from pathlib import Path

from src.core.config import OUTPUT_DIR

# Caratteri non validi per nomi cartella Windows.
_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def sanitize_folder_name(name: str, max_len: int = 120) -> str:
    """Restituisce un nome di cartella sicuro per Windows.

    Sostituisce ogni carattere non valido con uno spazio, collassa spazi multipli,
    rimuove spazi e punti in coda. Ritorna 'download' se la stringa risulta vuota.
    """
    s = _INVALID_WIN.sub(" ", name)
    s = re.sub(r" +", " ", s)
    s = s.strip().rstrip(".")
    if not s:
        return "download"
    return s[:max_len]


def final_output_dir(file_name: str, file_id: int) -> Path:
    """Cartella base definitiva per un job, calcolata dal nome file risolto."""
    safe = sanitize_folder_name(file_name)
    return OUTPUT_DIR / f"{safe}_{file_id}"
