"""Analizzatore di sola lettura dei log di diagnostica: ricompone app.log* +
crash.log in un report HTML autonomo (grafici, tabella sessioni, eccezioni).

Non modifica ne' ruota i log: li legge soltanto. Nessuna dipendenza esterna
(solo stdlib); il report usa Chart.js da CDN con fallback tabellare se offline.

Uso:
    python -m tools.analyze_crashlog
    python -m tools.analyze_crashlog --logs <cartella> --out crash_report.html

Formati attesi (vedi src/core/logging_setup.py e src/core/diagnostics.py,
DEVONO restare allineati a questo parser):
    app.log:   "%H:%M:%S [LEVELNAME] ThreadName logger.name: messaggio"
               (formatter di logging_setup.py: niente data, solo ora).
               Righe notevoli: "SESSION START vX.Y.Z pid=<pid>",
               "SESSION CLEAN EXIT", "HEARTBEAT mem_rss=... threads=...
               download_attivi=... pool_vivi=...", blocchi ERROR/CRITICAL
               seguiti da un traceback Python "grezzo" (senza prefisso di
               formattazione) fino alla riga successiva nel formato sopra.
    crash.log: dump nativi di faulthandler ("Fatal Python error: ..." senza
               timestamp) intervallati da voci scritte dall'app stessa con
               timestamp ISO: "<iso> [THREAD-EXC] ..." / "<iso> [QT-FATAL] ...".
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOG_LINE_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2}) \[(?P<level>[A-Z]+)\] (?P<thread>\S+) (?P<logger>\S+): (?P<msg>.*)$"
)
HEARTBEAT_RE = re.compile(
    r"^HEARTBEAT mem_rss=(?P<mem>[\d.]+|n/d) threads=(?P<threads>\d+) "
    r"download_attivi=(?P<dl>\d+) pool_vivi=(?P<pool>\d+)$"
)
SESSION_START_RE = re.compile(r"^SESSION START v(?P<version>\S+) pid=(?P<pid>\d+)$")
SESSION_CLEAN_EXIT_MSG = "SESSION CLEAN EXIT"
FILE_ID_RE = re.compile(r"\[file (?P<file_id>\d+)\]")

# Voci di crash.log scritte dall'app (timestamp ISO completo, vedi
# logging_setup._write_crash_log). I dump nativi di faulthandler invece NON
# hanno timestamp: iniziano con "Fatal Python error: ...".
CRASH_ENTRY_START_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) \[(?P<kind>THREAD-EXC|QT-FATAL)\]\s?(?P<rest>.*)$"
)
NATIVE_FAULT_START_RE = re.compile(r"^Fatal Python error:")

ERROR_LEVELS = {"ERROR", "CRITICAL"}


# === Modello dati =========================================================

@dataclass
class Heartbeat:
    line_idx: int
    time: str | None
    mem_rss_mb: float | None
    threads: int
    download_attivi: int
    pool_vivi: int


@dataclass
class ExceptionEntry:
    line_idx: int
    time: str | None
    level: str
    thread: str
    logger: str
    message: str
    file_id: int | None
    traceback: str


@dataclass
class CrashEntry:
    kind: str  # "THREAD-EXC" | "QT-FATAL" | "NATIVE"
    timestamp: str | None  # ISO completo, solo per THREAD-EXC/QT-FATAL
    text: str


@dataclass
class Session:
    start_idx: int
    start_time: str | None
    version: str | None
    pid: int | None
    end_idx: int | None = None
    end_time: str | None = None
    clean_exit: bool = False
    heartbeats: list[Heartbeat] = field(default_factory=list)
    exceptions: list[ExceptionEntry] = field(default_factory=list)
    crashes: list[CrashEntry] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        """CLEAN / NATIVA / ANOMALA — le sole 3 classi mostrate in tabella.
        La distinzione piu' fine (eccezione vs causa esterna) vive solo nel
        verdetto euristico, non nella colonna esito."""
        if self.clean_exit:
            return "CLEAN"
        if self.crashes:
            return "NATIVA"
        return "ANOMALA"

    @property
    def effective_end_time(self) -> str | None:
        if self.end_time:
            return self.end_time
        if self.heartbeats:
            return self.heartbeats[-1].time
        return self.start_time

    @property
    def mem_peak(self) -> float | None:
        vals = [h.mem_rss_mb for h in self.heartbeats if h.mem_rss_mb is not None]
        return max(vals) if vals else None


# === Lettura file ==========================================================

def find_app_log_files(logs_dir: Path) -> list[Path]:
    """File app.log* in ordine CRONOLOGICO (dal piu' vecchio al piu' recente).

    RotatingFileHandler numera i backup al CONTRARIO: app.log.3 e' il piu'
    vecchio, app.log.1 il piu' recente fra i ruotati, app.log e' quello
    corrente (il piu' recente di tutti). File assenti vengono saltati senza
    errori.
    """
    files: list[Path] = []
    for suffix in (3, 2, 1):
        p = logs_dir / f"app.log.{suffix}"
        if p.exists():
            files.append(p)
    current = logs_dir / "app.log"
    if current.exists():
        files.append(current)
    return files


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# === Parsing app.log ========================================================

def parse_app_log(lines: list[str]) -> tuple[list[Session], list[ExceptionEntry]]:
    """Ritorna (sessioni, eccezioni orfane senza una sessione aperta).

    Scansione sequenziale a singolo passaggio: l'ordine delle righe nel file
    e' l'unica fonte di "tempo relativo" disponibile (il formatter non
    include la data, solo l'ora — vedi logging_setup.py).
    """
    sessions: list[Session] = []
    orphan_exceptions: list[ExceptionEntry] = []
    current: Session | None = None
    pending_exc: ExceptionEntry | None = None
    pending_tb_lines: list[str] = []

    def _finalize_pending() -> None:
        nonlocal pending_exc, pending_tb_lines
        if pending_exc is not None:
            pending_exc.traceback = "\n".join(pending_tb_lines).strip()
        pending_exc = None
        pending_tb_lines = []

    for idx, line in enumerate(lines):
        m = LOG_LINE_RE.match(line)
        if m is None:
            # Riga di continuazione: traceback "grezzo" appeso da logging
            # quando si passa exc_info (niente prefisso di formattazione).
            if pending_exc is not None:
                pending_tb_lines.append(line)
            continue

        _finalize_pending()

        time_, level, thread, logger_, msg = (
            m.group("time"), m.group("level"), m.group("thread"),
            m.group("logger"), m.group("msg"),
        )

        if msg == SESSION_CLEAN_EXIT_MSG:
            if current is not None:
                current.end_idx = idx
                current.end_time = time_
                current.clean_exit = True
                sessions.append(current)
                current = None
            continue

        sm = SESSION_START_RE.match(msg)
        if sm:
            if current is not None:
                # Sessione precedente senza CLEAN EXIT prima del nuovo START:
                # chiusura anomala, la finalizziamo qui.
                current.end_idx = idx - 1
                sessions.append(current)
            current = Session(
                start_idx=idx, start_time=time_,
                version=sm.group("version"), pid=int(sm.group("pid")),
            )
            continue

        hb = HEARTBEAT_RE.match(msg)
        if hb:
            if current is not None:
                mem_raw = hb.group("mem")
                mem_val = None if mem_raw == "n/d" else float(mem_raw)
                current.heartbeats.append(Heartbeat(
                    line_idx=idx, time=time_, mem_rss_mb=mem_val,
                    threads=int(hb.group("threads")),
                    download_attivi=int(hb.group("dl")),
                    pool_vivi=int(hb.group("pool")),
                ))
            continue

        if level in ERROR_LEVELS:
            fm = FILE_ID_RE.search(msg)
            entry = ExceptionEntry(
                line_idx=idx, time=time_, level=level, thread=thread,
                logger=logger_, message=msg,
                file_id=int(fm.group("file_id")) if fm else None,
                traceback="",
            )
            pending_exc = entry
            pending_tb_lines = []
            if current is not None:
                current.exceptions.append(entry)
            else:
                orphan_exceptions.append(entry)
            continue

    _finalize_pending()
    if current is not None:
        # File terminato senza CLEAN EXIT: chiusura anomala (o sessione
        # ancora in corso al momento dell'analisi).
        current.end_idx = len(lines) - 1
        sessions.append(current)

    return sessions, orphan_exceptions


# === Parsing crash.log =======================================================

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
                kind=current_kind, timestamp=current_ts,
                text="\n".join(body).strip(),
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
    """Associa ogni voce di crash.log alla sessione di app.log piu'
    plausibile. Euristica (niente data nei timestamp di app.log):
    - voci con timestamp ISO (THREAD-EXC/QT-FATAL): confronta la sola
      porzione HH:MM:SS con la finestra [start_time, end_time] di ciascuna
      sessione; se nessuna finestra combacia, ricade sulla sessione con lo
      start_time piu' recente non successivo all'evento, altrimenti
      sull'ultima sessione del log.
    - dump nativi (nessun timestamp): attribuiti all'ultima sessione senza
      CLEAN EXIT (un crash nativo termina il processo, quindi e' quasi
      sempre legato alla sessione piu' recente ancora "aperta").
    Ritorna le voci che non si sono potute attribuire a nessuna sessione.
    """
    unattributed: list[CrashEntry] = []
    for c in crashes:
        target: Session | None = None
        if c.timestamp:
            tod = c.timestamp[11:19]  # HH:MM:SS
            for s in sessions:
                end = s.effective_end_time
                if s.start_time and end and s.start_time <= tod <= end:
                    target = s
                    break
            if target is None:
                earlier = [s for s in sessions if s.start_time and s.start_time <= tod]
                target = earlier[-1] if earlier else (sessions[-1] if sessions else None)
        else:
            open_sessions = [s for s in sessions if not s.clean_exit]
            target = open_sessions[-1] if open_sessions else (sessions[-1] if sessions else None)
        if target is not None:
            target.crashes.append(c)
        else:
            unattributed.append(c)
    return unattributed


# === Verdetto euristico ======================================================

def _mem_trend(heartbeats: list[Heartbeat]) -> tuple[bool, float, float]:
    """True se la memoria cresce in modo ~monotono (>=70% dei passi non
    decrescenti) con una crescita totale >= 15%: indizio di leak/OOM."""
    vals = [h.mem_rss_mb for h in heartbeats if h.mem_rss_mb is not None]
    if len(vals) < 3:
        return False, 0.0, 0.0
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    nondecreasing_ratio = sum(1 for d in diffs if d >= 0) / len(diffs)
    growth_pct = ((vals[-1] - vals[0]) / vals[0] * 100) if vals[0] > 0 else 0.0
    growing = nondecreasing_ratio >= 0.7 and growth_pct >= 15
    return growing, vals[0], vals[-1]


def build_verdict(sessions: list[Session]) -> list[str]:
    anomale = [s for s in sessions if s.outcome != "CLEAN"]
    if not anomale:
        return ["Nessuna chiusura anomala rilevata: tutte le sessioni si sono "
                "chiuse correttamente (SESSION CLEAN EXIT)."]
    bullets: list[str] = []
    for s in anomale:
        label = f"Sessione avviata alle {s.start_time or '?'}"
        if s.outcome == "NATIVA":
            bullets.append(f"{label}: crash NATIVO rilevato in crash.log -> vedi dump sotto.")
            continue
        if s.exceptions:
            bullets.append(f"{label}: eccezione non gestita con traceback -> vedi sotto.")
            continue
        growing, first, last = _mem_trend(s.heartbeats)
        if growing:
            bullets.append(
                f"{label}: memoria in crescita quasi monotona prima della chiusura "
                f"({first:.0f}->{last:.0f} MB) -> sospetto OOM/leak."
            )
        else:
            bullets.append(
                f"{label}: nessuna eccezione ne' dump nativo associato -> probabile "
                "causa esterna (sleep/standby, riavvio, kill del processo dal sistema)."
            )
    return bullets


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
.verdict { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px; margin-bottom: 8px; }
.verdict ul { margin: 6px 0 0; padding-left: 20px; }
.verdict li { margin: 4px 0; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
th { color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.badge.clean { background: rgba(62,207,142,.15); color: var(--ok); }
.badge.anomala { background: rgba(245,166,35,.15); color: var(--warn); }
.badge.nativa { background: rgba(242,87,103,.15); color: var(--bad); }
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


def _badge(outcome: str) -> str:
    cls = {"CLEAN": "clean", "ANOMALA": "anomala", "NATIVA": "nativa"}.get(outcome, "anomala")
    return f'<span class="badge {cls}">{html.escape(outcome)}</span>'


def _fmt_duration(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "n/d"
    try:
        t0 = datetime.strptime(start, "%H:%M:%S")
        t1 = datetime.strptime(end, "%H:%M:%S")
    except ValueError:
        return "n/d"
    delta = t1 - t0
    if delta.total_seconds() < 0:
        # Rollover di mezzanotte: niente data disponibile per disambiguare,
        # assumiamo +1 giorno (unica ipotesi ragionevole con solo HH:MM:SS).
        delta += timedelta(days=1)
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
            labels.append(hb.time or f"#{cursor}")
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
        "labels": labels,
        "mem": mem,
        "threads": threads,
        "download_attivi": download_attivi,
        "pool_vivi": pool_vivi,
        "session_start_marker": session_start_marker,
        "crash_marker": crash_marker,
    }


def _render_exception_details(exc: ExceptionEntry) -> str:
    # Nessun suffisso "[file N]" ridondante: il numero, quando presente,
    # e' gia' incluso nel testo di exc.message dalla convenzione di logging
    # del worker. exc.file_id resta disponibile per usi futuri (es. ordinamento).
    summary = (
        f'<span class="meta">{html.escape(exc.time or "?")} [{html.escape(exc.level)}] '
        f'{html.escape(exc.logger)}</span>{html.escape(exc.message)}'
    )
    body = html.escape(exc.traceback) if exc.traceback else "(nessun traceback disponibile)"
    return f"<details><summary>{summary}</summary><pre>{body}</pre></details>"


def _render_crash_details(c: CrashEntry) -> str:
    ts = c.timestamp or "n/d (dump nativo, nessun timestamp)"
    summary = f'<span class="meta">{html.escape(ts)} [{html.escape(c.kind)}]</span>'
    return f"<details><summary>{summary}</summary><pre>{html.escape(c.text)}</pre></details>"


def render_html(
    sessions: list[Session],
    orphan_exceptions: list[ExceptionEntry],
    unattributed_crashes: list[CrashEntry],
    generated_at: str,
) -> str:
    n_sessions = len(sessions)
    n_anomale = sum(1 for s in sessions if s.outcome != "CLEAN")
    n_exceptions = sum(len(s.exceptions) for s in sessions) + len(orphan_exceptions)
    n_native = sum(1 for s in sessions for c in s.crashes if c.kind == "NATIVE") + sum(
        1 for c in unattributed_crashes if c.kind == "NATIVE"
    )
    ultima_esito = sessions[-1].outcome if sessions else "n/d"
    mem_peak = None
    for s in sessions:
        p = s.mem_peak
        if p is not None and (mem_peak is None or p > mem_peak):
            mem_peak = p

    verdict_lines = build_verdict(sessions)

    cards_html = f"""
    <div class="cards">
      <div class="card"><div class="label">Sessioni</div><div class="value">{n_sessions}</div></div>
      <div class="card"><div class="label">Chiusure anomale</div><div class="value">{n_anomale}</div></div>
      <div class="card"><div class="label">Eccezioni</div><div class="value">{n_exceptions}</div></div>
      <div class="card"><div class="label">Crash nativi</div><div class="value">{n_native}</div></div>
      <div class="card"><div class="label">Esito ultima sessione</div><div class="value">{_badge(ultima_esito)}</div></div>
      <div class="card"><div class="label">Picco mem_rss</div><div class="value">{f"{mem_peak:.0f} MB" if mem_peak is not None else "n/d"}</div></div>
    </div>
    """

    verdict_html = "<div class=\"verdict\"><ul>" + "".join(
        f"<li>{html.escape(line)}</li>" for line in verdict_lines
    ) + "</ul></div>"

    rows = []
    for s in sessions:
        rows.append(
            "<tr>"
            f"<td>{html.escape(s.start_time or '?')}</td>"
            f"<td>{html.escape(s.effective_end_time or '?')}</td>"
            f"<td>{_fmt_duration(s.start_time, s.effective_end_time)}</td>"
            f"<td>{_badge(s.outcome)}</td>"
            f"<td>{f'{s.mem_peak:.0f} MB' if s.mem_peak is not None else 'n/d'}</td>"
            "</tr>"
        )
    sessions_table = (
        "<table><thead><tr><th>Inizio</th><th>Fine</th><th>Durata</th>"
        "<th>Esito</th><th>Mem max</th></tr></thead><tbody>"
        + ("".join(rows) if rows else '<tr><td colspan="5" class="empty">Nessuna sessione trovata.</td></tr>')
        + "</tbody></table>"
    )

    all_exceptions = [exc for s in sessions for exc in s.exceptions] + orphan_exceptions
    exceptions_html = (
        "".join(_render_exception_details(e) for e in all_exceptions)
        if all_exceptions else '<div class="empty">Nessuna eccezione trovata.</div>'
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
            <thead><tr><th>Ora</th><th>mem_rss (MB)</th><th>Thread</th><th>Download attivi</th><th>Pool vivi</th></tr></thead>
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
<title>Crash report — Mega Downloader Proxy Rotator</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Crash report diagnostico</h1>
<div class="subtitle">Generato il {html.escape(generated_at)} da tools/analyze_crashlog.py — solo lettura, nessun log modificato.</div>

<h2>Verdetto euristico</h2>
{verdict_html}

{cards_html}

<h2>Sessioni</h2>
{sessions_table}

<h2>Andamento nel tempo</h2>
{charts_section}

<h2>Eccezioni (app.log)</h2>
{exceptions_html}

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
        prog="analyze_crashlog",
        description="Analizza app.log/crash.log e genera un report HTML diagnostico (sola lettura).",
    )
    parser.add_argument(
        "--logs", type=Path, default=_PROJECT_ROOT,
        help="Cartella contenente app.log* e crash.log (default: root del progetto).",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Path del report HTML da generare (default: <logs>/crash_report.html).",
    )
    args = parser.parse_args(argv)

    logs_dir: Path = args.logs
    out_path: Path = args.out if args.out is not None else logs_dir / "crash_report.html"

    all_lines: list[str] = []
    for p in find_app_log_files(logs_dir):
        all_lines.extend(read_text_safe(p).splitlines())

    sessions, orphan_exceptions = parse_app_log(all_lines)

    crash_text = read_text_safe(logs_dir / "crash.log")
    crash_entries = parse_crash_log(crash_text)
    unattributed = attribute_crashes(sessions, crash_entries)

    generated_at = datetime.now().isoformat(timespec="seconds")
    report = render_html(sessions, orphan_exceptions, unattributed, generated_at)

    try:
        out_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        print(f"Errore: impossibile scrivere il report in {out_path}: {exc}", file=sys.stderr)
        return 1

    n_sessions = len(sessions)
    n_anomale = sum(1 for s in sessions if s.outcome != "CLEAN")
    n_exceptions = sum(len(s.exceptions) for s in sessions) + len(orphan_exceptions)
    n_native = sum(1 for c in crash_entries if c.kind == "NATIVE")
    print(f"Report scritto in: {out_path}")
    print(
        f"Sessioni: {n_sessions} | chiusure anomale: {n_anomale} | "
        f"eccezioni: {n_exceptions} | voci crash.log: {len(crash_entries)} "
        f"(di cui {n_native} crash nativi)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
