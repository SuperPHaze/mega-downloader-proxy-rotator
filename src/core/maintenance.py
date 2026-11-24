# Manutenzione: misura e azzeramento dei dati che l'applicazione lascia su
# disco (storico dei download, stato della sessione, cartella dei download,
# log e statistiche delle fonti).
#
# Modulo di CORE: non sa nulla dell'interfaccia. Espone due famiglie di
# funzioni, e la prima serve alla seconda:
#   - `survey()` / `survey_all()` MISURANO (quanti file, quante voci, quanto
#     spazio) senza toccare niente;
#   - `clear()` / `clear_items()` CANCELLANO, una voce alla volta, e ritornano
#     l'esito di ognuna.
#
# Regole di questa superficie — valgono per chi la usa oggi e per chi la
# estendera' domani. Qui si cancellano dati dell'utente, quindi:
#   - si misura PRIMA e si mostra all'utente l'elenco esatto di cio' che
#     sparira' (per questo `survey()` ritorna i percorsi, non solo i totali);
#   - nessuna voce e' attiva per default: chi disegna la finestra non
#     pre-seleziona niente;
#   - ogni azzeramento lascia una riga INFO nel log dell'applicazione;
#   - un fallimento su una voce NON ferma le altre: `clear_items()` prosegue e
#     l'esito dice quale non e' riuscita e perche'.
#
# Fuori perimetro per scelta:
#   - `preferences.json`: l'applicazione lo tiene in memoria e lo riscrive, e
#     cancellarlo a caldo produce uno stato incoerente. Resta competenza dello
#     strumento da riga di comando (`tools/pulizia-preferenze.py`).
#   - `logs/crash.log` e `logs/telemetry/`: sono diagnostica, non dati
#     dell'utente, e servono proprio quando qualcosa e' andato storto.
#   - la cache dei proxy: vive in `src/proxy/proxy_cache.py` e `core/` non puo'
#     importare da `src.proxy` (regola core.md). Chi mostra la finestra la
#     azzera chiamando `delete_proxy_cache()`, la funzione che esiste gia' —
#     non se ne riscrive una copia qui.
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from src.core import logging_setup, output_store
from src.core.config import (
    DOWNLOAD_HISTORY_LOG,
    EVENTS_LOG,
    FAILED_LINKS_LOG,
    LOGS_DIR,
    OUTPUT_DIR,
    SESSION_STATE_PATH,
    SOURCES_STATS_LOG,
    TERMINAL_LOG,
)

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Chiavi delle voci di manutenzione. Sono identificatori stabili: entrano nelle
# preferenze di nessuno, ma la GUI ci costruisce sopra le proprie chiavi i18n
# (`maintenance.item_<chiave>`), quindi rinominarne una si porta dietro i
# dizionari.
ITEM_HISTORY = "history"
ITEM_SESSION = "session"
ITEM_DOWNLOADS = "downloads"
ITEM_LOGS = "logs"
ITEM_PROXY_CACHE = "proxy_cache"

# Voci gestite da QUESTO modulo, nell'ordine in cui vanno mostrate (dalla meno
# alla piu' distruttiva). `ITEM_PROXY_CACHE` non c'e': vedi il commento in
# testa al file.
ITEMS = (ITEM_HISTORY, ITEM_SESSION, ITEM_DOWNLOADS, ITEM_LOGS)

# Voci che NON si possono azzerare mentre una sessione di download e' in corso.
# Non e' una raccomandazione: cancellare un `.part` sotto il worker che ci sta
# scrivendo produce errori a catena e penalizza i proxy innocenti, e troncare i
# log mentre scorrono butta via proprio le righe che servirebbero a capire cosa
# e' successo. Chi disegna la finestra le disattiva e dice perche'.
SESSION_LOCKED_ITEMS = frozenset({ITEM_DOWNLOADS, ITEM_LOGS})


@dataclass(frozen=True)
class ItemSurvey:
    """Misura di una voce, scattata al momento dell'apertura della finestra.

    `paths` elenca i singoli file. Per i download `receipts` conserva anche
    l’impronta verificata nell’anteprima, da ricontrollare alla conferma.
    """

    key: str
    paths: tuple[Path, ...] = ()
    total_bytes: int = 0
    count: int = 0
    extra_count: int = 0
    root: Path | None = None
    receipts: tuple[output_store.Receipt, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Non c'e' niente da cancellare per questa voce."""
        return not self.paths


@dataclass(frozen=True)
class ItemResult:
    """Esito dell'azzeramento di una voce.

    `error` e' il testo di sistema dell'eccezione (`str(exc)`): viene da una
    libreria o dal sistema operativo, quindi si mostra com'e' in entrambe le
    lingue — la cornice tradotta la mette chi disegna (vedi rules/core.md).
    """

    key: str
    ok: bool
    freed_bytes: int = 0
    removed: int = 0
    error: str | None = None
    failures: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Percorsi coinvolti da ogni voce
# ---------------------------------------------------------------------------

def _rotated_siblings(path: Path) -> list[Path]:
    """Archivi ruotati di un log (`app.log.1`, `app.log.2`, ...).

    `RotatingFileHandler` numera i backup con un suffisso numerico: il filtro
    sulle cifre e' quello che evita di raccogliere per sbaglio un `.tmp` o un
    omonimo di un altro strumento.
    """
    parent = path.parent
    if not parent.is_dir():
        return []
    out = []
    for candidate in parent.glob(path.name + ".*"):
        suffix = candidate.name[len(path.name) + 1:]
        if suffix.isdigit():
            out.append(candidate)
    return sorted(out, key=lambda p: p.name)


def _with_rotated(path: Path) -> list[Path]:
    return [path, *_rotated_siblings(path)]


def history_paths(logs_dir: Path | None = None) -> list[Path]:
    """Storico dei download: il log corrente piu' i suoi archivi ruotati."""
    base = logs_dir or LOGS_DIR
    return _with_rotated(base / DOWNLOAD_HISTORY_LOG)


def session_paths(project_root: Path | None = None) -> list[Path]:
    """Stato della sessione da ripristinare all'avvio."""
    base = project_root or _PROJECT_ROOT
    return [base / SESSION_STATE_PATH]


def log_paths(logs_dir: Path | None = None) -> list[Path]:
    """Log applicativi e statistiche delle fonti (archivi ruotati inclusi).

    NON contiene `crash.log` ne' `logs/telemetry/`: vedi il commento in testa
    al file. Non contiene nemmeno `download_history.log`, che e' una voce a
    se' (e' un dato dell'utente, non un log diagnostico).
    """
    base = logs_dir or LOGS_DIR
    out: list[Path] = []
    out += _with_rotated(base / "app.log")
    out += _with_rotated(base / EVENTS_LOG)
    out += [base / TERMINAL_LOG]
    out += _with_rotated(base / SOURCES_STATS_LOG)
    out += _with_rotated(base / FAILED_LINKS_LOG)
    return out


def downloads_root(root: Path | None = None) -> Path:
    """Radice della cartella dei download (quella scelta dall'utente, o il
    default di `config.OUTPUT_DIR`)."""
    return root or OUTPUT_DIR


# ---------------------------------------------------------------------------
# Misura
# ---------------------------------------------------------------------------

def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _count_lines(path: Path) -> int:
    """Righe non vuote di un file JSONL. Mai solleva: un file illeggibile
    vale zero, non un'eccezione dentro la finestra che deve ancora aprirsi."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def _count_session_links(path: Path) -> int:
    """Link in sospeso salvati nello stato di sessione. Mai solleva."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    urls = data.get("urls") if isinstance(data, dict) else None
    return len(urls) if isinstance(urls, list) else 0


def survey_paths(key: str, paths: Iterable[Path], *, count: int = 0) -> ItemSurvey:
    """Misura generica di un elenco esplicito di percorsi.

    Serve anche a chi gestisce una voce che non vive qui (la cache dei proxy),
    cosi' la finestra puo' trattare tutte le voci allo stesso modo.
    """
    present = tuple(p for p in paths if p.exists())
    return ItemSurvey(
        key=key,
        paths=present,
        total_bytes=sum(_size_of(p) for p in present),
        count=count or len(present),
    )


def survey(
    key: str,
    *,
    logs_dir: Path | None = None,
    project_root: Path | None = None,
    output_root: Path | None = None,
) -> ItemSurvey:
    """Misura una voce SENZA toccare niente.

    Significato dei due conteggi, voce per voce:
      - `history`: `count` = voci dello storico (righe del log corrente);
      - `session`: `count` = link rimasti in sospeso;
      - `downloads`: `count` = file, `extra_count` = frammenti `.part`;
      - `logs`: `count` = file presenti.
    """
    if key == ITEM_HISTORY:
        paths = [p for p in history_paths(logs_dir) if p.exists()]
        current = history_paths(logs_dir)[0]
        return ItemSurvey(
            key=key,
            paths=tuple(paths),
            total_bytes=sum(_size_of(p) for p in paths),
            count=_count_lines(current) if current.exists() else 0,
        )
    if key == ITEM_SESSION:
        paths = [p for p in session_paths(project_root) if p.exists()]
        return ItemSurvey(
            key=key,
            paths=tuple(paths),
            total_bytes=sum(_size_of(p) for p in paths),
            count=_count_session_links(paths[0]) if paths else 0,
        )
    if key == ITEM_DOWNLOADS:
        root = downloads_root(output_root).resolve()
        try:
            entries = output_store.receipts(root)
        except (OSError, sqlite3.Error) as exc:
            log.warning("Registro dei download non leggibile: %s", exc)
            entries = ()
        return ItemSurvey(
            key=key, root=root, paths=tuple(item.path for item in entries),
            total_bytes=sum(item.size for item in entries), count=len(entries),
            extra_count=sum(item.partial and item.path.suffix == ".part" for item in entries),
            receipts=entries,
        )
    if key == ITEM_LOGS:
        paths = [p for p in log_paths(logs_dir) if p.exists()]
        return ItemSurvey(
            key=key,
            paths=tuple(paths),
            total_bytes=sum(_size_of(p) for p in paths),
            count=len(paths),
        )
    raise ValueError(f"voce di manutenzione sconosciuta: {key}")


def survey_all(
    keys: Sequence[str] = ITEMS,
    *,
    logs_dir: Path | None = None,
    project_root: Path | None = None,
    output_root: Path | None = None,
) -> dict[str, ItemSurvey]:
    return {
        key: survey(
            key,
            logs_dir=logs_dir,
            project_root=project_root,
            output_root=output_root,
        )
        for key in keys
    }


# ---------------------------------------------------------------------------
# Azzeramento
# ---------------------------------------------------------------------------

def _clear_log_files(key: str, paths: Sequence[Path]) -> ItemResult:
    """Azzera dei file di LOG, che possono essere tenuti aperti dai canali di
    registrazione: il troncamento lo fa `logging_setup`, che e' l'unico a
    sapere quali flussi vanno chiusi e riaperti (su Windows `unlink` su un
    file aperto fallisce con errore di permessi)."""
    freed = 0
    removed = 0
    failures: list[str] = []
    for path in paths:
        try:
            freed += logging_setup.reset_log_file(path)
            removed += 1
        except OSError as exc:
            failures.append(f"{path.name}: {exc}")
            log.warning("[manutenzione] %s non azzerabile: %s", path, exc)
    return ItemResult(
        key=key,
        ok=not failures,
        freed_bytes=freed,
        removed=removed,
        error="; ".join(failures) or None,
        failures=tuple(failures),
    )


def _clear_downloads(root: Path, selected: tuple[output_store.Receipt, ...] | None) -> ItemResult:
    try:
        entries = output_store.receipts(root) if selected is None else selected
        removed, freed, failures = output_store.remove(root, entries)
    except (OSError, sqlite3.Error) as exc:
        removed, freed, failures = 0, 0, [str(exc)]
    return ItemResult(key=ITEM_DOWNLOADS, ok=not failures, freed_bytes=freed,
                      removed=removed, error="; ".join(failures) or None, failures=tuple(failures))


def _clear_plain_files(key: str, paths: Sequence[Path]) -> ItemResult:
    """Cancella file normali (non tenuti aperti da nessun canale)."""
    freed = 0
    removed = 0
    failures: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        size = _size_of(path)
        try:
            path.unlink()
            freed += size
            removed += 1
        except OSError as exc:
            failures.append(f"{path.name}: {exc}")
            log.warning("[manutenzione] %s non cancellabile: %s", path, exc)
    return ItemResult(
        key=key,
        ok=not failures,
        freed_bytes=freed,
        removed=removed,
        error="; ".join(failures) or None,
        failures=tuple(failures),
    )


def clear(
    key: str,
    *,
    logs_dir: Path | None = None,
    project_root: Path | None = None,
    output_root: Path | None = None,
    selected_downloads: tuple[output_store.Receipt, ...] | None = None,
) -> ItemResult:
    """Azzera UNA voce e ritorna il suo esito. Non solleva per i fallimenti di
    I/O: li mette nel risultato, cosi' le altre voci proseguono."""
    if key == ITEM_HISTORY:
        result = _clear_log_files(key, [p for p in history_paths(logs_dir) if p.exists()])
    elif key == ITEM_SESSION:
        result = _clear_plain_files(key, session_paths(project_root))
    elif key == ITEM_DOWNLOADS:
        result = _clear_downloads(downloads_root(output_root), selected_downloads)
    elif key == ITEM_LOGS:
        result = _clear_log_files(key, [p for p in log_paths(logs_dir) if p.exists()])
    else:
        raise ValueError(f"voce di manutenzione sconosciuta: {key}")
    # La riga nel log dopo l'operazione: e' il "lascia traccia" che il vecchio
    # strumento da riga di comando non faceva.
    if result.ok:
        log.info(
            "[manutenzione] voce '%s' azzerata: %d elementi, %d byte liberati",
            key, result.removed, result.freed_bytes,
            extra={"event_type": "maintenance_cleared", "item": key,
                   "freed_bytes": result.freed_bytes, "removed": result.removed},
        )
    else:
        log.warning(
            "[manutenzione] voce '%s' azzerata solo in parte: %d byte liberati (%s)",
            key, result.freed_bytes, result.error,
            extra={"event_type": "maintenance_failed", "item": key,
                   "freed_bytes": result.freed_bytes, "error": result.error},
        )
    return result


def clear_items(
    keys: Sequence[str],
    *,
    logs_dir: Path | None = None,
    project_root: Path | None = None,
    output_root: Path | None = None,
    selected_downloads: tuple[output_store.Receipt, ...] | None = None,
) -> list[ItemResult]:
    """Azzera piu' voci nell'ordine di `ITEMS`. Se una fallisce, le altre
    proseguono comunque: l'esito dice quale non e' riuscita e perche'."""
    ordered = [k for k in ITEMS if k in set(keys)]
    return [
        clear(
            key,
            logs_dir=logs_dir,
            project_root=project_root,
            output_root=output_root, selected_downloads=selected_downloads,
        )
        for key in ordered
    ]
