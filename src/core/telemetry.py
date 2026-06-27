# Scatola nera: recorder strutturato asincrono per l'analisi post-sessione.
# Principio: il recorder e' STUPIDO e affidabile. Registra eventi grezzi, non
# calcola aggregati (quelli li fa l'analizzatore offline, Fase 3). Il thread di
# download NON fa mai I/O: chiama solo emit() che fa un enqueue O(1). Un writer
# daemon drena la coda e scrive JSONL a batch. Questo rende sicuro anche il
# firehose (un campione per ogni lettura da 64 KB) senza falsare la misura.
from __future__ import annotations

import json
import os
import platform
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from src.core.config import (
    TELEMETRY_DIR,
    TELEMETRY_ENABLED,
    TELEMETRY_FLUSH_INTERVAL_S,
)

_SENTINEL = object()


class _Session:
    """Una sessione di cattura. Possiede la coda, il writer daemon e i file
    handle per stream (events/samples). Tutti i record passano per la coda;
    il manifest e' l'unica scrittura sincrona (one-shot all'avvio)."""

    def __init__(self, session_id: str, out_dir: Path) -> None:
        self.session_id = session_id
        self.out_dir = out_dir
        self._q: "queue.Queue[tuple[str, dict] | object]" = queue.Queue()
        self._writers: dict[str, object] = {}
        self.dropped = 0
        self._thread = threading.Thread(
            target=self._run, name="TelemetryWriter", daemon=True
        )
        self._thread.start()

    def _file(self, stream: str):
        fh = self._writers.get(stream)
        if fh is None:
            fh = open(
                self.out_dir / f"{stream}.jsonl",
                "a", encoding="utf-8", buffering=1024 * 64,
            )
            self._writers[stream] = fh
        return fh

    def emit(self, stream: str, record: dict) -> None:
        # Hot path: solo enqueue, nessun I/O, non solleva mai.
        try:
            self._q.put_nowait((stream, record))
        except Exception:
            self.dropped += 1

    def _run(self) -> None:
        batch: list[tuple[str, dict]] = []
        last_flush = time.monotonic()
        while True:
            try:
                item = self._q.get(timeout=TELEMETRY_FLUSH_INTERVAL_S)
            except queue.Empty:
                item = None
            if item is _SENTINEL:
                # Drena tutto cio' che resta in coda, poi flush ed esci.
                while True:
                    try:
                        rest = self._q.get_nowait()
                    except queue.Empty:
                        break
                    if rest is not _SENTINEL:
                        batch.append(rest)  # type: ignore[arg-type]
                self._flush(batch)
                return
            if item is not None:
                batch.append(item)  # type: ignore[arg-type]
            now = time.monotonic()
            if batch and (now - last_flush >= TELEMETRY_FLUSH_INTERVAL_S
                          or len(batch) >= 1000):
                self._flush(batch)
                batch = []
                last_flush = now

    def _flush(self, batch: list[tuple[str, dict]]) -> None:
        for stream, record in batch:
            try:
                line = json.dumps(record, default=str, ensure_ascii=False)
                self._file(stream).write(line + "\n")
            except Exception:
                pass  # una riga rotta non deve fermare la cattura
        for fh in self._writers.values():
            try:
                fh.flush()
            except Exception:
                pass

    def close(self) -> None:
        self._q.put(_SENTINEL)
        self._thread.join(timeout=10)
        for fh in self._writers.values():
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass


_lock = threading.Lock()
_session: _Session | None = None


def start_session(session_id: str, manifest: dict) -> None:
    """Apre una nuova sessione di cattura e scrive il manifest (sincrono).
    No-op se TELEMETRY_ENABLED e' False. Idempotente: una start con sessione
    gia' aperta la chiude prima (difesa contro doppie start)."""
    global _session
    if not TELEMETRY_ENABLED:
        return
    with _lock:
        if _session is not None:
            _session.close()
            _session = None
        out_dir = TELEMETRY_DIR / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        full = {
            "session_id": session_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "host_os": platform.platform(),
            "python": sys.version.split()[0],
            "pid": os.getpid(),
        }
        full.update(manifest or {})
        try:
            (out_dir / "manifest.json").write_text(
                json.dumps(full, default=str, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        _session = _Session(session_id, out_dir)


def is_active() -> bool:
    return _session is not None


def emit(stream: str, record: dict) -> None:
    """Accoda un record sullo stream indicato ('events' o 'samples').
    Arricchisce con session_id e ts. No-op se nessuna sessione attiva."""
    s = _session
    if s is None:
        return
    record.setdefault("session_id", s.session_id)
    record.setdefault("ts", datetime.now().isoformat(timespec="milliseconds"))
    s.emit(stream, record)


def event(event_type: str, **fields) -> None:
    """Helper per un evento discreto su events.jsonl."""
    if _session is None:
        return
    rec = {"event_type": event_type}
    rec.update(fields)
    emit("events", rec)


def chunk_attempt(record: dict) -> None:
    """Helper per un record di tentativo-chunk su events.jsonl."""
    if _session is None:
        return
    record["event_type"] = "chunk_attempt"
    emit("events", record)


def sample(record: dict) -> None:
    """Helper per un campione aggregato a 1 Hz su samples.jsonl."""
    if _session is None:
        return
    emit("samples", record)


def close() -> None:
    """Chiude la sessione corrente (drena la coda, chiude i file)."""
    global _session
    with _lock:
        if _session is not None:
            _session.close()
            _session = None
