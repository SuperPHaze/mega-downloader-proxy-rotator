# Modello per la tabella dei job di download.
# Un job = un link. Lo stato (in_coda/in_corso/completato/fallito/annullato)
# e le metriche (progress, tentativi, IP corrente, ecc.) sono tenute qui;
# la View li legge tramite data(role=DisplayRole) e i delegate li dipingono.
#
# Performance: dataChanged emesso col range minimo (solo le colonne effettivamente
# modificate). Niente layoutChanged/reset durante gli update — usati solo a reset
# totale a inizio sessione.
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    pyqtSignal,
)


# Stati possibili (stringhe per facilita' di display e serializzazione).
STATUS_QUEUED = "in_coda"
STATUS_RUNNING = "in_corso"
STATUS_COMPLETED = "completato"
STATUS_FAILED = "fallito"
STATUS_CANCELLED = "annullato"
STATUS_ABANDONED = "abbandonato"

# Colonne.
COL_ACTION = 0
COL_NUM = 1
COL_STATUS = 2
COL_URL = 3
COL_PROGRESS = 4
COL_IP = 5
COL_ATTEMPTS = 6
COL_DURATION = 7
N_COLUMNS = 8

HEADERS = ["", "#", "Stato", "Link", "Avanzamento", "IP corrente", "Tentativi", "Durata"]


@dataclass
class Job:
    file_id: int
    url: str
    status: str = STATUS_QUEUED
    progress: int = 0
    current_ip: str = ""
    attempts: int = 0
    errors_count: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    last_error: str = ""
    ips_history: list[tuple[float, str]] = field(default_factory=list)
    # Log dettagliato dei tentativi (timestamp, livello, msg). Capped a 500
    # entries per job per evitare crescita illimitata su sessioni lunghe.
    all_attempts_log: list[tuple[float, str, str]] = field(default_factory=list)
    # Dati throughput per il cruscotto KPI.
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0          # byte/s istantanei
    # Nome file risolto a download completato (vuoto finche' non arriva completed_info).
    file_name: str = ""
    # Path di output (cartella del job).
    output_path: str = ""

    def duration_s(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at if self.completed_at is not None else time.time()
        return max(0.0, end - self.started_at)

    def append_log(self, level: str, msg: str) -> None:
        self.all_attempts_log.append((time.time(), level, msg))
        if len(self.all_attempts_log) > 500:
            # Trim mantenendo le piu' recenti.
            del self.all_attempts_log[:-500]


def _fmt_mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


class JobsModel(QAbstractTableModel):
    # Segnale ad alto livello: un job specifico e' cambiato. I dialog di
    # dettaglio si registrano qui per refresh in real-time.
    job_updated = pyqtSignal(int)  # file_id
    # Stato aggregato cambiato (per StatsBar).
    aggregates_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._jobs: list[Job] = []
        self._by_id: dict[int, int] = {}  # file_id -> row index

    # ----- API Qt obbligatoria -----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._jobs)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return N_COLUMNS

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < N_COLUMNS:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._jobs):
            return None
        job = self._jobs[row]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_ACTION:
                # Il delegate disegna la X; il valore qui serve solo per
                # selezione / filtro (non usato).
                return ""
            if col == COL_NUM:
                return job.file_id + 1
            if col == COL_STATUS:
                return job.status
            if col == COL_URL:
                # Per i link abbandonati mostriamo SEMPRE l'URL completo:
                # l'utente deve poterlo copiare e riprovare manualmente.
                if job.status == STATUS_ABANDONED:
                    return job.url
                return job.url if len(job.url) <= 70 else job.url[:67] + "..."
            if col == COL_PROGRESS:
                return job.progress
            if col == COL_IP:
                return job.current_ip or "-"
            if col == COL_ATTEMPTS:
                return job.attempts
            if col == COL_DURATION:
                return _fmt_mmss(job.duration_s()) if job.started_at else "-"
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_URL:
                return job.url
            if col == COL_STATUS and job.last_error:
                return f"Ultimo errore: {job.last_error}"
            if col == COL_ACTION:
                if job.status in (STATUS_QUEUED, STATUS_RUNNING):
                    return "Annulla download ed elimina cartella"
                return "Elimina cartella su disco"
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (COL_ACTION, COL_NUM, COL_ATTEMPTS, COL_DURATION):
                return int(Qt.AlignmentFlag.AlignCenter)
        elif role == Qt.ItemDataRole.UserRole:
            # Accesso diretto al Job (utile a delegate e dialog).
            return job
        return None

    # ----- API pubblica per gli slot della GUI -----
    def reset(self, links: list[str]) -> None:
        self.beginResetModel()
        self._jobs = [Job(file_id=i, url=u) for i, u in enumerate(links)]
        self._by_id = {j.file_id: i for i, j in enumerate(self._jobs)}
        self.endResetModel()
        self.aggregates_changed.emit()

    def _emit_changed(self, file_id: int, cols: list[int]) -> None:
        row = self._by_id.get(file_id)
        if row is None:
            return
        if not cols:
            return
        top = min(cols)
        bot = max(cols)
        self.dataChanged.emit(
            self.index(row, top),
            self.index(row, bot),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
        )
        self.job_updated.emit(file_id)

    def _job(self, file_id: int) -> Job | None:
        row = self._by_id.get(file_id)
        if row is None:
            return None
        return self._jobs[row]

    def set_progress(self, file_id: int, percent: int) -> None:
        job = self._job(file_id)
        if job is None:
            return
        new_pct = max(0, min(100, int(percent)))
        if new_pct == job.progress and job.status == STATUS_RUNNING:
            return  # niente da segnalare
        if job.status == STATUS_QUEUED:
            job.status = STATUS_RUNNING
            job.started_at = time.time()
            job.append_log("INFO", "Download avviato")
            self._emit_changed(file_id, [COL_STATUS, COL_PROGRESS, COL_DURATION])
            self.aggregates_changed.emit()
        job.progress = new_pct
        self._emit_changed(file_id, [COL_PROGRESS, COL_DURATION])

    def set_ip(self, file_id: int, ip: str) -> None:
        job = self._job(file_id)
        if job is None or not ip:
            return
        if job.status == STATUS_QUEUED:
            job.status = STATUS_RUNNING
            job.started_at = time.time()
            self.aggregates_changed.emit()
        job.current_ip = ip
        job.ips_history.append((time.time(), ip))
        job.append_log("INFO", f"IP uscente: {ip}")
        self._emit_changed(file_id, [COL_STATUS, COL_IP])

    def add_failure(self, file_id: int, reason: str) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.attempts += 1
        job.errors_count += 1
        job.last_error = reason
        job.append_log("WARN", f"Tentativo {job.attempts}: {reason}")
        self._emit_changed(file_id, [COL_STATUS, COL_ATTEMPTS])

    def mark_completed(self, file_id: int) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.status = STATUS_COMPLETED
        job.progress = 100
        job.completed_at = time.time()
        job.append_log("INFO", "Download completato")
        self._emit_changed(file_id, [COL_STATUS, COL_PROGRESS, COL_DURATION])
        self.aggregates_changed.emit()

    def mark_failed_fatal(self, file_id: int, reason: str) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.status = STATUS_FAILED
        job.last_error = reason
        job.completed_at = time.time()
        job.append_log("ERROR", f"Errore fatale: {reason}")
        self._emit_changed(file_id, [COL_STATUS, COL_DURATION])
        self.aggregates_changed.emit()

    def mark_abandoned(self, file_id: int, attempts: int, last_error: str) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.status = STATUS_ABANDONED
        job.attempts = max(job.attempts, attempts)
        job.last_error = last_error
        job.completed_at = time.time()
        job.append_log("ERROR", f"Link abbandonato dopo {attempts} tentativi: {last_error}")
        self._emit_changed(file_id, [COL_STATUS, COL_ATTEMPTS, COL_DURATION])
        self.aggregates_changed.emit()

    def mark_cancelled(self, file_id: int) -> None:
        # Cancellazione di un singolo job (idempotente: i job gia' terminati
        # vengono ignorati per non sovrascrivere stati finali).
        job = self._job(file_id)
        if job is None:
            return
        if job.status not in (STATUS_QUEUED, STATUS_RUNNING):
            return
        job.status = STATUS_CANCELLED
        job.completed_at = time.time()
        job.append_log("WARN", "Cancellato dall'utente")
        self._emit_changed(file_id, [COL_STATUS, COL_DURATION])
        self.aggregates_changed.emit()

    def set_throughput(self, file_id: int, bps: float, downloaded: int, total: int) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.speed = max(0.0, float(bps))
        job.downloaded_bytes = int(downloaded)
        job.total_bytes = int(total)
        # Non emette dataChanged per ogni campione (0.5s) per non intasare il
        # modello: il widget-card legge direttamente dal Job a ogni refresh.
        self.job_updated.emit(file_id)
        self.aggregates_changed.emit()

    def set_file_info(self, file_id: int, file_name: str, output_path: str) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.file_name = file_name
        job.output_path = output_path
        self.job_updated.emit(file_id)

    def mark_cancelled_all(self) -> None:
        # Marca come "annullato" tutti i job non ancora terminati.
        changed = False
        for job in self._jobs:
            if job.status in (STATUS_QUEUED, STATUS_RUNNING):
                job.status = STATUS_CANCELLED
                job.completed_at = time.time()
                self._emit_changed(job.file_id, [COL_STATUS, COL_DURATION])
                changed = True
        if changed:
            self.aggregates_changed.emit()

    def get_job(self, file_id: int) -> Job | None:
        return self._job(file_id)

    def jobs_iter(self) -> Iterator[Job]:
        return iter(self._jobs)

    # ----- Riavvio job terminati -----
    # _total_attempts del nuovo worker parte da 0: max_attempts è cap per-sessione,
    # non cumulativo tra riavvii successivi.
    _RESTARTABLE = {STATUS_FAILED, STATUS_ABANDONED, STATUS_CANCELLED}

    def restart_job(self, file_id: int) -> bool:
        """Resetta un job riavviabile a STATUS_QUEUED. Ritorna False se non riavviabile."""
        job = self._job(file_id)
        if job is None or job.status not in self._RESTARTABLE:
            return False
        job.status = STATUS_QUEUED
        job.progress = 0
        job.attempts = 0
        job.errors_count = 0
        job.last_error = ""
        job.started_at = None
        job.completed_at = None
        job.speed = 0.0
        job.downloaded_bytes = 0
        job.total_bytes = 0
        job.append_log("INFO", "----- Riavvio richiesto -----")
        self._emit_changed(
            file_id,
            [COL_STATUS, COL_PROGRESS, COL_ATTEMPTS, COL_DURATION],
        )
        self.aggregates_changed.emit()
        return True

    def restartable_count(self) -> int:
        return sum(1 for j in self._jobs if j.status in self._RESTARTABLE)

    def iter_restartable(self) -> Iterator[Job]:
        return (j for j in self._jobs if j.status in self._RESTARTABLE)

    # ----- Aggregati per StatsBar -----
    def aggregates(self) -> dict:
        agg: dict = {
            "total": len(self._jobs),
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "abandoned": 0,
            "total_speed": 0.0,
            "total_remaining_bytes": 0,
        }
        for j in self._jobs:
            if j.status == STATUS_QUEUED:
                agg["queued"] += 1
            elif j.status == STATUS_RUNNING:
                agg["running"] += 1
                agg["total_speed"] += j.speed
                if j.total_bytes > 0:
                    agg["total_remaining_bytes"] += max(0, j.total_bytes - j.downloaded_bytes)
            elif j.status == STATUS_COMPLETED:
                agg["completed"] += 1
            elif j.status == STATUS_FAILED:
                agg["failed"] += 1
            elif j.status == STATUS_CANCELLED:
                agg["cancelled"] += 1
            elif j.status == STATUS_ABANDONED:
                agg["abandoned"] += 1
        return agg
