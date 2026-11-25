"""Scelta e proprietà dei singoli file in una destinazione condivisa."""
import os
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from itertools import count
from pathlib import Path

from PyQt6.QtCore import QFile, QLockFile

from src.core.file_naming import numbered_file_name
from src.core.partial_downloads import (
    PartialDownload, RecoveryChanged, inspect_partial, remember_source,
)


_WORK_SUFFIXES = (".part", ".progress.json", ".part.progress.json", ".part.progress.json.tmp")
_LOCK_SUFFIX = ".part.lock"


def _lock(target: Path) -> QLockFile:
    lock = QLockFile(str(target) + _LOCK_SUFFIX)
    lock.setStaleLockTime(0)
    return lock


@contextmanager
def target_lock(target: Path):
    lock = _lock(target)
    if not lock.tryLock(0):
        raise RecoveryChanged()
    try:
        yield
    finally:
        lock.unlock()


def _occupied(target: Path) -> bool:
    name = str(target)
    if any(os.path.lexists(name + suffix) for suffix in ("", *_WORK_SUFFIXES)):
        return True
    # Anche il nome remoto può coincidere con il checkpoint di un altro download.
    return any(name.endswith(suffix) and os.path.lexists(name[:-len(suffix)] + _LOCK_SUFFIX)
               for suffix in (*_WORK_SUFFIXES, _LOCK_SUFFIX))


@contextmanager
def available_target(requested: Path):
    """Riserva il primo nome libero, anche tra due istanze dell'app."""
    for number in count(1):
        path = requested if number == 1 else requested.with_name(numbered_file_name(requested.name, number))
        if _occupied(path) or os.path.lexists(str(path) + _LOCK_SUFFIX):
            continue
        lock = _lock(path)
        if not lock.tryLock(0):
            if lock.error() == QLockFile.LockError.LockFailedError:
                continue
            raise RecoveryChanged()
        try:
            if _occupied(path):
                continue
            yield path
            return
        finally:
            lock.unlock()


def prune_empty(directory: Path, root: Path) -> None:
    while directory != root and directory.is_relative_to(root) and directory.resolve() == directory:
        try:
            directory.rmdir()
        except OSError:
            break
        directory = directory.parent


def rename_without_replacing(source: Path, destination: Path) -> None:
    if not QFile(str(source)).rename(str(destination)):
        raise RecoveryChanged()


class JobFiles:
    """Percorsi e identità realmente scritti dal job, conservati anche al suo riavvio."""

    def __init__(self, root: Path, recovery: PartialDownload | None = None):
        self.root = root.resolve()
        self.partial = recovery
        self.completed: dict[Path, tuple[int, int, int, int]] = {}

    @contextmanager
    def destination(self, directory: Path, name: str, recovery: PartialDownload | None = None):
        directory = directory.absolute()
        if (directory.resolve() != directory or not directory.is_relative_to(self.root)
                or Path(name).name != name or name in ("", ".", "..")):
            raise RecoveryChanged()
        if recovery and (recovery.root != self.root
                         or name != (recovery.source_name or recovery.target.name)
                         or directory not in (recovery.target.parent, self.root)):
            raise RecoveryChanged()
        directory.mkdir(parents=True, exist_ok=True)
        with ExitStack() as locks:
            if recovery:
                locks.enter_context(target_lock(recovery.target))
            if recovery and directory == recovery.target.parent:
                final = recovery.target
            else:
                final = locks.enter_context(available_target(directory / name))
            previous = self.partial
            try:
                yield final
            finally:
                # Un tentativo interrotto può aver scritto altri byte o salvato nuovi blocchi.
                if self.partial is not None and self.partial is not previous:
                    self._refresh_partial()

    def _refresh_partial(self) -> None:
        item = self.partial
        try:
            current, _ = inspect_partial(self.root, item.target)
        except (OSError, ValueError, RecoveryChanged):
            return
        if current.identity == item.identity:
            self.partial = replace(item, size=current.size, saved=current.saved,
                                   chunk_size=current.chunk_size or item.chunk_size)

    def started(self, target: Path, url: str, size: int, name: str, chunk_size: int = 0) -> None:
        part = target.with_name(target.name + ".part")
        remember_source(part, url, size, name)
        entry, _ = inspect_partial(self.root, target)
        self.partial = replace(entry, url=url, expected_size=size, source_name=name,
                               chunk_size=entry.chunk_size or chunk_size)

    @staticmethod
    def signature(path: Path) -> tuple[int, int, int, int]:
        st = path.lstat()
        return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns

    def finished(self, path: Path) -> None:
        self.completed[path] = self.signature(path)
        self.partial = None

    def publish(self, final: Path) -> None:
        item = self.partial
        if item is None or item.part.parent.resolve() != item.part.parent or final.parent.resolve() != final.parent:
            raise RecoveryChanged()
        st = item.part.lstat()
        if ((st.st_dev, st.st_ino) != item.identity or st.st_size != item.expected_size
                or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1):
            raise RecoveryChanged()
        # QFile.rename rifiuta anche un omonimo apparso dopo la prenotazione.
        rename_without_replacing(item.part, final)
        self.finished(final)

    def discard(self, *, include_completed: bool = False) -> list[Path]:
        removed = []
        if self.partial is not None:
            item = self.partial
            with target_lock(item.target):
                item.remove()
            self.partial = None
            removed.append(item.target)
        if include_completed:
            for path, signature in list(self.completed.items()):
                if not os.path.lexists(path):
                    continue
                with target_lock(path):
                    if path.resolve() != path or self.signature(path) != signature:
                        raise RecoveryChanged()
                    path.unlink()
                del self.completed[path]
                removed.append(path)
        for path in removed:
            prune_empty(path.parent, self.root)
        return removed
