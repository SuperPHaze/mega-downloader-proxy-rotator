# Configurazione centralizzata del logging: console + file rotante.
# Chiamare setup_logging() una sola volta all'avvio (in src/main.py).
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILE = Path(__file__).resolve().parents[2] / "app.log"
_FORMAT = "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
_initialized = False


def setup_logging(level: int = logging.DEBUG) -> Path:
    global _initialized
    if _initialized:
        return _LOG_FILE

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(_FORMAT, datefmt="%H:%M:%S")

    # Console (stderr).
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File rotante (5 MB x 3 backup).
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Riduci rumore di librerie verbose (urllib3 debug = troppo).
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    _initialized = True
    root.info("Logging inizializzato. File: %s", _LOG_FILE)
    return _LOG_FILE
