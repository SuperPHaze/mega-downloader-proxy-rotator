"""Generatore di report HTML diagnostico (di sola lettura): legge il log
strutturato universale `logs/events.jsonl` (+ rotazioni) e `logs/crash.log`
e produce un report autonomo in `logs/reports/report_<timestamp>.html`.

Non modifica ne' ruota i log: li legge soltanto, in streaming (riga per
riga). Nessuna dipendenza esterna (solo stdlib); il report usa Chart.js da
CDN con fallback tabellare se offline.

Uso:
    python -m tools.report
    python -m tools.report --logs <cartella> --out <file.html>

Formati attesi:
    events.jsonl: una riga JSON per record (vedi
        src/core/logging_setup.py:JsonLinesFormatter), campi base sempre
        presenti (ts ISO-8601 con millisecondi, level, logger, thread, msg)
        + campi extra a livello superiore secondo `event_type`
        (session_start, session_clean_exit, heartbeat, config,
        download_completed, download_abandoned, download_cancelled).
        Le rotazioni (events.jsonl.1 ... events.jsonl.N) sono lette in
        ordine cronologico (dalla piu' vecchia alla corrente).
    crash.log: dump nativi di faulthandler ("Fatal Python error: ..." senza
        timestamp) intervallati da voci scritte dall'app con timestamp ISO:
        "<iso> [THREAD-EXC] ..." / "<iso> [QT-FATAL] ...".
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from src.core.config import EVENTS_LOG, EVENTS_LOG_BACKUPS, LOGS_DIR, REPORTS_DIR

ERROR_LEVELS = {"WARNING", "ERROR", "CRITICAL"}
DOWNLOAD_EVENT_TYPES = {"download_completed", "download_abandoned", "download_cancelled"}

# Voci di crash.log scritte dall'app (timestamp ISO completo, vedi
# logging_setup._write_crash_log). I dump nativi di faulthandler invece NON
# hanno timestamp: iniziano con "Fatal Python error: ...".
CRASH_ENTRY_START_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) \[(?P<kind>THREAD-EXC|QT-FATAL)\]\s?(?P<rest>.*)$"
)
NATIVE_FAULT_START_RE = re.compile(r"^Fatal Python error:")


# === Modello dati =========================================================

@dataclass
class HeartbeatEvent:
    ts: str | None
    mem_rss_mb: float | None
    threads: int | None
    download_attivi: int | None
    pool_vivi: int | None


@dataclass
class LogEvent:
    ts: str | None
    level: str
    logger: str
    thread: str
    msg: str
    exc: str | None = None


@dataclass
class DownloadEvent:
    ts: str | None
    event_type: str  # download_completed | download_abandoned | download_cancelled
    file_id: int | None
    url: str | None = None
    file_name: str | None = None
    file_size: object = None
    attempts: int | None = None
    last_error: str | None = None


@dataclass
class CrashEntry:
    kind: str  # THREAD-EXC | QT-FATAL | NATIVE
    timestamp: str | None
    text: str


@dataclass
class Session:
    start_ts: str | None
    version: str | None
    pid: int | None
    end_ts: str | None = None
    clean_exit: bool = False
    heartbeats: list[HeartbeatEvent] = field(default_factory=list)
    errors: list[LogEvent] = field(default_factory=list)
    downloads: list[DownloadEvent] = field(default_factory=list)
    crashes: list[CrashEntry] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        if self.clean_exit:
            return "CLEAN"
        if self.crashes:
            return "CRASH"
        return "TRONCATA"

    @property
    def effective_end_ts(self) -> str | None:
        if self.end_ts:
            return self.end_ts
        if self.heartbeats:
            return self.heartbeats[-1].ts
        return self.start_ts

    @property
    def mem_peak(self) -> float | None:
        vals = [h.mem_rss_mb for h in self.heartbeats if h.mem_rss_mb is not None]
        return max(vals) if vals else None


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# === Lettura file in streaming ============================================

def find_events_log_files(logs_dir: Path) -> list[Path]:
    """File events.jsonl* in ordine CRONOLOGICO (dal piu' vecchio al piu'
    recente). RotatingFileHandler numera i backup al CONTRARIO: il suffisso
    piu' alto e' il piu' vecchio, events.jsonl (senza suffisso) e' il
    corrente. File assenti vengono saltati senza errori."""
    files: list[Path] = []
    for suffix in range(EVENTS_LOG_BACKUPS, 0, -1):
        p = logs_dir / f"{EVENTS_LOG}.{suffix}"
        if p.exists():
            files.append(p)
    current = logs_dir / EVENTS_LOG
    if current.exists():
        files.append(current)
    return files


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def stream_records(paths: Iterable[Path], malformed_counter: list[int]) -> Iterator[dict]:
    """Legge le righe JSON dei file forniti una alla volta (no caricamento
    integrale in RAM). Le righe malformate vengono contate in
    malformed_counter[0], non interrompono la lettura."""
    for p in paths:
        try:
            f = open(p, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    malformed_counter[0] += 1
                    continue
                if isinstance(rec, dict):
                    yield rec
                else:
                    malformed_counter[0] += 1


# === Ricostruzione sessioni ================================================

def build_sessions(
    records: Iterable[dict],
) -> tuple[list[Session], list[LogEvent], list[DownloadEvent]]:
    """Ritorna (sessioni, errori orfani, download orfani) — "orfani" sono i
    record arrivati senza una sessione apertura corrispondente (session_start
    mai vista, es. log troncato all'inizio)."""
    sessions: list[Session] = []
    current: Session | None = None
    orphan_errors: list[LogEvent] = []
    orphan_downloads: list[DownloadEvent] = []

    for rec in records:
        event_type = rec.get("event_type")
        ts = rec.get("ts")
        level = rec.get("level", "")

        if event_type == "session_start":
            if current is not None:
                # Sessione precedente senza CLEAN EXIT prima del nuovo START:
                # chiusura anomala (verra' marcata CRASH o TRONCATA in base
                # all'eventuale attribuzione di un crash.log).
                sessions.append(current)
            current = Session(start_ts=ts, version=rec.get("app_version"), pid=rec.get("pid"))
            continue

        if event_type == "session_clean_exit":
            if current is not None:
                current.end_ts = ts
                current.clean_exit = True
                sessions.append(current)
                current = None
            continue

        if event_type == "heartbeat":
            if current is not None:
                current.heartbeats.append(HeartbeatEvent(
                    ts=ts, mem_rss_mb=rec.get("mem_rss_mb"), threads=rec.get("threads"),
                    download_attivi=rec.get("download_attivi"), pool_vivi=rec.get("pool_vivi"),
                ))
            continue

        if event_type in DOWNLOAD_EVENT_TYPES:
            dl = DownloadEvent(
                ts=ts, event_type=event_type, file_id=rec.get("file_id"),
                url=rec.get("url"), file_name=rec.get("file_name"),
                file_size=rec.get("file_size"), attempts=rec.get("attempts"),
                last_error=rec.get("last_error"),
            )
            (current.downloads if current is not None else orphan_downloads).append(dl)
            continue

        if level in ERROR_LEVELS:
            ev = LogEvent(
                ts=ts, level=level, logger=rec.get("logger", ""),
                thread=rec.get("thread", ""), msg=rec.get("msg", ""), exc=rec.get("exc"),
            )
            (current.errors if current is not None else orphan_errors).append(ev)
            continue

    if current is not None:
        # File terminato senza session_clean_exit: chiusura anomala (o
        # sessione ancora in corso al momento dell'analisi).
        sessions.append(current)

    return sessions, orphan_errors, orphan_downloads


# === Parsing crash.log ======================================================

def parse_crash_log(text: str) -> list[CrashEntry]:
    """crash.log e' eterogeneo: dump nativi di faulthandler (nessun
    timestamp) intervallati da voci scritte dall'app con timestamp ISO. Una
    nuova voce inizia quando una riga combacia con uno dei due pattern di
    apertura; il corpo accumula le righe successive fino alla prossima voce.
    """
    if not text.strip():
        return []
    lines = text.splitlines()
    entries: list[CrashEntry] = []
    current_kind: str | None = None
    current_ts: str | None = None
    body: list[str] = []

    def _flush() -> None:
        if current_kind is not None:
            entries.append(CrashEntry(
                kind=current_kind, timestamp=current_ts, text="\n".join(body).strip(),
            ))

    for line in lines:
        m = CRASH_ENTRY_START_RE.match(line)
        if m:
            _flush()
            current_kind = m.group("kind")
            current_ts = m.group("ts")
            body = [m.group("rest")] if m.group("rest") else []
            continue
        if NATIVE_FAULT_START_RE.match(line):
            _flush()
            current_kind = "NATIVE"
            current_ts = None
            body = [line]
            continue
        if current_kind is not None:
            body.append(line)
        # righe prima della prima voce riconosciuta vengono scartate
        # (preambolo non strutturato, se presente).

    _flush()
    return entries


def attribute_crashes(sessions: list[Session], crashes: list[CrashEntry]) -> list[CrashEntry]:
    """Associa ogni voce di crash.log alla sessione di events.jsonl piu'
    plausibile, confrontando timestamp ISO completi (data compresa, niente
    ambiguita' di mezzanotte):
    - voci con timestamp (THREAD-EXC/QT-FATAL): la sessione la cui finestra
      [start_ts, effective_end_ts] contiene il timestamp; altrimenti la
      sessione con lo start_ts piu' recente non successivo, altrimenti
      l'ultima sessione.
    - dump nativi (nessun timestamp): attribuiti all'ultima sessione senza
      CLEAN EXIT (un crash nativo termina il processo, quindi e' quasi
      sempre legato alla sessione piu' recente ancora "aperta").
    Ritorna le voci che non si sono potute attribuire a nessuna sessione.
    """
    unattributed: list[CrashEntry] = []
    for c in crashes:
        target: Session | None = None
        if c.timestamp:
            c_dt = _parse_ts(c.timestamp)
            for s in sessions:
                start_dt = _parse_ts(s.start_ts)
                end_dt = _parse_ts(s.effective_end_ts)
                if start_dt and end_dt and c_dt and start_dt <= c_dt <= end_dt:
                    target = s
                    break
            if target is None and c_dt is not None:
                earlier = [s for s in sessions if _parse_ts(s.start_ts) and _parse_ts(s.start_ts) <= c_dt]
                target = earlier[-1] if earlier else (sessions[-1] if sessions else None)
        else:
            open_sessions = [s for s in sessions if not s.clean_exit]
            target = open_sessions[-1] if open_sessions else (sessions[-1] if sessions else None)
        if target is not None:
            target.crashes.append(c)
        else:
            unattributed.append(c)
    return unattributed


# === Rendering HTML ==========================================================

_CHARTJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"

_CSS = """
:root {
  --bg: #0f1115; --panel: #171a21; --border: #2a2e38; --text: #e6e8ec;
  --muted: #9aa1ad; --accent: #4f8cff; --ok: #3ecf8e; --warn: #f5a623; --bad: #f25767;
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text); margin: 0; padding: 24px;
  font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.5;
}
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; margin: 32px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
.subtitle { color: var(--muted); margin-bottom: 24px; font-size: 0.9rem; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 18px; min-width: 150px; flex: 1;
}
.card .label { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: .03em; }
.card .value { font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
th { color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.badge.clean { background: rgba(62,207,142,.15); color: var(--ok); }
.badge.troncata { background: rgba(245,166,35,.15); color: var(--warn); }
.badge.crash { background: rgba(242,87,103,.15); color: var(--bad); }
.badge.completed { background: rgba(62,207,142,.15); color: var(--ok); }
.badge.abandoned { background: rgba(242,87,103,.15); color: var(--bad); }
.badge.cancelled { background: rgba(245,166,35,.15); color: var(--warn); }
.chart-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.chart-wrap canvas { max-height: 320px; }
.fallback-table { display: none; }
.fallback-table.shown { display: block; }
details { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; margin: 6px 0; padding: 8px 12px; }
summary { cursor: pointer; font-size: 0.9rem; }
summary .meta { color: var(--muted); margin-right: 8px; }
pre { white-space: pre-wrap; word-break: break-word; color: #d6d9e0; font-size: 0.82rem; margin: 8px 0 0; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0; }
footer { color: var(--muted); font-size: 0.78rem; margin-top: 32px; text-align: center; }
"""


def _session_badge(outcome: str) -> str:
    cls = {"CLEAN": "clean", "TRONCATA": "troncata", "CRASH": "crash"}.get(outcome, "troncata")
    return f'<span class="badge {cls}">{html.escape(outcome)}</span>'


_DOWNLOAD_BADGE = {
    "download_completed": ("completed", "Completato"),
    "download_abandoned": ("abandoned", "Abbandonato"),
    "download_cancelled": ("cancelled", "Annullato"),
}


def _download_badge(event_type: str) -> str:
    cls, label = _DOWNLOAD_BADGE.get(event_type, ("troncata", event_type))
    return f'<span class="badge {cls}">{html.escape(label)}</span>'


def _fmt_duration(start: str | None, end: str | None) -> str:
    t0, t1 = _parse_ts(start), _parse_ts(end)
    if t0 is None or t1 is None:
        return "n/d"
    delta = t1 - t0
    if delta.total_seconds() < 0:
        return "n/d"
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_chart_data(sessions: list[Session]) -> dict:
    labels: list[str] = []
    mem: list[float | None] = []
    threads: list[int | None] = []
    download_attivi: list[int | None] = []
    pool_vivi: list[int | None] = []
    session_start_marker: list[float | None] = []
    crash_marker: list[float | None] = []

    cursor = 0
    for s in sessions:
        start_marker_idx = cursor
        crash_marker_idx = None
        for hb in s.heartbeats:
            labels.append(hb.ts or f"#{cursor}")
            mem.append(hb.mem_rss_mb)
            threads.append(hb.threads)
            download_attivi.append(hb.download_attivi)
            pool_vivi.append(hb.pool_vivi)
            session_start_marker.append(None)
            crash_marker.append(None)
            crash_marker_idx = cursor
            cursor += 1
        if start_marker_idx < len(mem):
            session_start_marker[start_marker_idx] = mem[start_marker_idx]
        if s.crashes and crash_marker_idx is not None:
            crash_marker[crash_marker_idx] = mem[crash_marker_idx]

    return {
        "labels": labels, "mem": mem, "threads": threads,
        "download_attivi": download_attivi, "pool_vivi": pool_vivi,
        "session_start_marker": session_start_marker, "crash_marker": crash_marker,
    }


def _render_error_details(e: LogEvent, session_label: str) -> str:
    summary = (
        f'<span class="meta">{html.escape(e.ts or "?")} [{html.escape(e.level)}] '
        f'{html.escape(e.logger)} — {html.escape(session_label)}</span>{html.escape(e.msg)}'
    )
    body = html.escape(e.exc) if e.exc else "(nessun traceback disponibile)"
    return f"<details><summary>{summary}</summary><pre>{body}</pre></details>"


def _render_crash_details(c: CrashEntry) -> str:
    ts = c.timestamp or "n/d (dump nativo, nessun timestamp)"
    summary = f'<span class="meta">{html.escape(ts)} [{html.escape(c.kind)}]</span>'
    return f"<details><summary>{summary}</summary><pre>{html.escape(c.text)}</pre></details>"


def render_html(
    sessions: list[Session],
    orphan_errors: list[LogEvent],
    orphan_downloads: list[DownloadEvent],
    unattributed_crashes: list[CrashEntry],
    malformed_lines: int,
    generated_at: str,
) -> str:
    n_sessions = len(sessions)
    n_anomale = sum(1 for s in sessions if s.outcome != "CLEAN")
    n_errors = sum(len(s.errors) for s in sessions) + len(orphan_errors)
    all_downloads = [(s, d) for s in sessions for d in s.downloads] + [(None, d) for d in orphan_downloads]
    n_downloads = len(all_downloads)
    n_native = sum(1 for s in sessions for c in s.crashes if c.kind == "NATIVE") + sum(
        1 for c in unattributed_crashes if c.kind == "NATIVE"
    )
    mem_peak = None
    for s in sessions:
        p = s.mem_peak
        if p is not None and (mem_peak is None or p > mem_peak):
            mem_peak = p

    cards_html = f"""
    <div class="cards">
      <div class="card"><div class="label">Sessioni</div><div class="value">{n_sessions}</div></div>
      <div class="card"><div class="label">Chiusure anomale</div><div class="value">{n_anomale}</div></div>
      <div class="card"><div class="label">Errori/warning</div><div class="value">{n_errors}</div></div>
      <div class="card"><div class="label">Eventi download</div><div class="value">{n_downloads}</div></div>
      <div class="card"><div class="label">Crash nativi</div><div class="value">{n_native}</div></div>
      <div class="card"><div class="label">Picco mem_rss</div><div class="value">{f"{mem_peak:.0f} MB" if mem_peak is not None else "n/d"}</div></div>
      <div class="card"><div class="label">Righe malformate</div><div class="value">{malformed_lines}</div></div>
    </div>
    """

    rows = []
    for s in sessions:
        rows.append(
            "<tr>"
            f"<td>{html.escape(s.version or '?')}</td>"
            f"<td>{html.escape(str(s.pid) if s.pid is not None else '?')}</td>"
            f"<td>{html.escape(s.start_ts or '?')}</td>"
            f"<td>{html.escape(s.effective_end_ts or '?')}</td>"
            f"<td>{_fmt_duration(s.start_ts, s.effective_end_ts)}</td>"
            f"<td>{_session_badge(s.outcome)}</td>"
            f"<td>{f'{s.mem_peak:.0f} MB' if s.mem_peak is not None else 'n/d'}</td>"
            "</tr>"
        )
    sessions_table = (
        "<table><thead><tr><th>Versione</th><th>PID</th><th>Inizio</th><th>Fine</th>"
        "<th>Durata</th><th>Esito</th><th>Mem max</th></tr></thead><tbody>"
        + ("".join(rows) if rows else '<tr><td colspan="7" class="empty">Nessuna sessione trovata.</td></tr>')
        + "</tbody></table>"
    )

    def _session_label(s: Session | None) -> str:
        return f"sessione {s.start_ts}" if s is not None else "(orfano, nessuna sessione)"

    all_errors = [(s, e) for s in sessions for e in s.errors] + [(None, e) for e in orphan_errors]
    errors_html = (
        "".join(_render_error_details(e, _session_label(s)) for s, e in all_errors)
        if all_errors else '<div class="empty">Nessun errore/warning trovato.</div>'
    )

    dl_rows = []
    for s, d in all_downloads:
        detail = ""
        if d.event_type == "download_completed":
            size = d.file_size if d.file_size is not None else "n/d"
            detail = f"{html.escape(d.file_name or '?')} ({size} byte)"
        elif d.event_type == "download_abandoned":
            detail = f"tentativi={d.attempts} — {html.escape(d.last_error or '')}"
        elif d.event_type == "download_cancelled":
            detail = "cancellato dall'utente"
        dl_rows.append(
            "<tr>"
            f"<td>{html.escape(d.ts or '?')}</td>"
            f"<td>{d.file_id if d.file_id is not None else '?'}</td>"
            f"<td>{_download_badge(d.event_type)}</td>"
            f"<td>{html.escape(d.url or '')}</td>"
            f"<td>{detail}</td>"
            "</tr>"
        )
    downloads_table = (
        "<table><thead><tr><th>Quando</th><th>File ID</th><th>Esito</th><th>URL</th><th>Dettaglio</th></tr></thead><tbody>"
        + ("".join(dl_rows) if dl_rows else '<tr><td colspan="5" class="empty">Nessun evento download trovato.</td></tr>')
        + "</tbody></table>"
    )

    all_crashes = [c for s in sessions for c in s.crashes] + unattributed_crashes
    crashes_html = (
        "".join(_render_crash_details(c) for c in all_crashes)
        if all_crashes else '<div class="empty">Nessun crash nativo trovato in crash.log.</div>'
    )

    chart_data = _build_chart_data(sessions)
    has_heartbeats = bool(chart_data["labels"])
    chart_data_json = json.dumps(chart_data).replace("</", "<\\/")

    if has_heartbeats:
        fallback_rows = "".join(
            f"<tr><td>{html.escape(t)}</td><td>{m if m is not None else 'n/d'}</td>"
            f"<td>{th}</td><td>{dl}</td><td>{pv}</td></tr>"
            for t, m, th, dl, pv in zip(
                chart_data["labels"], chart_data["mem"], chart_data["threads"],
                chart_data["download_attivi"], chart_data["pool_vivi"],
            )
        )
        charts_section = f"""
        <div class="chart-wrap">
          <canvas id="chartMem" height="90"></canvas>
          <table class="fallback-table" id="fallbackMem">
            <thead><tr><th>Quando</th><th>mem_rss (MB)</th><th>Thread</th><th>Download attivi</th><th>Pool vivi</th></tr></thead>
            <tbody>{fallback_rows}</tbody>
          </table>
        </div>
        <div class="chart-wrap">
          <canvas id="chartThreads" height="90"></canvas>
        </div>
        """
    else:
        charts_section = '<div class="empty">Nessun dato HEARTBEAT trovato nei log.</div>'

    script = f"""
    <script>
    const CHART_DATA = {chart_data_json};
    function buildCharts() {{
      if (typeof Chart === 'undefined') {{
        const fb = document.getElementById('fallbackMem');
        if (fb) fb.classList.add('shown');
        return;
      }}
      try {{
        new Chart(document.getElementById('chartMem'), {{
          data: {{
            labels: CHART_DATA.labels,
            datasets: [
              {{ type: 'line', label: 'mem_rss (MB)', data: CHART_DATA.mem,
                 borderColor: '#4f8cff', backgroundColor: 'rgba(79,140,255,.15)',
                 spanGaps: false, pointRadius: 2, tension: 0.15 }},
              {{ type: 'scatter', label: 'Avvio sessione', data: CHART_DATA.session_start_marker,
                 backgroundColor: '#3ecf8e', pointStyle: 'triangle', pointRadius: 7, showLine: false }},
              {{ type: 'scatter', label: 'Crash', data: CHART_DATA.crash_marker,
                 backgroundColor: '#f25767', pointStyle: 'crossRot', pointRadius: 8, showLine: false }},
            ],
          }},
          options: {{
            responsive: true,
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{ legend: {{ labels: {{ color: '#e6e8ec' }} }} }},
            scales: {{
              x: {{ ticks: {{ color: '#9aa1ad', maxTicksLimit: 16 }}, grid: {{ color: '#2a2e38' }} }},
              y: {{ ticks: {{ color: '#9aa1ad' }}, grid: {{ color: '#2a2e38' }}, title: {{ display: true, text: 'MB', color: '#9aa1ad' }} }},
            }},
          }},
        }});
        new Chart(document.getElementById('chartThreads'), {{
          type: 'line',
          data: {{
            labels: CHART_DATA.labels,
            datasets: [
              {{ label: 'Thread attivi', data: CHART_DATA.threads, borderColor: '#f5a623', pointRadius: 1, tension: 0.15 }},
              {{ label: 'Download attivi', data: CHART_DATA.download_attivi, borderColor: '#4f8cff', pointRadius: 1, tension: 0.15 }},
              {{ label: 'Pool vivi', data: CHART_DATA.pool_vivi, borderColor: '#3ecf8e', pointRadius: 1, tension: 0.15 }},
            ],
          }},
          options: {{
            responsive: true,
            plugins: {{ legend: {{ labels: {{ color: '#e6e8ec' }} }} }},
            scales: {{
              x: {{ ticks: {{ color: '#9aa1ad', maxTicksLimit: 16 }}, grid: {{ color: '#2a2e38' }} }},
              y: {{ ticks: {{ color: '#9aa1ad' }}, grid: {{ color: '#2a2e38' }} }},
            }},
          }},
        }});
      }} catch (e) {{
        const fb = document.getElementById('fallbackMem');
        if (fb) fb.classList.add('shown');
      }}
    }}
    buildCharts();
    </script>
    """ if has_heartbeats else ""

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Report diagnostico — Mega Downloader Proxy Rotator</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Report diagnostico</h1>
<div class="subtitle">Generato il {html.escape(generated_at)} da tools/report.py — solo lettura, nessun log modificato.</div>

{cards_html}

<h2>Sessioni</h2>
{sessions_table}

<h2>Andamento nel tempo</h2>
{charts_section}

<h2>Errori e anomalie</h2>
{errors_html}

<h2>Download</h2>
{downloads_table}

<h2>Crash nativi (crash.log)</h2>
{crashes_html}

<footer>Mega Downloader Proxy Rotator (MDPR) — report diagnostico generato localmente, non contiene dati di rete.</footer>
<script src="{_CHARTJS_CDN}" onerror="document.getElementById('fallbackMem') && document.getElementById('fallbackMem').classList.add('shown')"></script>
{script}
</body>
</html>
"""


# === CLI ======================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report",
        description="Genera un report HTML diagnostico da logs/events.jsonl + logs/crash.log (sola lettura).",
    )
    parser.add_argument(
        "--logs", type=Path, default=LOGS_DIR,
        help="Cartella contenente events.jsonl* e crash.log (default: logs/ del progetto).",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Path del report HTML da generare (default: logs/reports/report_<timestamp>.html).",
    )
    args = parser.parse_args(argv)

    logs_dir: Path = args.logs
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path: Path = args.out if args.out is not None else REPORTS_DIR / f"report_{timestamp}.html"

    malformed_counter = [0]
    records = stream_records(find_events_log_files(logs_dir), malformed_counter)
    sessions, orphan_errors, orphan_downloads = build_sessions(records)

    crash_text = read_text_safe(logs_dir / "crash.log")
    crash_entries = parse_crash_log(crash_text)
    unattributed = attribute_crashes(sessions, crash_entries)

    generated_at = datetime.now().isoformat(timespec="seconds")
    report = render_html(
        sessions, orphan_errors, orphan_downloads, unattributed,
        malformed_counter[0], generated_at,
    )

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        print(f"Errore: impossibile scrivere il report in {out_path}: {exc}", file=sys.stderr)
        return 1

    n_sessions = len(sessions)
    n_anomale = sum(1 for s in sessions if s.outcome != "CLEAN")
    n_errors = sum(len(s.errors) for s in sessions) + len(orphan_errors)
    n_native = sum(1 for c in crash_entries if c.kind == "NATIVE")
    print(f"Report scritto in: {out_path}")
    print(
        f"Sessioni: {n_sessions} | chiusure anomale: {n_anomale} | "
        f"errori/warning: {n_errors} | voci crash.log: {len(crash_entries)} "
        f"(di cui {n_native} crash nativi) | righe malformate: {malformed_counter[0]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
