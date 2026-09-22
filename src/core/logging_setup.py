# Configurazione centralizzata del logging: console + file rotante.
# Chiamare setup_logging() una sola volta all'avvio (in src/main.py).
from __future__ import annotations

import faulthandler
import io
import json
import logging
import sys
import threading
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import EVENTS_LOG, EVENTS_LOG_BACKUPS, EVENTS_LOG_MAX_BYTES, LOGS_DIR, TERMINAL_LOG

_LOG_FILE = LOGS_DIR / "app.log"
_CRASH_LOG_FILE = LOGS_DIR / "crash.log"
_TERMINAL_LOG_FILE = LOGS_DIR / TERMINAL_LOG
_FORMAT = "%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s"
_initialized = False

# Attributi standard di LogRecord: tutto cio' che NON e' in questo insieme e
# presente in record.__dict__ e' un campo "extra" passato dal chiamante, e va
# nel JSONL (vedi rules/logging.md: instrumentazione extra={"event_type": ...}).
_STANDARD_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JsonLinesFormatter(logging.Formatter):
    """Formatter per il log strutturato universale (events.jsonl): una riga
    JSON per record, con tutti gli extra del chiamante. Non solleva mai:
    in caso di errore di serializzazione emette una riga minima."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            payload = {
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "thread": record.threadName,
                "msg": record.getMessage(),
            }
            for key, value in record.__dict__.items():
                if key in _STANDARD_RECORD_ATTRS or key.startswith("_"):
                    continue
                payload[key] = value
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
            return json.dumps(payload, default=str, ensure_ascii=False)
        except Exception:
            try:
                minimal = {
                    "ts": datetime.now().isoformat(timespec="milliseconds"),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": str(getattr(record, "msg", "")),
                    "_formatter_error": True,
                }
                return json.dumps(minimal, default=str, ensure_ascii=False)
            except Exception:
                return '{"_formatter_error": true}'

# Handle di crash.log tenuto vivo a livello di modulo per tutta la vita del
# processo: faulthandler ci scrive il traceback C nativo di un segfault/abort
# (richiede un file object aperto, non un logging handler), e gli hook sotto
# ci scrivono in piu' un estratto leggibile delle eccezioni Python fatali.
_crash_file_handle = None

# Handle di terminal-log.txt tenuto vivo a livello di modulo (come
# _crash_file_handle) per non farlo garbage-collectare per tutta la sessione.
_terminal_log_file_handle = None


class _TeeStream:
    """Sdoppia un flusso (stdout/stderr) su un file, oltre al flusso originale.

    Gli attributi non definiti qui (isatty, encoding, ...) sono delegati al
    flusso originale via __getattr__: librerie e Qt devono vedere il flusso
    reale, non il tee. fileno() resta quello reale, quindi l'output nativo
    C-level continua ad andare al terminale e non al file (qui catturiamo solo
    il livello Python, sufficiente per i nostri log).

    **Il flusso originale puo' mancare del tutto** (`None`): e' il caso
    dell'avvio silenzioso con `pythonw.exe`, dove non esiste console e Python
    mette `sys.stdout`/`sys.stderr` a `None`. In quel caso il tee resta l'UNICO
    consumatore — scrive solo su file — e nessun metodo deve sollevare:
    basterebbe la prima riga di log per far cadere l'applicazione prima ancora
    che la finestra compaia. `fileno()` in quel caso NON inventa un
    descrittore: dichiara che non ce n'e' uno, come fa qualunque flusso Python
    senza supporto (`io.UnsupportedOperation` e' sia OSError sia ValueError,
    quindi i chiamanti difensivi la intercettano comunque)."""

    def __init__(self, stream, file):
        self._stream = stream
        self._file = file

    def write(self, data):
        if self._stream is not None:
            try:
                self._stream.write(data)
            except Exception:
                pass  # console sparita a meta' sessione: il file resta
        try:
            self._file.write(data)
            self._file.flush()
        except Exception:
            pass  # un file rotto non deve uccidere l'app né l'output a video
        return len(data)

    def flush(self):
        if self._stream is not None:
            try:
                self._stream.flush()
            except Exception:
                pass
        try:
            self._file.flush()
        except Exception:
            pass

    def isatty(self):
        # Senza console non c'e' terminale interattivo: rispondere "non lo so"
        # (delegando a None) farebbe esplodere chi la interroga per decidere
        # se colorare l'output.
        if self._stream is None:
            return False
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    def fileno(self):
        if self._stream is None:
            raise io.UnsupportedOperation(
                "nessun descrittore: processo senza console (pythonw)"
            )
        return self._stream.fileno()

    def __getattr__(self, name):
        if self._stream is None:
            # Nessun flusso da cui delegare: AttributeError e' la risposta
            # corretta (chi sonda con hasattr() deve vedere "non c'e'").
            raise AttributeError(name)
        return getattr(self._stream, name)


def _install_terminal_tee() -> None:
    """Sdoppia sys.stdout/sys.stderr su logs/terminal-log.txt (riazzerato a
    ogni avvio). Se l'apertura del file fallisce, prosegue senza tee.

    Con `pythonw.exe` i due flussi originali sono `None`: il tee si installa
    lo stesso, e da li' in poi `logs/terminal-log.txt` e' l'unica copia di cio'
    che senza console non si vede piu' da nessuna parte."""
    global _terminal_log_file_handle
    try:
        _terminal_log_file_handle = open(
            _TERMINAL_LOG_FILE, "w", encoding="utf-8", errors="replace", buffering=1,
        )
    except OSError:
        logging.getLogger().warning(
            "terminal-log.txt non apribile: cattura terminale disabilitata", exc_info=True,
        )
        return
    sys.stdout = _TeeStream(sys.stdout, _terminal_log_file_handle)
    sys.stderr = _TeeStream(sys.stderr, _terminal_log_file_handle)


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


def log_unhandled_main_exception(exc_type, exc_value, exc_tb) -> None:
    """Scrive in crash.log un'eccezione non gestita del THREAD PRINCIPALE.

    Gemello di `_threading_excepthook` per i thread secondari. Serviva meno
    finche' l'app partiva da un terminale: il traceback si vedeva a video.
    Con l'avvio silenzioso (pythonw, nessuna console) crash.log e'
    l'unico posto dove quel traceback sta insieme ai crash nativi, ed e' il
    file che `tools/report.py` legge per ricostruire com'e' morta la
    sessione. Non solleva mai: gira dentro un excepthook."""
    ts = datetime.now().isoformat(timespec="seconds")
    try:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:       # pragma: no cover - difensivo
        tb_text = f"{exc_type}: {exc_value}\n"
    _write_crash_log(f"{ts} [MAIN-EXC]\n{tb_text}\n")


def setup_logging(level: int = logging.DEBUG) -> Path:
    global _initialized, _crash_file_handle
    if _initialized:
        return _LOG_FILE

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    _install_terminal_tee()

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(_FORMAT, datefmt="%H:%M:%S")

    # Console (stderr): sys.stderr e' già sdoppiato da _install_terminal_tee(),
    # quindi tutto cio' che passa di qui finisce anche in terminal-log.txt.
    # Se il tee NON si e' installato (file non apribile) e siamo senza console
    # (pythonw), sys.stderr e' None: un StreamHandler su None fallirebbe a ogni
    # riga, in silenzio ma su ogni riga. Meglio non aggiungerlo affatto: il
    # file rotante e events.jsonl restano, ed e' li' che si guarda davvero.
    if sys.stderr is not None:
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(level)
        ch.setFormatter(fmt)
        root.addHandler(ch)
    else:
        root.warning(
            "Nessuno stderr (processo senza console) e nessun tee: "
            "log solo su file",
        )

    # File rotante (5 MB x 3 backup).
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Log strutturato universale (JSON Lines, sempre a DEBUG: nessun filtro a
    # monte, il filtraggio lo fa tools/report.py a valle).
    events_fh = RotatingFileHandler(
        LOGS_DIR / EVENTS_LOG, maxBytes=EVENTS_LOG_MAX_BYTES,
        backupCount=EVENTS_LOG_BACKUPS, encoding="utf-8",
    )
    events_fh.setLevel(logging.DEBUG)
    events_fh.setFormatter(JsonLinesFormatter())
    root.addHandler(events_fh)

    # Riduci rumore di librerie verbose (urllib3 debug = troppo).
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    # crash.log: append, line-buffered. Se non e' scrivibile (permessi,
    # disco pieno) la diagnostica nativa resta disattivata ma l'app continua:
    # non e' un errore che deve impedire l'avvio.
    # Nota per l'avvio silenzioso (pythonw, nessuna console): faulthandler
    # scrive QUI, su un file vero con un descrittore vero, non su sys.stderr —
    # il traceback nativo di un segfault resta quindi disponibile anche senza
    # terminale. E' il motivo per cui `file=` e' esplicito e non va tolto.
    try:
        _crash_file_handle = open(_CRASH_LOG_FILE, "a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=_crash_file_handle, all_threads=True)
    except OSError:
        root.warning("crash.log non apribile: faulthandler disabilitato", exc_info=True)

    threading.excepthook = _threading_excepthook

    _initialized = True
    root.info("Logging inizializzato. File: %s", _LOG_FILE)
    return _LOG_FILE


def _iter_file_handlers():
    """Ogni `FileHandler` installato nel processo: quelli del root (app.log,
    events.jsonl) e quelli dei logger dedicati JSONL (`download_history`,
    `failed_links`, `proxy_sources_stats`), che nascono pigri alla prima
    scrittura e sono quindi presenti solo in certe sessioni."""
    seen: set[int] = set()
    loggers = [logging.getLogger()]
    # La lista dei logger cambia mentre la si scorre (un modulo puo' crearne
    # uno), quindi si fotografa prima.
    for name in list(logging.root.manager.loggerDict):
        candidate = logging.root.manager.loggerDict.get(name)
        if isinstance(candidate, logging.Logger):
            loggers.append(candidate)
    for logger in loggers:
        for handler in list(getattr(logger, "handlers", [])):
            if isinstance(handler, logging.FileHandler) and id(handler) not in seen:
                seen.add(id(handler))
                yield handler


def _truncate_handler_file(handler: logging.FileHandler) -> None:
    """Chiude il flusso del canale, tronca il file e lo riapre.

    E' l'unico modo di azzerare un log MENTRE l'applicazione lo tiene aperto:
    su Windows `unlink` su un file aperto fallisce con errore di permessi.
    Il flusso si riapre subito, ma anche se la riapertura fallisse il canale
    si ricucirebbe da solo: `FileHandler.emit()` riapre quando
    `self.stream is None` e la modalita' non e' `"w"`."""
    handler.acquire()
    try:
        stream = handler.stream
        if stream is not None:
            try:
                stream.flush()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            handler.stream = None
        Path(handler.baseFilename).write_bytes(b"")
        try:
            handler.stream = handler._open()
        except OSError:
            handler.stream = None   # riaperto dal primo emit() utile
    finally:
        handler.release()


def _truncate_terminal_log() -> bool:
    """Azzera `terminal-log.txt` SENZA chiudere l'handle di modulo.

    Qui il flusso non si puo' chiudere e riaprire come per i canali di
    logging: `_TeeStream` ha catturato *questo* oggetto file, e sostituirlo
    lascerebbe il tee a scrivere su un file chiuso (cioe' a perdere l'output
    per il resto della sessione). Si tronca in posto: il file e' aperto in
    modalita' `"w"`, quindi dopo il troncamento la prossima scrittura riparte
    da zero."""
    handle = _terminal_log_file_handle
    if handle is None or handle.closed:
        return False
    try:
        handle.flush()
        handle.truncate(0)
        handle.seek(0)
        return True
    except (OSError, ValueError):
        return False


def reset_log_file(path: Path) -> int:
    """Azzera un file di log e ritorna i byte liberati.

    Un file TENUTO APERTO dall'applicazione (app.log, events.jsonl,
    download_history.log e gli altri JSONL, terminal-log.txt) viene troncato
    attraverso il proprio canale e resta scrivibile: l'applicazione continua a
    loggare senza accorgersene. Un file che nessuno tiene aperto (un archivio
    ruotato come `app.log.1`) viene cancellato direttamente.

    Propaga `OSError` se l'azzeramento fallisce: chi chiama deve poter dire
    all'utente quale voce non e' riuscita.
    """
    target = Path(path)
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target

    if resolved == _TERMINAL_LOG_FILE.resolve() and _truncate_terminal_log():
        return size

    held = False
    for handler in _iter_file_handlers():
        base = getattr(handler, "baseFilename", None)
        if not base:
            continue
        try:
            if Path(base).resolve() != resolved:
                continue
        except OSError:
            continue
        _truncate_handler_file(handler)
        held = True

    if held:
        return size

    if target.exists():
        target.unlink()
    return size


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
