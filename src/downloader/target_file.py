"""Esclusione tra processi durante la scrittura dello stesso file."""
from contextlib import contextmanager
from pathlib import Path

from PyQt6.QtCore import QFile, QLockFile

from src.core.partial_downloads import RecoveryChanged


@contextmanager
def target_lock(target: Path):
    lock = QLockFile(str(target) + ".part.lock")
    lock.setStaleLockTime(0)  # Un trasferimento può durare più del timeout predefinito.
    if not lock.tryLock(0):
        raise RecoveryChanged()
    try:
        yield
    finally:
        lock.unlock()


def publish_recovery(part: Path, final: Path) -> None:
    # QFile rifiuta la rinomina se esiste già un file col nome di destinazione.
    if not QFile(str(part)).rename(str(final)):
        raise RecoveryChanged()
