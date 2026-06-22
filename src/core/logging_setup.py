# Configurazione centralizzata del logging: console + file rotante.
# Chiamare setup_logging() una sola volta all'avvio (in src/main.py).
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILE = Path(__file__).resolve().parents[2] / "app.log"
_CRASH_LOG_FILE = Path(__file__).resolve().parents[2] / "crash.log"
_FORMAT = "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
_initialized = False

# Handle di crash.log tenuto vivo a livello di modulo per tutta la vita del
# processo: faulthandler ci scrive il traceback C nativo di un segfault/abort
# (richiede un file object aperto, non un logging handler), e gli hook sotto
# ci scrivono in piu' un estratto leggibile delle eccezioni Python fatali.
_crash_file_handle = None


def crash_log_path() -> Path:
    return _CRASH_LOG_FILE


def _write_crash_log(text: str) -> None:
    if _crash_file_handle is None:
        return
    try:
        _crash_file_handle.write(text)
        _crash_file_handle.flush()
    except Exception:
        pass  # crash.log stesso non deve poter far cadere il processo


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    # Senza questo hook, un'eccezione non gestita su un thread secondario
    # (es. un QThread che esce dal proprio run() in modo imprevisto) sparisce
    # silenziosamente: il default di Python la stampa solo su stderr, che di
    # notte nessuno guarda.
    thread_name = args.thread.name if args.thread is not None else "?"
    logging.getLogger("threading").error(
        "Eccezione non gestita nel thread %s", thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    ts = datetime.now().isoformat(timespec="seconds")
    tb_text = "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    _write_crash_log(f"{ts} [THREAD-EXC] {thread_name}\n{tb_text}\n")


def setup_logging(level: int = logging.DEBUG) -> Path:
    global _initialized, _crash_file_handle
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

    # crash.log: append, line-buffered. Se non e' scrivibile (permessi,
    # disco pieno) la diagnostica nativa resta disattivata ma l'app continua:
    # non e' un errore che deve impedire l'avvio.
    try:
        _crash_file_handle = open(_CRASH_LOG_FILE, "a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=_crash_file_handle, all_threads=True)
    except OSError:
        root.warning("crash.log non apribile: faulthandler disabilitato", exc_info=True)

    threading.excepthook = _threading_excepthook

    _initialized = True
    root.info("Logging inizializzato. File: %s", _LOG_FILE)
    return _LOG_FILE


def install_qt_message_handler() -> None:
    """Instrada i messaggi interni di Qt (warning/critical/fatal) sul logger
    Python invece di lasciarli solo sulla console. Import di PyQt6 locale
    (come da convenzione delle dipendenze pesanti): questa funzione va
    chiamata dal solo entry point GUI, dopo setup_logging() e prima di
    creare la QApplication."""
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    qt_log = logging.getLogger("qt")

    def _handler(msg_type, _context, message) -> None:
        if msg_type == QtMsgType.QtDebugMsg:
            qt_log.debug(message)
        elif msg_type == QtMsgType.QtInfoMsg:
            qt_log.info(message)
        elif msg_type == QtMsgType.QtWarningMsg:
            qt_log.warning(message)
        elif msg_type == QtMsgType.QtCriticalMsg:
            qt_log.error(message)
        elif msg_type == QtMsgType.QtFatalMsg:
            qt_log.critical(message)
            ts = datetime.now().isoformat(timespec="seconds")
            _write_crash_log(f"{ts} [QT-FATAL] {message}\n")
        else:
            qt_log.info(message)

    qInstallMessageHandler(_handler)
