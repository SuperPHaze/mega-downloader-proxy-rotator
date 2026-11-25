"""Inventario locale dei file interrotti. La dimensione di un .part può essere preallocata."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Event

from src.core import session_store
from src.core.config import LOGS_DIR, PARALLEL_MIN_SEGMENT_BYTES
from src.core.download_history import completion_records
from src.core.errors import UserFacingRuntimeError
from src.core.failed_log import read_failed_links
from src.core.mega_links import MEGA_PREFIX, parse_file_link, parse_folder_job_url


class RecoveryChanged(UserFacingRuntimeError):
    """Il file scelto non è più quello esaminato dall'utente."""

    def __init__(self):
        super().__init__("partial_changed")


def link_handle(url: str) -> str | None:
    if isinstance(url, str) and url.startswith(MEGA_PREFIX):
        file = parse_file_link(url)
        if file is not None:
            return file.handle
        job = parse_folder_job_url(url)
        if job is not None:
            return job.node_handle
    return None


def _source_path(part: Path) -> Path:
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(part.absolute())))).hexdigest()
    return LOGS_DIR / "partial-sources" / (key + ".json")


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_source(part: Path, url: str, total: int) -> None:
    """Il link con chiave resta nei dati locali dell'app, anche con destinazione condivisa."""
    if not link_handle(url):
        return
    target = _source_path(part)
    tmp = None
    try:
        st = part.stat()
        data = {"dev": st.st_dev, "ino": st.st_ino, "size": total, "url": url}
        if _read_json(target) == data:
            return
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False, encoding="utf-8") as stream:
            tmp = Path(stream.name)
            json.dump(data, stream)
        os.replace(tmp, target)
    except OSError:
        pass  # Il link si può sempre reinserire manualmente.
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def forget_source(part: Path) -> None:
    try:
        _source_path(part).unlink(missing_ok=True)
    except OSError:
        pass


def _checkpoint(data: dict, size: int) -> tuple[int, set[tuple[int, int]]]:
    chunk = data.get("chunk_size")
    done = data.get("done")
    if (type(chunk) is not int or chunk < 16 or chunk % 16 or type(data.get("file_size")) is not int
            or data["file_size"] != size
            or not isinstance(data.get("file_handle"), str) or not data["file_handle"]
            or not isinstance(done, list)):
        return 0, set()
    step = size if size <= PARALLEL_MIN_SEGMENT_BYTES else chunk
    ranges = set()
    for item in done:
        if not isinstance(item, list) or len(item) != 2 or not all(type(n) is int for n in item):
            return 0, set()
        start, end = item
        if not 0 <= start <= end < size or start % step or end != min(start + step, size) - 1:
            return 0, set()
        ranges.add((start, end))
    return chunk, ranges


@dataclass(frozen=True)
class PartialDownload:
    root: Path
    target: Path                         # nome finale, anche per il formato precedente a .part
    identity: tuple[int, int]
    size: int
    handle: str | None
    chunk_size: int
    saved: int
    url: str = field(default="", repr=False)
    in_history: bool = False
    expected_size: int | None = None

    @property
    def part(self) -> Path:
        return self.target.with_name(self.target.name + ".part")

    def remove(self) -> None:
        """Rimuove solo il file selezionato, anche dopo la promozione al nome finale."""
        if self.target.parent.resolve(strict=True) != self.target.parent:
            raise RecoveryChanged()
        files = [p for p in (self.part, self.target) if os.path.lexists(p)]
        if len(files) != 1:
            raise RecoveryChanged()
        path = files[0]
        st = path.lstat()
        if (st.st_dev, st.st_ino) != self.identity or not stat.S_ISREG(st.st_mode):
            raise RecoveryChanged()
        path.unlink()
        path.with_name(path.name + ".progress.json").unlink(missing_ok=True)
        forget_source(self.part)

    def validate(self, handle: str, size: int, target: Path) -> set[tuple[int, int]]:
        """Ricontrolla associazione e blocchi prima di scrivere, anche quando il job ha un nuovo ID."""
        if (target != self.target or size < self.size
                or (self.expected_size is not None and size != self.expected_size)
                or (self.handle and handle != self.handle)
                or (self.url and handle != link_handle(self.url))):
            raise RecoveryChanged()
        try:
            current, ranges = inspect_partial(self.root, target)
        except (OSError, ValueError) as exc:
            raise RecoveryChanged() from exc
        if (current.identity != self.identity or current.size not in (self.size, size)
                or (current.expected_size is not None and current.expected_size != size)
                or (current.handle and current.handle != handle)
                or (current.url and link_handle(current.url) != handle)
                or (self.saved and (current.chunk_size != self.chunk_size or current.saved < self.saved))):
            raise RecoveryChanged()
        return ranges


def inspect_partial(root: Path, target: Path) -> tuple[PartialDownload, set[tuple[int, int]]]:
    part = target.with_name(target.name + ".part")
    if not target.is_relative_to(root) or target.parent.resolve(strict=True) != target.parent:
        raise RecoveryChanged()
    if os.path.lexists(target):
        old_map = target.with_name(target.name + ".progress.json")
        if os.path.lexists(part) or old_map.is_symlink() or not old_map.is_file():
            raise RecoveryChanged()
        part = target
    st = part.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise RecoveryChanged()
    sidecar = part.with_name(part.name + ".progress.json")
    if sidecar.is_symlink() or sidecar.with_suffix(sidecar.suffix + ".tmp").is_symlink():
        raise RecoveryChanged()
    data = _read_json(sidecar)
    chunk, ranges = _checkpoint(data, st.st_size)
    handle = data.get("file_handle")
    if not isinstance(handle, str) or not handle:
        handle = None
    source = _read_json(_source_path(part))
    url = source.get("url", "")
    if ((source.get("dev"), source.get("ino")) != (st.st_dev, st.st_ino)
            or type(source.get("size")) is not int or source["size"] < st.st_size
            or not link_handle(url) or (handle and link_handle(url) != handle)):
        url = ""
    total = source["size"] if url else (st.st_size if chunk else None)
    return PartialDownload(root, target, (st.st_dev, st.st_ino), st.st_size, handle, chunk,
                           sum(end - start + 1 for start, end in ranges), url, expected_size=total), ranges


def scan_partials(root: Path, session_links=(), *, stop: Event | None = None) -> list[PartialDownload]:
    root = root.resolve()
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    def on_error(exc):
        if Path(exc.filename) == root:
            raise exc

    files_on_disk = []
    for directory, dirs, files in os.walk(root, onerror=on_error):
        if stop and stop.is_set():
            return []
        parent = Path(directory)
        dirs[:] = [name for name in dirs if not (parent / name).is_symlink()]
        targets = {p.removesuffix(".part") for p in files if p.endswith(".part")}
        targets.update(p.removesuffix(".progress.json") for p in files
                       if p.endswith(".progress.json") and not p.endswith(".part.progress.json"))
        # Un .part senza metadati potrebbe appartenere a un altro programma.
        job_layout = re.fullmatch(r"ciclo_\d+", parent.name) and re.fullmatch(r".+_\d+", parent.parent.name)
        for name in targets:
            if stop and stop.is_set():
                return []
            if not name:
                continue
            try:
                entry, _ = inspect_partial(root, parent / name)
            except (RecoveryChanged, ValueError, OSError):
                continue
            if job_layout or entry.handle or entry.url:
                files_on_disk.append(entry)
    if not files_on_disk:
        return []

    by_handle = defaultdict(set)
    by_name = defaultdict(set)
    completed = set()
    for rec in completion_records():
        if stop and stop.is_set():
            return []
        url = rec.get("url", "")
        handle = link_handle(url)
        if handle and rec.get("handle") == handle:
            by_handle[handle].add(url)
            completed.add(handle)
            name, size = rec.get("file_name"), rec.get("file_size")
            if isinstance(name, str) and type(size) is int:
                by_name[name, size].add(url)
    failed = [r.get("url") for r in read_failed_links() if isinstance(r, dict)]
    for url in [*session_links, *session_store.load(), *failed]:
        handle = link_handle(url)
        if handle:
            by_handle[handle].add(url)
    found = []
    for entry in files_on_disk:
        name_matches = by_name[entry.target.name, entry.size]
        candidates = by_handle[entry.handle] if entry.handle else name_matches
        url = entry.url or (next(iter(candidates)) if len(candidates) == 1 else "")
        total = entry.expected_size
        if not entry.handle and url in name_matches:
            total = entry.size
        completed_before = (entry.handle or link_handle(url)) in completed
        found.append(replace(entry, url=url, expected_size=total, in_history=completed_before))
    return sorted(found, key=lambda e: (e.target.name.casefold(), str(e.target)))
