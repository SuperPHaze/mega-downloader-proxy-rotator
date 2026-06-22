# Coordina lo scraping/validazione proxy e l'avvio dei worker per ogni link.
# - Setup iniziale in QThread per non bloccare la GUI.
# - Pool con refill: quando si svuota, i worker chiamano pool.refill_blocking()
#   che invoca _refill_proxies() qui sotto (scrape+validate sincrono).
from __future__ import annotations

import logging
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from src.core.config import (
    MAX_CONCURRENT_DOWNLOADS,
    MAX_PROXIES_TO_VALIDATE,
    PARALLEL_CHUNK_SIZE_MB,
    PARALLEL_CONNECTIONS_PER_FILE,
    PROXY_CACHE_MIN_SCORE_FOR_PERSISTENCE,
    PROXY_CACHE_SAVE_INTERVAL_S,
    VALIDATOR_STAGE1_WORKERS,
)
from src.core.download_history import extract_handle, record_completed
from src.core.failed_log import log_failed_link
from src.core.sources_stats import log_validation_result
from src.core.state import SessionState
from src.downloader.worker import DownloadWorker
from src.proxy import proxy_cache
from src.proxy.pool import ProxyPool
from src.proxy.refresher import BackgroundPoolRefresher
from src.proxy.scraper import ProxyScraper
from src.proxy.validator import ProxyValidator

# Soglia minima di proxy revalidati dalla cache sotto la quale NON consideriamo
# l'hot-start riuscito: torniamo al flusso classico (scrape+validate completo).
# Sopra questa soglia il pool e' gia' usabile e lo scrape parte solo in background.
_HOT_START_MIN_ALIVE = 10

log = logging.getLogger(__name__)


def _log_per_source_survival(
    candidates: list[dict],
    stage1_alive: list[dict],
    stage2_alive: list[dict],
) -> None:
    # Aggrega per `_source` (tag inserito da ProxyScraper.fetch_all) e logga
    # un record `validation` per ogni fonte rappresentata nei candidati.
    by_source_total: dict[str, int] = {}
    by_source_s1: dict[str, int] = {}
    by_source_s2: dict[str, int] = {}
    for p in candidates:
        s = p.get("_source", "unknown")
        by_source_total[s] = by_source_total.get(s, 0) + 1
    for p in stage1_alive:
        s = p.get("_source", "unknown")
        by_source_s1[s] = by_source_s1.get(s, 0) + 1
    for p in stage2_alive:
        s = p.get("_source", "unknown")
        by_source_s2[s] = by_source_s2.get(s, 0) + 1
    for source_name, total in by_source_total.items():
        try:
            log_validation_result(
                source_name,
                survived_stage1=by_source_s1.get(source_name, 0),
                survived_stage2=by_source_s2.get(source_name, 0),
                total_from_source=total,
            )
        except Exception:
            log.debug("log_validation_result fallita per '%s'", source_name)


def _scrape_and_validate() -> list[dict]:
    # Helper riutilizzato sia dal setup iniziale sia dal refill del pool.
    scraper = ProxyScraper()
    candidates = scraper.fetch_all()
    if len(candidates) > MAX_PROXIES_TO_VALIDATE:
        log.info("Cap candidati a %d (su %d)", MAX_PROXIES_TO_VALIDATE, len(candidates))
        candidates = candidates[:MAX_PROXIES_TO_VALIDATE]
    validator = ProxyValidator()
    breakdown = validator.validate_against_mega(candidates, return_stage_breakdown=True)
    _log_per_source_survival(candidates, breakdown["stage1_alive"], breakdown["stage2_alive"])
    return breakdown["stage2_alive"]


class _SetupThread(QThread):
    finished_ok = pyqtSignal(list)
    # Emesso (insieme a finished_ok) quando il setup e' partito da cache:
    # l'orchestrator avvia il refresher con initial_force=True per uno scrape
    # di rinforzo in background.
    hot_started = pyqtSignal()
    failed = pyqtSignal(str)
    setup_progress = pyqtSignal(int, int, int)
    setup_status = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SetupThread")

    def run(self) -> None:
        try:
            # === Fase 0: tenta hot-start da cache. ===
            cached = proxy_cache.load()
            self.setup_status.emit(f"Cache proxy: {len(cached)} candidati...")
            hot_alive: list[dict] = []
            if cached:
                validator = ProxyValidator()
                hot_alive = validator._run_stage(
                    cached,
                    validator._check_alive,
                    VALIDATOR_STAGE1_WORKERS,
                    progress_callback=lambda d, t, a: self.setup_progress.emit(d, t, a),
                    stage_name="cache-revalidate",
                    target_alive=None,
                )
                log.info(
                    "Hot-start: %d/%d proxy cache revalidati",
                    len(hot_alive), len(cached),
                )

            if len(hot_alive) >= _HOT_START_MIN_ALIVE:
                self.setup_status.emit(
                    f"Hot-start: {len(hot_alive)} proxy pronti dalla cache"
                )
                self.finished_ok.emit(hot_alive)
                self.hot_started.emit()
                return

            # === Flusso classico: scrape completo + validazione 2-stage. ===
            self.setup_status.emit("Raccolta proxy dalle fonti pubbliche...")
            scraper = ProxyScraper()
            candidates = scraper.fetch_all()
            log.info("Setup: %d candidati totali", len(candidates))
            if not candidates and not hot_alive:
                self.failed.emit("Nessun proxy raccolto dalle fonti")
                return
            if len(candidates) > MAX_PROXIES_TO_VALIDATE:
                log.info("Setup: cap a %d (su %d)", MAX_PROXIES_TO_VALIDATE, len(candidates))
                candidates = candidates[:MAX_PROXIES_TO_VALIDATE]
            # Se l'hot-start ha portato qualcosa ma sotto soglia, usalo come seed
            # in testa ai candidati. Dedup (host, port).
            if hot_alive:
                seen = {(p["host"], p["port"]) for p in hot_alive}
                merged = list(hot_alive)
                for p in candidates:
                    key = (p["host"], p["port"])
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(p)
                candidates = merged
                log.info(
                    "Setup: %d candidati totali dopo merge cache+scrape", len(candidates),
                )
            self.setup_status.emit(f"Validazione di {len(candidates)} proxy contro Mega...")
            validator = ProxyValidator()
            breakdown = validator.validate_against_mega(
                candidates,
                progress_callback=lambda d, t, a: self.setup_progress.emit(d, t, a),
                return_stage_breakdown=True,
            )
            _log_per_source_survival(
                candidates, breakdown["stage1_alive"], breakdown["stage2_alive"],
            )
            alive = breakdown["stage2_alive"]
            log.info("Setup completato: %d proxy vivi", len(alive))
            self.finished_ok.emit(alive)
        except Exception as exc:
            log.exception("Setup proxy fallito")
            self.failed.emit(str(exc))


class DownloadOrchestrator(QObject):
    progress = pyqtSignal(int, int, int)
    ip_logged = pyqtSignal(int, int, str)
    cycle_completed = pyqtSignal(int, int)
    failed = pyqtSignal(int, int, str)
    fatal_error = pyqtSignal(int, str)
    all_done = pyqtSignal(int)

    pool_ready = pyqtSignal(int)
    pool_failed = pyqtSignal(str)
    setup_progress = pyqtSignal(int, int, int)
    setup_status = pyqtSignal(str)

    # Cancellazione per singolo job: la GUI lo usa per aggiornare il modello.
    job_cancelled = pyqtSignal(int)
    # Link abbandonato dopo MAX_ATTEMPTS_PER_FILE tentativi falliti.
    abandoned = pyqtSignal(int, str, int, str)  # (file_id, url, attempts, last_error)
    # Dimensione corrente del pool proxy vivi: emesso periodicamente
    # dal _pool_size_timer attivato in _on_setup_ok.
    pool_size_changed = pyqtSignal(int)
    # Throughput in tempo reale: relay dal worker. (file_id, bps, downloaded, total)
    throughput = pyqtSignal(int, float, object, object)
    # Relay del completed_info del worker: (file_id, url, file_name, file_size, path)
    completed_info = pyqtSignal(int, str, str, object, str)
    # Nome file risolto appena noto (non solo a fine download): (file_id, file_name, file_size, path)
    file_resolved = pyqtSignal(int, str, object, str)

    def __init__(self, session_state: SessionState) -> None:
        super().__init__()
        self.session_state = session_state
        # Il pool ha una callback per ri-eseguire scrape+validate quando si svuota.
        self.pool = ProxyPool(refill_fn=_scrape_and_validate)
        self._refresher = BackgroundPoolRefresher(self.pool, self.session_state)
        self._workers: list[DownloadWorker] = []
        self._setup: _SetupThread | None = None
        self._pending_links: list[str] = []
        # Coda dei link non ancora avviati, come (file_id, url).
        # Mantiene il file_id originale per coerenza con le righe del ProgressPanel.
        self._queue: list[tuple[int, str]] = []
        self._active_count = 0
        # Numero di download simultanei. La GUI puo' sovrascriverlo prima di
        # chiamare start(), oppure passarlo come parametro a start().
        self.max_concurrent: int = MAX_CONCURRENT_DOWNLOADS
        # Limite di durata wall-clock per-file (secondi). None = nessun limite.
        self.file_time_limit_s: int | None = None
        # Dimensione chunk per il parallel client (byte). None = usa default config.
        self.chunk_size_bytes: int | None = None
        # Connessioni per file (Leva A) e modalita' di selezione proxy (Leva B):
        # scheda Funzioni Sperimentali. None/"score" = comportamento storico.
        self.connections_per_file: int | None = None
        self.selection_mode: str = "score"
        # Timer che pubblica periodicamente la size del pool. Non attivato in
        # __init__/start(): viene avviato in _on_setup_ok dopo il primo
        # add_many, altrimenti emetterebbe 0 a ripetizione durante il setup.
        self._pool_size_timer = QTimer(self)
        self._pool_size_timer.setInterval(2000)
        self._pool_size_timer.timeout.connect(self._emit_pool_size)
        # Timer per il salvataggio periodico della cache proxy. Non parte
        # in __init__: viene avviato in _on_setup_ok una volta che il pool
        # ha del contenuto serializzabile. Fermato in _on_slot_freed.
        self._cache_save_timer = QTimer(self)
        self._cache_save_timer.setInterval(PROXY_CACHE_SAVE_INTERVAL_S * 1000)
        self._cache_save_timer.timeout.connect(self._persist_cache)
        # Serializza save concorrenti (timer vs shutdown vs cancel).
        self._cache_save_lock = threading.Lock()
        # Settato da shutdown(): impedisce a un _SetupThread ancora in volo di
        # avviare refresher/timer/worker su un orchestrator dismesso. Serve un
        # flag LOCALE perche' session_state e' condiviso e viene resettato
        # dalla sessione successiva (is_cancelled tornerebbe False).
        self._shutdown_requested = False
        # Hook di shutdown: persisti la cache prima che la QApplication esca.
        # Non serve modificare la GUI: aboutToQuit scatta per qualunque path
        # di chiusura (X sulla finestra, Ctrl+C, sys.exit). Connessione una
        # sola volta per istanza.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._persist_cache)

    def start(
        self,
        links: list[str],
        concurrency: int | None = None,
        file_time_limit_s: int | None = None,
        chunk_size_bytes: int | None = None,
        connections_per_file: int | None = None,
        selection_mode: str | None = None,
    ) -> None:
        if concurrency is not None:
            self.max_concurrent = max(1, int(concurrency))
        self.file_time_limit_s = file_time_limit_s
        self.chunk_size_bytes = chunk_size_bytes
        self.connections_per_file = connections_per_file
        self.selection_mode = selection_mode or "score"
        # Letti UNA volta all'avvio sessione (non a caldo): il pool condiviso
        # da tutti i worker adotta la modalita' di selezione e il K per il
        # ramo "throughput" prima che parta il primo download.
        self.pool.selection_mode = self.selection_mode
        if self.connections_per_file is not None:
            self.pool.n_connections = max(1, int(self.connections_per_file))
        # Riga CONFIG a inizio sessione (vedi rules/logging.md): correla
        # config attiva <-> eventuale crash nei log raccolti dagli utenti.
        connessioni = self.connections_per_file or PARALLEL_CONNECTIONS_PER_FILE
        chunk_mb = (
            self.chunk_size_bytes / (1024 * 1024)
            if self.chunk_size_bytes is not None
            else PARALLEL_CHUNK_SIZE_MB
        )
        log.info(
            "CONFIG connessioni=%d chunk_mb=%g selezione_velocita=%s "
            "file_paralleli=%d validator_stage1=%d",
            connessioni, chunk_mb,
            "on" if self.selection_mode == "throughput" else "off",
            self.max_concurrent, VALIDATOR_STAGE1_WORKERS,
        )
        log.info(
            "Orchestrator.start: %d link, max %d concorrenti",
            len(links), self.max_concurrent,
        )
        self.session_state.start()
        self._pending_links = list(links)
        self._setup = _SetupThread()
        self._hot_started = False
        self._setup.setup_status.connect(self.setup_status)
        self._setup.setup_progress.connect(self.setup_progress)
        self._setup.finished_ok.connect(self._on_setup_ok)
        self._setup.hot_started.connect(self._on_hot_started)
        self._setup.failed.connect(self._on_setup_failed)
        self._setup.start()

    def stop_background_tasks(self) -> None:
        # Ferma subito refresher e timer, senza aspettare _on_slot_freed.
        # Usato dalla GUI su Annulla e da shutdown(). Idempotente.
        self._refresher.stop()
        self._pool_size_timer.stop()
        self._cache_save_timer.stop()

    def shutdown(self, timeout_ms: int = 10_000) -> bool:
        """Teardown completo dell'orchestrator: da chiamare PRIMA di crearne
        uno nuovo o alla chiusura dell'app.

        Cancella la sessione se attiva, svuota la coda, chiede la
        cancellazione a tutti i worker vivi e li attende (wait bounded),
        ferma refresher/timer, persiste la cache e disconnette aboutToQuit.

        Ritorna False se un thread (worker o setup) non termina entro il
        timeout: in quel caso il chiamante DEVE conservare un riferimento a
        questo orchestrator (distruggerlo con QThread vivi = crash hard).
        """
        log.info("Orchestrator.shutdown richiesto")
        self._shutdown_requested = True
        if not self.session_state.is_cancelled():
            self.session_state.cancel()
        self._queue.clear()
        self._pending_links = []
        self.stop_background_tasks()
        for w in self._workers:
            if w.isRunning():
                w.request_cancel()
        all_stopped = True
        for w in self._workers:
            if w.isRunning() and not w.wait(timeout_ms):
                log.warning(
                    "shutdown: worker file_id=%d non terminato entro %dms",
                    w.file_id, timeout_ms,
                )
                all_stopped = False
        if self._setup is not None and self._setup.isRunning():
            if not self._setup.wait(timeout_ms):
                log.warning("shutdown: setup thread non terminato entro %dms", timeout_ms)
                all_stopped = False
        self._persist_cache()
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.disconnect(self._persist_cache)
            except TypeError:
                pass  # gia' disconnesso (shutdown ripetuto)
        log.info("Orchestrator.shutdown completato (all_stopped=%s)", all_stopped)
        return all_stopped

    def _on_hot_started(self) -> None:
        # Marcatore: il setup e' partito da cache. _on_setup_ok lo legge per
        # decidere se avviare il refresher con initial_force=True.
        self._hot_started = True

    def _on_setup_ok(self, alive: list) -> None:
        log.info("Orchestrator: setup ok, %d proxy vivi", len(alive))
        if self._shutdown_requested or self.session_state.is_cancelled():
            # Sessione cancellata/dismessa mentre il setup era in corso:
            # NON avviare refresher, timer e worker su una sessione morta.
            log.info("Orchestrator: setup completato su sessione morta, ignoro")
            return
        if not alive:
            self.pool_failed.emit("Nessun proxy valido per Mega")
            return
        self.pool.add_many(alive)
        self.pool_ready.emit(len(alive))
        # Emissione immediata + tick periodico della size del pool.
        self._emit_pool_size()
        self._pool_size_timer.start()
        # Cache save periodico: parte ora che il pool ha del contenuto.
        self._cache_save_timer.start()
        # Avvia il refresher in background: rimpiazza i proxy morti mentre i
        # worker scaricano, senza bloccare nessuno. Se siamo partiti da cache
        # (hot-start), forziamo un primo refill subito per rinforzare il pool
        # con uno scrape completo.
        self._refresher.start(initial_force=self._hot_started)
        self._spawn_workers()

    def _persist_cache(self) -> None:
        # Idempotente: se il pool e' vuoto (es. chiusura prima di setup ok)
        # non scrive nulla. Serializzato con un lock per coprire il caso
        # in cui timer periodico e aboutToQuit si sovrappongano.
        if not self._cache_save_lock.acquire(blocking=False):
            log.debug("Cache save gia' in corso, skip")
            return
        try:
            snapshot = self.pool.export_for_cache(
                min_score=PROXY_CACHE_MIN_SCORE_FOR_PERSISTENCE,
            )
            if not snapshot:
                log.debug("Cache save: pool vuoto, niente da scrivere")
                return
            now_iso = datetime.now().isoformat(timespec="seconds")
            for entry in snapshot:
                entry["last_seen"] = now_iso
            proxy_cache.save(snapshot)
        finally:
            self._cache_save_lock.release()

    def _emit_pool_size(self) -> None:
        try:
            n = self.pool.size()
        except Exception:
            n = 0
        self.pool_size_changed.emit(int(n))

    def _on_setup_failed(self, msg: str) -> None:
        log.error("Orchestrator: setup fallito: %s", msg)
        self.pool_failed.emit(msg)

    def _spawn_workers(self) -> None:
        # Riempi la coda con tutti i link e avvia solo i primi N.
        self._queue = list(enumerate(self._pending_links))
        self._active_count = 0
        log.info(
            "Coda: %d link, max %d concorrenti",
            len(self._queue),
            self.max_concurrent,
        )
        self._fill_slots()

    def _fill_slots(self) -> None:
        # Avvia worker finche' restano slot liberi e link in coda.
        while self._active_count < self.max_concurrent and self._queue:
            file_id, link = self._queue.pop(0)
            self._launch_worker(file_id, link)

    def _launch_worker(self, file_id: int, link: str) -> None:
        log.info(
            "Avvio worker file_id=%d url=%s (attivi=%d, in_coda=%d)",
            file_id,
            link,
            self._active_count + 1,
            len(self._queue),
        )
        worker = DownloadWorker(
            file_id, link, self.pool, self.session_state,
            file_time_limit_s=self.file_time_limit_s,
            chunk_size_bytes=self.chunk_size_bytes,
            connections_per_file=self.connections_per_file,
        )
        worker.setObjectName(f"Worker-{file_id}")
        worker.progress.connect(self.progress)
        worker.ip_logged.connect(self.ip_logged)
        worker.cycle_completed.connect(self.cycle_completed)
        worker.failed.connect(self.failed)
        worker.fatal_error.connect(self.fatal_error)
        worker.all_done.connect(self.all_done)
        worker.throughput.connect(self.throughput)
        worker.file_resolved.connect(self.file_resolved)
        worker.completed_info.connect(self._on_worker_completed)
        # Quando un worker termina (fine cicli o errore fatale) libera lo slot
        # e riempie con il prossimo della coda. Usiamo i segnali del worker
        # stesso anziche' QThread.finished per restare nel contratto pubblico.
        worker.all_done.connect(self._on_slot_freed)
        worker.fatal_error.connect(lambda _fid, _msg: self._on_slot_freed(_fid))
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.abandoned.connect(self._on_worker_abandoned)
        self._workers.append(worker)
        self._active_count += 1
        worker.start()

    def _on_slot_freed(self, file_id: int) -> None:
        self._active_count = max(0, self._active_count - 1)
        log.info(
            "Slot liberato da file_id=%d (attivi=%d, in_coda=%d)",
            file_id,
            self._active_count,
            len(self._queue),
        )
        if self.session_state.is_cancelled():
            self._refresher.stop()
            self._pool_size_timer.stop()
            self._cache_save_timer.stop()
            self._persist_cache()
            return
        if self._active_count == 0 and not self._queue:
            # Tutti i download finiti: spegni il refresher per non lasciare
            # un thread daemon a girare a vuoto.
            log.info("Tutti i download conclusi, fermo il refresher")
            self._refresher.stop()
            self._pool_size_timer.stop()
            self._cache_save_timer.stop()
            self._persist_cache()
            return
        self._fill_slots()

    def _on_worker_completed(
        self, file_id: int, url: str, file_name: str, file_size: object, path: str,
    ) -> None:
        # Relay alla GUI (per aggiornare nome file e path nel modello).
        self.completed_info.emit(file_id, url, file_name, file_size, path)
        # Persiste lo storico dei download completati: punto unico, come
        # failed_log per gli abbandoni. Dedup per handle Mega (estratto
        # senza rete): link senza handle riconoscibile vengono saltati.
        handle = extract_handle(url)
        if handle is None:
            log.debug("Storico: handle non estraibile da %s, skip", url)
            return
        try:
            record_completed(handle, url, file_name, int(file_size), path)
        except Exception:
            log.exception(
                "Scrittura download_history.log fallita per file_id=%d", file_id,
            )

    def _on_worker_abandoned(self, file_id: int, url: str, attempts: int, last_error: str) -> None:
        # Persistiamo l'evento sul file dedicato (centralizzato qui per non
        # duplicarlo nel worker) e libera lo slot come per all_done/fatal_error.
        log.warning(
            "Worker file_id=%d abbandonato dopo %d tentativi: %s",
            file_id, attempts, last_error,
        )
        try:
            log_failed_link(file_id, url, attempts, last_error)
        except Exception:
            log.exception("Scrittura failed_links.log fallita per file_id=%d", file_id)
        self.abandoned.emit(file_id, url, attempts, last_error)
        self._on_slot_freed(file_id)

    def _on_worker_cancelled(self, file_id: int) -> None:
        # Un worker ha onorato una richiesta di cancellazione locale.
        # Notifica la GUI e libera lo slot per il prossimo in coda.
        log.info("Worker file_id=%d cancellato dall'utente", file_id)
        self.job_cancelled.emit(file_id)
        self._on_slot_freed(file_id)

    def restart_job(self, file_id: int, url: str) -> bool:
        """Riavvia un singolo job (già in stato terminato). Ritorna False se
        il job è già in coda o in esecuzione, o se l'orchestrator non è pronto."""
        if any(fid == file_id for fid, _ in self._queue):
            return False
        if any(
            w.file_id == file_id and w.isRunning() and not w.is_local_cancelled()
            for w in self._workers
        ):
            return False
        # Pulisci worker terminati per non accumulare riferimenti.
        self._workers = [w for w in self._workers if w.isRunning()]
        # Riattiva sessione se necessario (es. dopo Annulla globale).
        if self.session_state.is_cancelled():
            self.session_state.start()
            self._shutdown_requested = False
        # Riavvia refresher (idempotente: start() non fa nulla se già vivo).
        self._refresher.start()
        if not self._pool_size_timer.isActive():
            self._pool_size_timer.start()
        if not self._cache_save_timer.isActive():
            self._cache_save_timer.start()
        self._queue.append((file_id, url))
        self._fill_slots()
        return True

    def restart_all_failed(self, jobs: list[tuple[int, str]]) -> int:
        """Riavvia una lista di job (file_id, url). Ritorna quanti accettati."""
        return sum(1 for fid, url in jobs if self.restart_job(fid, url))

    def cancel_job(self, file_id: int) -> str:
        # Cancella un singolo job. Ritorna lo stato precedente:
        #   "queued"   -> rimosso dalla coda, GUI gia' aggiornata
        #   "running"  -> richiesta cancellazione al worker (asincrona)
        #   "unknown"  -> niente da cancellare (gia' finito o id non valido)
        # Per i job in coda, emettiamo job_cancelled subito.
        # Per quelli in esecuzione, sara' il worker a emettere cancelled
        # (cfr. _on_worker_cancelled) quando avra' effettivamente terminato.
        for i, (fid, _url) in enumerate(self._queue):
            if fid == file_id:
                del self._queue[i]
                log.info("Cancellato dalla coda file_id=%d", file_id)
                self.job_cancelled.emit(file_id)
                return "queued"
        for w in self._workers:
            if w.file_id == file_id and w.isRunning() and not w.is_local_cancelled():
                w.request_cancel()
                return "running"
        return "unknown"
