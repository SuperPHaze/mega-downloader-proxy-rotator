"""Persistent folder assignments and receipts for files written by this installation."""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import stat
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.core.mega_links import parse_folder_job_url

log = logging.getLogger(__name__)
_INDEX = Path(__file__).resolve().parents[2] / "output-index.sqlite3"


@contextmanager
def transaction():
    with closing(sqlite3.connect(_INDEX, timeout=5)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS destinations (
            root TEXT, share TEXT, node TEXT, path TEXT, PRIMARY KEY (root, share, node))""")
        db.execute("""CREATE TABLE IF NOT EXISTS outputs (
            root TEXT, path TEXT, owner TEXT, partial INTEGER, signature TEXT,
            PRIMARY KEY (root, path))""")
        yield db


def job_owner(url: str, file_id: int) -> str:
    job = parse_folder_job_url(url)
    if job:
        return f"folder/{job.folder_id}/{job.node_handle}"
    return f"file/{file_id}/" + hashlib.sha256(url.encode()).hexdigest()


def _signature(root: Path, path: Path) -> str | None:
    """Reject replaced files, directories, and paths reached through a link."""
    try:
        if not path.is_relative_to(root) or path.resolve(strict=True) != path:
            return None
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            return f"{info.st_dev}/{info.st_ino}/{info.st_size}/{info.st_mtime_ns}"
    except (OSError, RuntimeError):
        pass
    return None


def unchanged(db: sqlite3.Connection, root: Path, path: Path) -> bool:
    signature = _signature(root, path)
    if signature is None:
        return False
    return db.execute("SELECT 1 FROM outputs WHERE root=? AND path=? AND signature=?",
                      (str(root), path.relative_to(root).as_posix(), signature)).fetchone() is not None


@dataclass(frozen=True)
class Receipt:
    path: Path
    signature: str
    size: int
    partial: bool


def record(root: Path, owner: str, path: Path, partial: bool) -> Receipt | None:
    root = root.resolve()
    path = path.absolute()
    signature = _signature(root, path)
    if signature is None:
        return
    try:
        with transaction() as db:
            db.execute("INSERT OR REPLACE INTO outputs VALUES (?,?,?,?,?)",
                       (str(root), path.relative_to(root).as_posix(), owner, partial, signature))
        return Receipt(path, signature, int(signature.split("/")[2]), partial)
    except (sqlite3.Error, OSError) as exc:
        # A receipt is optional for downloading. An unrecorded file is always kept.
        log.warning("Impossibile registrare il file prodotto %s: %s", path, exc)


def receipts(root: Path, owner: str | None = None) -> tuple[Receipt, ...]:
    if not _INDEX.is_file():
        return ()
    root = root.resolve()
    found = []
    with transaction() as db:
        rows = db.execute("""SELECT path, signature, partial FROM outputs WHERE root=?
            AND (? IS NULL OR owner=?) ORDER BY path""",
                          (str(root), owner, owner))
        for relative, signature, partial in rows:
            path = root / relative
            if _signature(root, path) == signature:
                found.append(Receipt(path, signature, int(signature.split("/")[2]), bool(partial)))
    return tuple(found)


def remove(root: Path, selected: tuple[Receipt, ...]) -> tuple[int, int, list[str]]:
    """Delete only confirmed, still-identical files. Never walk or remove a directory."""
    root = root.resolve()
    count = size = 0
    failures = []
    if not selected:
        return count, size, failures
    with transaction() as db:
        for item in selected:
            path = item.path
            if _signature(root, path) != item.signature:
                continue
            key = (str(root), path.relative_to(root).as_posix(), item.signature)
            if not db.execute("SELECT 1 FROM outputs WHERE root=? AND path=? AND signature=?", key).fetchone():
                continue
            try:
                path.unlink()
            except OSError as exc:
                failures.append(f"{path.name}: {exc}")
                continue
            db.execute("DELETE FROM outputs WHERE root=? AND path=? AND signature=?", key)
            count += 1
            size += item.size
    return count, size, failures


class JobOutputs:
    def __init__(self, root: Path, url: str, file_id: int):
        self.root = root.resolve()
        self.owner = job_owner(url, file_id)
        self._partials: dict[Path, Receipt] = {}

    def written(self, path: Path, *, partial: bool = False) -> None:
        item = record(self.root, self.owner, path, partial)
        if partial and item is not None:
            self._partials[item.path] = item

    def discard_partial(self) -> None:
        try:
            _, _, errors = remove(self.root, tuple(self._partials.values()))
            for error in errors:
                log.warning("Eliminazione del parziale fallita: %s", error)
        except (sqlite3.Error, OSError) as exc:
            log.warning("Registro dei parziali non disponibile: %s", exc)

    def moved(self, before: Path, after: Path) -> None:
        """Follow a completed single-file job's directory rename by file identity."""
        if not _INDEX.is_file():
            return
        try:
            with transaction() as db:
                rows = list(db.execute("SELECT path, signature FROM outputs WHERE root=? AND owner=?",
                                       (str(self.root), self.owner)))
                for relative, signature in rows:
                    old = self.root / relative
                    if old.is_relative_to(before):
                        new = after / old.relative_to(before)
                        if _signature(self.root, new) == signature:
                            db.execute("UPDATE OR REPLACE outputs SET path=? WHERE root=? AND path=?",
                                       (new.relative_to(self.root).as_posix(), str(self.root), relative))
        except (sqlite3.Error, OSError) as exc:
            log.warning("Aggiornamento dei percorsi registrati fallito: %s", exc)


@contextmanager
def write_partial(path: Path, outputs: JobOutputs | None):
    """Take the final receipt after the serial stream closes, also on cancellation."""
    stream = path.open("wb")
    try:
        with stream:
            yield stream
    finally:
        if outputs is not None:
            outputs.written(path, partial=True)
