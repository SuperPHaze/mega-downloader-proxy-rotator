from __future__ import annotations

import os
import re
from pathlib import Path

from src.core.config import OUTPUT_DIR

# Caratteri non validi per nomi file/cartella Windows.
_INVALID_WIN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

# Nomi di dispositivo riservati da Windows: non possono essere usati come nome
# file NEMMENO con estensione (es. "CON.txt" è ugualmente vietato).
_RESERVED_WIN = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


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


def sanitize_file_name(name: str, max_len: int = 200, fallback: str = "download") -> str:
    """Restituisce un nome di FILE sicuro per Windows, preservando l'estensione.

    - Blocca il path traversal (`Path(name).name`: via separatori e `..`).
    - Sostituisce i caratteri riservati (`< > : " / \\ | ? *` e i controlli).
    - Evita i nomi di dispositivo riservati (`CON`, `NUL`, `COM1`, …) anteponendo `_`.
    - Rimuove spazi/punti in coda (Windows li trima, creando nomi ambigui).
    - Tronca a `max_len` mantenendo l'estensione.
    Ritorna `fallback` se non resta nulla di valido (es. nome tutto simboli).
    """
    base = Path(name).name
    base = _INVALID_WIN.sub(" ", base)
    base = re.sub(r" +", " ", base).strip().rstrip(" .")
    if not base:
        return fallback
    stem, ext = os.path.splitext(base)
    # Spazi in coda allo stem (es. da un "?" prima del punto) fanno un brutto
    # "nome .ext": rimuovili.
    stem = stem.rstrip()
    if stem.upper() in _RESERVED_WIN:
        stem = "_" + stem
    base = stem + ext
    if len(base) > max_len:
        keep = max_len - len(ext)
        base = (stem[:keep] + ext) if keep > 0 else base[:max_len]
    return base or fallback


def final_output_dir(
    file_name: str, file_id: int, output_root: Path | None = None
) -> Path:
    """Cartella base definitiva per un job, calcolata dal nome file risolto.
    `output_root` = cartella di download scelta dall'utente (None = default)."""
    safe = sanitize_folder_name(file_name)
    return (output_root or OUTPUT_DIR) / f"{safe}_{file_id}"
