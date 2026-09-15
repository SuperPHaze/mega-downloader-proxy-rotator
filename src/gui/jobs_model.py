# Modello dei job di download.
# Un job = un link. Lo stato (in_coda/in_corso/completato/fallito/annullato)
# e le metriche (progress, tentativi, IP corrente, ecc.) sono tenute qui; a
# disegnarle e' `JobsPanel`, che legge il modello con `get_job()`.
#
# i18n: questo modulo NON formatta testo. La cronologia e l'ultimo errore
# vivono come CHIAVE + parametri (`job_log.*` e il payload codice/parametri di
# E1) e vengono resi da chi disegna, nella lingua del momento. E' il motivo per
# cui non ha (ne' deve avere) un `retranslate()`: non c'e' niente di gia'
# formattato da riscrivere.
#
# Non e' piu' un QAbstractTableModel: la view a tabella e' sparita col
# restyling 1.3.0 e da allora `data()`/`headerData()`/`HEADERS` non avevano
# piu' un chiamante — erano testo utente solo all'apparenza. Restano i due
# segnali che la GUI usa davvero, `job_updated` e `aggregates_changed`.
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator

from PyQt6.QtCore import QObject, pyqtSignal


# Stati possibili (stringhe per facilita' di display e serializzazione).
STATUS_QUEUED = "in_coda"
STATUS_RUNNING = "in_corso"
STATUS_COMPLETED = "completato"
STATUS_FAILED = "fallito"
STATUS_CANCELLED = "annullato"
STATUS_ABANDONED = "abbandonato"


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
    # Ultimo errore come PAYLOAD (codice, parametri), non come frase: e' quello
    # che permette di renderlo in italiano o in inglese al momento del disegno.
    # None finche' non c'e' stato un errore.
    last_error: tuple[str, dict] | None = None
    ips_history: list[tuple[float, str]] = field(default_factory=list)
    # Log dettagliato dei tentativi (timestamp, livello, chiave, parametri).
    # Capped a 500 entries per job per evitare crescita illimitata su sessioni
    # lunghe. Il livello (INFO/WARN/ERROR) NON si traduce: e' diagnostico.
    all_attempts_log: list[tuple[float, str, str, dict]] = field(default_factory=list)
    # Dati throughput per il cruscotto KPI.
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0          # byte/s istantanei
    # Nome file risolto a download completato (vuoto finche' non arriva completed_info).
    file_name: str = ""
    # Path di output (cartella del job).
    output_path: str = ""
    # Velocita' media finale, congelata al passaggio in stato terminale.
    # None finche' il job non e' terminato o se la durata e' 0.
    average_bps_final: float | None = None

    def duration_s(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at if self.completed_at is not None else time.time()
        return max(0.0, end - self.started_at)

    def append_log(self, level: str, key: str, **params: object) -> None:
        self.all_attempts_log.append((time.time(), level, key, params))
        if len(self.all_attempts_log) > 500:
            # Trim mantenendo le piu' recenti.
            del self.all_attempts_log[:-500]


class JobsModel(QObject):
    # Segnale ad alto livello: un job specifico e' cambiato. I dialog di
    # dettaglio si registrano qui per refresh in real-time.
    job_updated = pyqtSignal(int)  # file_id
    # Stato aggregato cambiato (per StatsBar).
    aggregates_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._jobs: list[Job] = []
        self._by_id: dict[int, int] = {}  # file_id -> row index

    # ----- API pubblica per gli slot della GUI -----
    def reset(self, links: list[str]) -> None:
        self._jobs = [Job(file_id=i, url=u) for i, u in enumerate(links)]
        self._by_id = {j.file_id: i for i, j in enumerate(self._jobs)}
        self.aggregates_changed.emit()

    def append_jobs(self, jobs: list[tuple[int, str]]) -> list[int]:
        """ACCODA job a quelli esistenti (aggiunta a caldo), senza toccare le
        righe gia' presenti ne' i loro dati. Ritorna gli identificativi
        effettivamente aggiunti.

        Gli identificativi arrivano dall'orchestrator, che e' l'unico ad
        assegnarli: qui non si rinumera nulla. Un identificativo gia' noto
        viene ignorato — riusarlo sovrascriverebbe la storia di un job vivo.
        """
        added: list[int] = []
        for file_id, url in jobs:
            if file_id in self._by_id:
                continue
            self._jobs.append(Job(file_id=file_id, url=url))
            self._by_id[file_id] = len(self._jobs) - 1
            added.append(file_id)
        if added:
            self.aggregates_changed.emit()
        return added

    def _notify(self, file_id: int) -> None:
        if file_id not in self._by_id:
            return
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
            job.append_log("INFO", "job_log.started")
            self._notify(file_id)
            self.aggregates_changed.emit()
        job.progress = new_pct
        self._notify(file_id)

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
        job.append_log("INFO", "job_log.ip", ip=ip)
        self._notify(file_id)

    def add_failure(self, file_id: int, code: str, params: dict | None = None) -> None:
        """Un TENTATIVO fallito. `code`/`params` sono il payload di E1.

        `last_error` conserva la cornice «Tentativo N: » perche' e' cosi' che
        la card la mostrava prima della traduzione: il payload della cornice
        (`attempt_frame`) porta dentro di se' quello del motivo vero.

        Il numero e' `job.attempts`, cumulativo sul job. Il canale tipato non
        trasporta il contatore per-ciclo del worker (che riparte da 1 a ogni
        ciclo), quindi con `DOWNLOAD_CYCLES > 1` la numerazione diventerebbe
        quella cumulativa. Con `DOWNLOAD_CYCLES = 1`, che e' la configurazione
        in uso, i due contatori coincidono sempre.
        """
        job = self._job(file_id)
        if job is None:
            return
        job.attempts += 1
        job.errors_count += 1
        payload = {"code": code, "params": dict(params or {})}
        job.last_error = ("attempt_frame", {"n": job.attempts, "reason": payload})
        job.append_log("WARN", "job_log.attempt", attempt=job.attempts, error=payload)
        self._notify(file_id)

    def _freeze_average(self, job: Job) -> None:
        dur = job.duration_s()
        if dur > 0 and job.downloaded_bytes > 0:
            job.average_bps_final = job.downloaded_bytes / dur
        else:
            job.average_bps_final = None

    def mark_completed(self, file_id: int) -> None:
        job = self._job(file_id)
        if job is None:
            return
        job.status = STATUS_COMPLETED
        job.progress = 100
        job.completed_at = time.time()
        job.append_log("INFO", "job_log.completed")
        self._freeze_average(job)
        self._notify(file_id)
        self.aggregates_changed.emit()

    def mark_failed_fatal(
        self, file_id: int, code: str, params: dict | None = None,
    ) -> None:
        job = self._job(file_id)
        if job is None:
            return
        payload = {"code": code, "params": dict(params or {})}
        job.status = STATUS_FAILED
        job.last_error = (code, payload["params"])
        job.completed_at = time.time()
        job.append_log("ERROR", "job_log.fatal", error=payload)
        self._freeze_average(job)
        self._notify(file_id)
        self.aggregates_changed.emit()

    def mark_abandoned(
        self, file_id: int, attempts: int, code: str, params: dict | None = None,
    ) -> None:
        """Link abbandonato. `code` e' gia' quello dell'ABBANDONO (la
        formulazione coi due punti): l'alias lo applica `JobsPanel` al confine
        col segnale, che e' l'unico punto che sa da quale canale arriva."""
        job = self._job(file_id)
        if job is None:
            return
        payload = {"code": code, "params": dict(params or {})}
        job.status = STATUS_ABANDONED
        job.attempts = max(job.attempts, attempts)
        job.last_error = (code, payload["params"])
        job.completed_at = time.time()
        job.append_log(
            "ERROR", "job_log.abandoned", n=attempts, error=payload,
        )
        self._freeze_average(job)
        self._notify(file_id)
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
        job.append_log("WARN", "job_log.cancelled")
        self._freeze_average(job)
        self._notify(file_id)
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
                self._freeze_average(job)
                self._notify(job.file_id)
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
        job.last_error = None
        job.started_at = None
        job.completed_at = None
        job.speed = 0.0
        job.downloaded_bytes = 0
        job.total_bytes = 0
        job.average_bps_final = None
        job.append_log("INFO", "job_log.restart")
        self._notify(file_id)
        self.aggregates_changed.emit()
        return True

    def restartable_count(self) -> int:
        return sum(1 for j in self._jobs if j.status in self._RESTARTABLE)

    def iter_restartable(self) -> Iterator[Job]:
        return (j for j in self._jobs if j.status in self._RESTARTABLE)

    # ----- Aggregati per StatsBar e StatsPanel -----
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
            "total_downloaded_bytes": 0,
            "terminated_count": 0,
            "all_terminated": False,
            "arithmetic_avg_bps": None,
        }
        avg_bps_list: list[float] = []
        for j in self._jobs:
            agg["total_downloaded_bytes"] += j.downloaded_bytes
            if j.status == STATUS_QUEUED:
                agg["queued"] += 1
            elif j.status == STATUS_RUNNING:
                agg["running"] += 1
                agg["total_speed"] += j.speed
                if j.total_bytes > 0:
                    agg["total_remaining_bytes"] += max(0, j.total_bytes - j.downloaded_bytes)
            elif j.status == STATUS_COMPLETED:
                agg["completed"] += 1
                agg["terminated_count"] += 1
                if j.average_bps_final is not None:
                    avg_bps_list.append(j.average_bps_final)
            elif j.status == STATUS_FAILED:
                agg["failed"] += 1
                agg["terminated_count"] += 1
                if j.average_bps_final is not None:
                    avg_bps_list.append(j.average_bps_final)
            elif j.status == STATUS_CANCELLED:
                agg["cancelled"] += 1
                agg["terminated_count"] += 1
                if j.average_bps_final is not None:
                    avg_bps_list.append(j.average_bps_final)
            elif j.status == STATUS_ABANDONED:
                agg["abandoned"] += 1
                agg["terminated_count"] += 1
                if j.average_bps_final is not None:
                    avg_bps_list.append(j.average_bps_final)
        total = agg["total"]
        terminated = agg["terminated_count"]
        agg["all_terminated"] = total > 0 and terminated == total
        if avg_bps_list:
            agg["arithmetic_avg_bps"] = sum(avg_bps_list) / len(avg_bps_list)
        return agg
