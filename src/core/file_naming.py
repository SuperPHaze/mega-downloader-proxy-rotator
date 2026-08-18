from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from pathlib import Path

from src.core.config import OUTPUT_DIR

log = logging.getLogger(__name__)

# Soglia di allarme sulla lunghezza totale del path (limite Windows: 260).
_LONG_PATH_WARN = 250

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


# Lunghezza massima di un nome file prodotto da sanitize_file_name. Esposta
# come costante perche' chi costruisce nomi (es. i suffissi di de-collisione
# in mega_folder) deve stare dentro lo stesso budget, altrimenti il suffisso
# viene ritagliato proprio da questa funzione e la collisione torna.
MAX_FILE_NAME_LEN = 200


def sanitize_file_name(
    name: str, max_len: int = MAX_FILE_NAME_LEN, fallback: str = "download",
) -> str:
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


def folder_job_output_dir(
    rel_path: "Sequence[str]", output_root: Path | None = None
) -> Path:
    """Cartella di destinazione di un file appartenente a una cartella Mega.

    Layout ad ALBERO: tutti i file di una cartella finiscono sotto un'unica
    cartella top-level col nome della cartella Mega, preservando le
    sottocartelle. Nessun suffisso `_<file_id>` e nessun `ciclo_N`: il path e'
    quello che l'utente si aspetta di ritrovare su disco.

    `rel_path` include il nome file come ULTIMO segmento, che non entra nel
    path della cartella. I segmenti vengono ri-sanificati qui: e' il confine
    che tocca il filesystem, e un job puo' arrivare da un file di sessione
    scritto da una versione precedente.
    """
    if not rel_path:
        raise ValueError("rel_path vuoto")
    base = output_root or OUTPUT_DIR
    for seg in rel_path[:-1]:
        safe = sanitize_folder_name(seg)
        if safe in (".", ".."):
            safe = "download"
        base = base / safe
    # Windows rifiuta i path oltre 260 caratteri se il supporto ai path lunghi
    # non e' attivo: con una cartella di download profonda e un albero Mega
    # annidato ci si puo' arrivare. Meglio una riga di log che spieghi un
    # OSError altrimenti misterioso a meta' download.
    full_len = len(str(base / sanitize_file_name(rel_path[-1])))
    if full_len >= _LONG_PATH_WARN:
        log.warning(
            "[file_naming] path molto lungo (%d caratteri): su Windows senza "
            "supporto ai path lunghi la scrittura puo' fallire -> %s",
            full_len, base,
        )
    return base
