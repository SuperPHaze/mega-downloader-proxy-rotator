# Finestra principale: assembla i pannelli e connette i segnali.
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from src.core import diagnostics, session_store
from src.core.branding import resolve as resolve_branding
from src.core.config import (
    APP_VERSION,
    HEARTBEAT_INTERVAL_S,
    OUTPUT_DIR,
    PROXY_SPEEDTEST_STREAMS,
)
from src.core.file_naming import folder_job_output_dir, sanitize_file_name
from src.core.icon_loader import build_app_icon
from src.core.state import SessionState
from src.downloader.orchestrator import DownloadOrchestrator
from src.core.mega_links import is_folder_link, parse_folder_job_url
from src.downloader.worker import job_output_dir
from src.gui.folder_expand_worker import FolderExpandWorker
from src.gui.about_dialog import AboutDialog
from src.gui.controls import ControlsBar
from src.gui.experimental_dialog import ExperimentalFeaturesDialog
from src.gui.i18n import TR, t, tn
from src.gui.job_detail_dialog import JobDetailDialog
from src.gui.jobs_panel import JobsPanel
from src.gui.link_panel import LinkPanel, confirm_already_downloaded
from src.gui.preferences import (
    load_check_updates_on_startup,
    load_connections_per_file,
    load_dark_theme,
    load_download_dir,
    load_link_speed_mbps,
    load_segment_max_duration_s,
    load_speed_selection_enabled,
    load_speed_selection_min_kbps,
    save_dark_theme,
    save_download_dir,
    save_link_speed_mbps,
)
from src.gui.proxy_bar import ProxyBar
from src.gui.speedtest_worker import ProxySpeedTestWorker, SpeedTestWorker
from src.gui.stats_bar import StatsBar
from src.gui.stats_panel import StatsPanel
from src.gui import style as _style
from src.gui.style import LIGHT_QSS, apply_theme
from src.gui.update_banner import UpdateBanner
from src.gui.update_check import STATUS_AVAILABLE, UpdateCheckWorker, repo_url, updates_enabled

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._refresh_window_title()
        self.resize(1100, 820)
        self.setWindowIcon(build_app_icon())

        self.session_state = SessionState()
        self.orchestrator: DownloadOrchestrator | None = None
        self._expected_files = 0
        self._completed_files = 0
        self._open_dialogs: dict[int, JobDetailDialog] = {}
        self._links_by_id: dict[int, str] = {}
        self._pending_delete: set[int] = set()
        # Cartella radice dei download della sessione corrente (None = default).
        # Serve anche a ritrovare la cartella di lavoro per l'eliminazione.
        self._active_output_root: Path | None = None
        # Link non ancora completati della sessione corrente (file_id -> url):
        # persistiti su disco per il ripristino all'avvio (2.7).
        self._session_incomplete: dict[int, str] = {}
        self._dark_theme = False
        # Ultimo messaggio di stato in forma ancora ritraducibile
        # (chiave + parametri): resta None quando il testo arriva gia'
        # formattato dall'orchestrator e non e' quindi ritraducibile.
        self._status_source: tuple[str, int | None, dict[str, object]] | None = None
        self._startup_update_worker: UpdateCheckWorker | None = None
        self._speedtest_worker: SpeedTestWorker | None = None
        self._proxy_speedtest_worker: ProxySpeedTestWorker | None = None
        self._folder_expander: FolderExpandWorker | None = None
        self._expand_dialog: QProgressDialog | None = None

        # LinkPanel: nascosto dall'UI ma funzionale come gestore della lista link.
        self.link_panel = LinkPanel()
        self.link_panel.setParent(self)
        self.link_panel.hide()

        # Applica tema (da preferenze persistite).
        app = QApplication.instance()
        self._dark_theme = load_dark_theme()
        if self._dark_theme:
            apply_theme(app, True)
        else:
            app.setStyleSheet(LIGHT_QSS)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 4)

        self.controls = ControlsBar()
        self.controls.set_dark(self._dark_theme)
        self.controls.set_download_dir(load_download_dir())

        self.update_banner = UpdateBanner()
        self.update_banner.download_requested.connect(self._on_update_download_requested)

        self.jobs_panel = JobsPanel()
        self.stats_bar = StatsBar(self.jobs_panel.model)
        self.proxy_bar = ProxyBar()
        self._stats_panel = StatsPanel(self.jobs_panel.model)

        # Banda della linea: mostra subito l'ultimo valore misurato (proprieta'
        # della linea, persistita) e collega il pulsante di ri-misura.
        cached = load_link_speed_mbps()
        if cached > 0:
            self.proxy_bar.on_speedtest_result(cached, True)
        self.proxy_bar.speedtest_requested.connect(self._run_speedtest)
        self.proxy_bar.proxy_speedtest_requested.connect(self._run_proxy_speedtest)

        # Cruscotto su un'unica riga: zona download (StatsBar) | separatore
        # verticale | zona proxy (ProxyBar). Il colore del separatore segue
        # il tema (vedi _on_theme_toggle -> _restyle_dashboard_separator).
        dashboard_row = QHBoxLayout()
        dashboard_row.setContentsMargins(0, 0, 0, 0)
        dashboard_row.setSpacing(0)
        self._dashboard_separator = QFrame()
        self._dashboard_separator.setFrameShape(QFrame.Shape.NoFrame)
        self._dashboard_separator.setFixedWidth(1)
        self._restyle_dashboard_separator()
        # Stretch 2:1 fra StatsBar (2 zone interne: velocita'+download) e ProxyBar
        # (1 zona): lo spazio extra si distribuisce in proporzione cosi' le
        # tre zone del cruscotto ottengono larghezza comparabile, utile alle
        # sparkline/barra segmentata che crescono in orizzontale.
        dashboard_row.addWidget(self.stats_bar, 2)
        dashboard_row.addWidget(self._dashboard_separator, 0)
        dashboard_row.addWidget(self.proxy_bar, 1)

        layout.addWidget(self.update_banner, 0)
        layout.addWidget(self.controls, 0)
        layout.addLayout(dashboard_row)
        layout.addWidget(self._stats_panel, 0)
        layout.addWidget(self.jobs_panel, 1)

        self.setCentralWidget(central)

        # Barra di stato persistente: stato a sx, versione a dx.
        sb = self.statusBar()
        self._status_lbl = QLabel("")
        sb.addWidget(self._status_lbl, 1)

        version_lbl = QLabel(f"v{APP_VERSION}")
        version_lbl.setStyleSheet("color: gray; font-size: 8pt; padding: 0 4px;")
        sb.addPermanentWidget(version_lbl)

        # Connessioni.
        self.controls.start_requested.connect(self._on_start)
        self.controls.pause_toggled.connect(self._on_pause)
        self.controls.cancel_requested.connect(self._on_cancel)
        self.controls.paste_links_requested.connect(self.link_panel.open_paste_dialog)
        self.controls.theme_toggled.connect(self._on_theme_toggle)
        # Cambio lingua a caldo: il singleton TR e' l'unica sorgente (il
        # selettore nel menu Impostazioni chiama TR.set_preference), qui si fa
        # il fan-out sui pannelli come per il tema.
        TR.language_changed.connect(self._on_language_changed)
        self.controls.info_requested.connect(self._open_about_dialog)
        self.controls.experimental_requested.connect(self._open_experimental_dialog)
        self.controls.download_dir_changed.connect(self._on_download_dir_changed)
        self.jobs_panel.job_double_clicked.connect(self._open_detail)
        self.jobs_panel.cancel_job_requested.connect(self._on_cancel_job_requested)
        self.jobs_panel.delete_folder_requested.connect(self._on_delete_folder_requested)
        self.jobs_panel.paste_links_requested.connect(self.link_panel.open_paste_dialog)
        self.jobs_panel.restart_job_requested.connect(self._on_restart_job_requested)
        self.jobs_panel.restart_all_failed_requested.connect(self._on_restart_all_failed_requested)

        self._maybe_check_updates_on_startup()
        # Misura automatica della banda della linea all'avvio (diretta, fuori
        # dai proxy, in QThread: non blocca la GUI).
        self._run_speedtest()
        # Ripristino sessione: differito all'avvio del loop eventi (dopo che la
        # finestra è visibile), così il prompt ha un parent valido.
        QTimer.singleShot(0, self._maybe_restore_session)

        # Heartbeat diagnostico: una riga INFO periodica su app.log con
        # memoria/thread/job attivi/pool vivi. Passivo, non influenza il
        # download: serve solo a vedere l'ultimo respiro prima di un crash
        # silenzioso e la curva della memoria nel tempo.
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(HEARTBEAT_INTERVAL_S * 1000)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat)
        self._heartbeat_timer.start()

    # ---- diagnostica -------------------------------------------------------

    def _on_heartbeat(self) -> None:
        download_attivi = self.jobs_panel.model.aggregates()["running"]
        pool_vivi = self.orchestrator.pool.size() if self.orchestrator is not None else 0
        diagnostics.log_heartbeat(download_attivi, pool_vivi)

    # ---- Info / controllo aggiornamenti -----------------------------------

    def _open_about_dialog(self) -> None:
        dlg = AboutDialog(self)
        dlg.exec()

    def _open_experimental_dialog(self) -> None:
        dlg = ExperimentalFeaturesDialog(self)
        dlg.exec()

    def _on_update_download_requested(self) -> None:
        QDesktopServices.openUrl(QUrl(repo_url()))

    def _maybe_check_updates_on_startup(self) -> None:
        if not updates_enabled() or not load_check_updates_on_startup():
            return
        self._startup_update_worker = UpdateCheckWorker()
        self._startup_update_worker.finished_check.connect(
            self._on_startup_check_done, Qt.ConnectionType.QueuedConnection
        )
        self._startup_update_worker.start()

    def _on_startup_check_done(self, status: str, latest_version: str) -> None:
        if status == STATUS_AVAILABLE:
            self.update_banner.show_update(latest_version)

    # ---- speed test banda linea -------------------------------------------

    def _run_speedtest(self) -> None:
        if self._speedtest_worker is not None and self._speedtest_worker.isRunning():
            return
        self.proxy_bar.on_speedtest_running()
        self._speedtest_worker = SpeedTestWorker()
        self._speedtest_worker.finished_test.connect(
            self._on_speedtest_done, Qt.ConnectionType.QueuedConnection
        )
        self._speedtest_worker.start()

    def _on_speedtest_done(self, mbit: float, ok: bool) -> None:
        self.proxy_bar.on_speedtest_result(mbit, ok)
        if ok and mbit > 0:
            save_link_speed_mbps(mbit)

    # ---- speed test banda proxy (pool live) -------------------------------

    def _run_proxy_speedtest(self) -> None:
        if self._proxy_speedtest_worker is not None and self._proxy_speedtest_worker.isRunning():
            return
        # Il test "con proxy" usa i proxy vivi del pool dell'orchestrator: ha
        # senso solo durante una sessione attiva. Campioniamo i migliori per
        # score (export_for_cache include host/port/protocol, gia' filtrati sui
        # vivi) e ne prendiamo i top PROXY_SPEEDTEST_STREAMS.
        if self.orchestrator is None:
            self._set_status_t("main_window.proxy_speed_no_session")
            self.proxy_bar.on_proxy_speedtest_result(0.0, False)
            return
        snapshot = self.orchestrator.pool.export_for_cache()
        if not snapshot:
            self._set_status_t("main_window.proxy_speed_no_proxy")
            self.proxy_bar.on_proxy_speedtest_result(0.0, False)
            return
        snapshot.sort(key=lambda p: p.get("score", 0), reverse=True)
        sample = snapshot[:PROXY_SPEEDTEST_STREAMS]
        self.proxy_bar.on_proxy_speedtest_running()
        self._proxy_speedtest_worker = ProxySpeedTestWorker(sample)
        self._proxy_speedtest_worker.finished_test.connect(
            self._on_proxy_speedtest_done, Qt.ConnectionType.QueuedConnection
        )
        self._proxy_speedtest_worker.start()

    def _on_proxy_speedtest_done(self, mbit: float, ok: bool) -> None:
        self.proxy_bar.on_proxy_speedtest_result(mbit, ok)

    # ---- stato status bar ------------------------------------------------

    def _set_status(self, msg: str) -> None:
        """Testo gia' formattato: e' la forma usata dai segnali
        dell'orchestrator, che nasce fuori dalla GUI e non e' traducibile qui.
        """
        self._status_source = None
        self._status_lbl.setText(msg)

    def _set_status_t(self, key: str, **params: object) -> None:
        """Come `_set_status`, ma ricorda chiave e parametri: al cambio
        lingua la riga di stato si riscrive invece di restare indietro.
        """
        self._status_source = (key, None, params)
        self._status_lbl.setText(t(key, **params))

    def _set_status_tn(self, key: str, n: int, **params: object) -> None:
        """Variante plurale di `_set_status_t`."""
        self._status_source = (key, n, params)
        self._status_lbl.setText(tn(key, n, **params))

    def _refresh_status(self) -> None:
        if self._status_source is None:
            return
        key, n, params = self._status_source
        self._status_lbl.setText(
            t(key, **params) if n is None else tn(key, n, **params)
        )

    # ---- avvio sessione --------------------------------------------------

    def _on_download_dir_changed(self, path: str) -> None:
        # Persisti la scelta; se la cartella non è scrivibile, avvisa e torna
        # al default (evita di scoprirlo solo a download avviato).
        if path and not os.access(path, os.W_OK):
            QMessageBox.warning(
                self, t("main_window.dir_not_writable_title"),
                t("main_window.dir_not_writable_body", path=path),
            )
            self.controls.set_download_dir("")
            save_download_dir("")
            self._set_status_t("main_window.dir_reset")
            return
        save_download_dir(path)
        if path:
            self._set_status_t("main_window.dir_set", path=path)
        else:
            self._set_status_t("main_window.dir_default")

    def _on_start(self) -> None:
        links = self.link_panel.get_links()
        if not links:
            QMessageBox.warning(
                self,
                t("main_window.no_links_title"),
                t("main_window.no_links_body"),
            )
            return
        # Un link a cartella non e' scaricabile com'e': va prima elencato ed
        # espanso in un job per file. E' una chiamata di rete, quindi gira in
        # un QThread e il flusso riprende in _on_expansion_done.
        if any(is_folder_link(u) for u in links):
            self._begin_folder_expansion(links)
            return
        self._start_with_links(links)

    # ---- espansione dei link cartella ------------------------------------

    def _begin_folder_expansion(self, links: list[str]) -> None:
        if self._folder_expander is not None and self._folder_expander.isRunning():
            # Il pulsante Avvia e' gia' disabilitato: qui si copre solo il caso
            # di un secondo invio del segnale prima che il thread abbia finito.
            self._set_status_t("main_window.expand_already_running")
            return
        n_folders = sum(1 for u in links if is_folder_link(u))
        self.controls.set_start_enabled(False)
        self._set_status_tn("main_window.expand_status", n_folders)
        qc = Qt.ConnectionType.QueuedConnection
        self._folder_expander = FolderExpandWorker(links)
        self._folder_expander.finished_ok.connect(self._on_expansion_done, qc)
        self._folder_expander.failed.connect(self._on_expansion_failed, qc)
        self._folder_expander.progress.connect(self._on_expansion_progress, qc)
        # Barra di avanzamento annullabile: l'elenco puo' richiedere minuti se
        # la rete verso Mega e' filtrata (5 tentativi con backoff), e in quella
        # fase Pausa/Annulla della sessione non sono ancora attivi: senza questo
        # l'unico modo di uscire sarebbe chiudere la finestra.
        dlg = QProgressDialog(
            t("main_window.expand_dialog_text"),
            t("main_window.expand_dialog_cancel"),
            0,
            max(1, n_folders),
            self,
        )
        dlg.setWindowTitle(t("main_window.expand_dialog_title"))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.canceled.connect(self._on_expansion_cancel_requested)
        self._expand_dialog = dlg
        self._folder_expander.start()

    def _on_expansion_cancel_requested(self) -> None:
        if self._folder_expander is not None and self._folder_expander.isRunning():
            self._set_status_t("main_window.expand_cancelling")
            self._folder_expander.request_cancel()

    def _on_expansion_progress(self, done: int, total: int) -> None:
        self._set_status_t(
            "main_window.expand_progress", done=done, total=total
        )
        if self._expand_dialog is not None:
            self._expand_dialog.setValue(done)

    def _close_expand_dialog(self) -> None:
        if self._expand_dialog is not None:
            self._expand_dialog.close()
            self._expand_dialog = None

    def _on_expansion_failed(self, msg: str) -> None:
        self._close_expand_dialog()
        self.controls.set_start_enabled(True)
        if self._folder_expander is not None and self._folder_expander.is_cancelled():
            # Annullata dall'utente: nessun popup d'errore, non e' un guasto.
            self._set_status_t("main_window.expand_cancelled")
            return
        self._set_status_t("main_window.expand_failed_status")
        QMessageBox.warning(
            self,
            t("main_window.expand_failed_title"),
            t("main_window.expand_failed_body", details=msg),
        )

    def _on_expansion_done(
        self, links: list[str], report: list[str], truncated: int,
    ) -> None:
        self._close_expand_dialog()
        self.controls.set_start_enabled(True)
        # I doppioni e le collisioni di path sono gia' stati risolti dal worker
        # (deduplicate_job_urls), che vede l'insieme completo dei job.
        unique = list(links)
        if truncated:
            proceed = QMessageBox.question(
                self,
                t("main_window.expand_truncated_title"),
                tn(
                    "main_window.expand_truncated_body",
                    truncated,
                    kept=len(unique),
                ),
            )
            if proceed != QMessageBox.StandardButton.Yes:
                self._set_status_t("main_window.start_cancelled")
                return
        if report:
            QMessageBox.information(
                self, t("main_window.expand_report_title"), "\n".join(report),
            )
        self._set_status_tn("main_window.expand_ready", len(unique))
        self._start_with_links(unique)

    def _start_with_links(self, links: list[str]) -> None:
        links = confirm_already_downloaded(links, self)
        if links is None:
            return
        if not links:
            self._set_status_t("main_window.nothing_to_download")
            return

        if self.orchestrator is not None:
            if not self.orchestrator.shutdown():
                self._set_status_t("main_window.previous_session_closing")
                return

        self.jobs_panel.reset(links)
        self._links_by_id = {i: u for i, u in enumerate(links)}
        # Ripristino sessione (2.7): tutti i link partono "non completati";
        # ognuno viene rimosso quando termina (completato/abbandonato/annullato).
        self._session_incomplete = dict(enumerate(links))
        self._session_persist()
        self._pending_delete.clear()
        self.stats_bar.start_clock()
        self._stats_panel.start_clock()
        self.proxy_bar.reset()
        self._set_status_t("main_window.collecting_proxies")
        self._expected_files = len(links)
        self._completed_files = 0
        self.controls.set_running(True)
        self.link_panel.set_running(True)

        concurrency = self.controls.get_concurrency()
        file_time_limit_s = self.controls.get_file_time_limit_s()
        chunk_size_bytes = self.controls.get_chunk_size_bytes()
        connections_per_file = load_connections_per_file()
        segment_max_duration_s = load_segment_max_duration_s()
        speed_enabled = load_speed_selection_enabled()
        speed_min_bps = load_speed_selection_min_kbps() * 1024  # GUI KB/s → motore B/s
        # Banda della linea (Mbit/s): la GUI la legge dalle preferenze e la passa
        # all'orchestrator come config di sessione (il downloader non importa la GUI).
        link_mbit = load_link_speed_mbps()
        download_dir = self.controls.get_download_dir()
        self._active_output_root = Path(download_dir) if download_dir else None
        self.orchestrator = DownloadOrchestrator(self.session_state)
        qc = Qt.ConnectionType.QueuedConnection
        self.orchestrator.progress.connect(self.jobs_panel.on_progress, qc)
        self.orchestrator.ip_logged.connect(self.jobs_panel.on_ip, qc)
        self.orchestrator.failed.connect(self.jobs_panel.on_failed, qc)
        self.orchestrator.cycle_completed.connect(self.jobs_panel.on_cycle_completed, qc)
        self.orchestrator.all_done.connect(self._on_file_done, qc)
        self.orchestrator.fatal_error.connect(self._on_fatal_error, qc)
        self.orchestrator.job_cancelled.connect(self._on_job_cancelled, qc)
        self.orchestrator.abandoned.connect(self._on_abandoned, qc)
        self.orchestrator.throughput.connect(self.jobs_panel.on_throughput, qc)
        self.orchestrator.file_resolved.connect(self.jobs_panel.on_file_resolved, qc)
        self.orchestrator.completed_info.connect(self.jobs_panel.on_completed_info, qc)
        self.orchestrator.pool_ready.connect(
            lambda n: (
                self._set_status_t("main_window.pool_ready", n=n),
                self.proxy_bar.on_validation_done(),
            ),
            qc,
        )
        self.orchestrator.pool_failed.connect(
            lambda msg: self._set_status_t(
                "main_window.pool_failed", error=msg
            ),
            qc,
        )
        self.orchestrator.setup_status.connect(self._set_status, qc)
        self.orchestrator.setup_progress.connect(
            lambda d, tot, a: (
                self._set_status_t(
                    "main_window.validation_progress", done=d, total=tot, alive=a
                ),
                self.proxy_bar.on_validation_progress(d, tot, a),
            ),
            qc,
        )
        self.orchestrator.pool_size_changed.connect(self.proxy_bar.on_pool_size, qc)
        self.orchestrator.proxy_stats.connect(self.proxy_bar.on_proxy_stats, qc)
        self.orchestrator.start(
            links,
            concurrency=concurrency,
            file_time_limit_s=file_time_limit_s,
            chunk_size_bytes=chunk_size_bytes,
            connections_per_file=connections_per_file,
            segment_max_duration_s=segment_max_duration_s,
            speed_selection_enabled=speed_enabled,
            speed_selection_min_bps=speed_min_bps,
            link_capacity_mbit=link_mbit if link_mbit > 0 else None,
            output_root=self._active_output_root,
        )

    # ---- pausa / annullo globale -----------------------------------------

    def _on_pause(self, paused: bool) -> None:
        if paused:
            self.session_state.pause()
            self._set_status_t("main_window.paused")
        else:
            self.session_state.resume()
            self._set_status_t("main_window.resumed")

    def _on_cancel(self) -> None:
        self.session_state.cancel()
        if self.orchestrator is not None:
            self.orchestrator.stop_background_tasks()
        self.jobs_panel.on_cancel_all()
        self.controls.reset()
        self._restore_session_ui()
        # Annullo esplicito dell'utente: niente prompt di ripristino la prossima
        # volta (i .part restano comunque su disco per un eventuale riavvio).
        self._session_incomplete.clear()
        session_store.clear()
        self._set_status_t("main_window.cancelled")

    # ---- ripristino sessione (2.7) ---------------------------------------

    def _session_persist(self) -> None:
        urls = list(self._session_incomplete.values())
        if urls:
            session_store.save(urls)
        else:
            session_store.clear()

    def _session_mark_finished(self, file_id: int) -> None:
        # Un job è terminato (completato/abbandonato/annullato/errore): togli il
        # suo link dai "non completati" e aggiorna il file di stato.
        if self._session_incomplete.pop(file_id, None) is not None:
            self._session_persist()

    def _maybe_restore_session(self) -> None:
        urls = session_store.load()
        if not urls:
            return
        reply = QMessageBox.question(
            self,
            t("main_window.restore_title"),
            tn("main_window.restore_body", len(urls)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.link_panel.set_links(urls)
            self._set_status_tn(
                "main_window.restored_status", len(urls)
            )
        else:
            session_store.clear()

    def _restore_session_ui(self) -> None:
        self.link_panel.set_running(False)

    # ---- terminazione download -------------------------------------------

    def _on_file_done(self, file_id: int) -> None:
        self.jobs_panel.on_all_done(file_id)
        self._session_mark_finished(file_id)
        self._completed_files += 1
        self._set_status_t(
            "main_window.file_done",
            file=file_id + 1,
            done=self._completed_files,
            total=self._expected_files,
        )
        if self._completed_files >= self._expected_files:
            self._set_status_t("main_window.all_completed")
            self.controls.reset()
            self._restore_session_ui()

    def _on_fatal_error(self, file_id: int, msg: str) -> None:
        self.jobs_panel.on_fatal(file_id, msg)
        QMessageBox.critical(
            self,
            t("main_window.fatal_title"),
            t("main_window.fatal_body", file=file_id + 1, error=msg),
        )
        self._set_status_t(
            "main_window.fatal_status", file=file_id + 1, error=msg
        )
        self._session_mark_finished(file_id)
        self._completed_files += 1
        if self._completed_files >= self._expected_files:
            self.controls.reset()
            self._restore_session_ui()

    def _on_abandoned(self, file_id: int, url: str, attempts: int, last_error: str) -> None:
        self.jobs_panel.on_abandoned(file_id, url, attempts, last_error)
        self._session_mark_finished(file_id)
        self._completed_files += 1
        self._set_status_tn(
            "main_window.abandoned_status",
            attempts,
            file=file_id + 1,
            error=last_error,
        )
        if self._completed_files >= self._expected_files:
            self._set_status_t("main_window.all_terminated")
            self.controls.reset()
            self._restore_session_ui()

    # ---- cancellazione per-job ------------------------------------------

    def _on_cancel_job_requested(self, file_id: int, delete_folder: bool) -> None:
        if self.orchestrator is None:
            if delete_folder:
                self._delete_folder_for(file_id)
            self.jobs_panel.model.mark_cancelled(file_id)
            return
        state = self.orchestrator.cancel_job(file_id)
        if state == "unknown":
            if delete_folder:
                self._delete_folder_for(file_id)
            return
        if delete_folder:
            self._pending_delete.add(file_id)
        if state == "running":
            self._set_status_t(
                "main_window.job_cancelling", file=file_id + 1
            )

    def _on_job_cancelled(self, file_id: int) -> None:
        self.jobs_panel.model.mark_cancelled(file_id)
        self._session_mark_finished(file_id)
        if file_id in self._pending_delete:
            self._pending_delete.discard(file_id)
            self._delete_folder_for(file_id)
        self._completed_files += 1
        self._set_status_t(
            "main_window.job_cancelled",
            file=file_id + 1,
            done=self._completed_files,
            total=self._expected_files,
        )
        if self._completed_files >= self._expected_files:
            self._set_status_t("main_window.all_terminated")
            self.controls.reset()
            self._restore_session_ui()

    def _on_delete_folder_requested(self, file_id: int) -> None:
        url = self._links_by_id.get(file_id)
        is_folder_job = url is not None and parse_folder_job_url(url) is not None
        # Le due varianti erano costruite a pezzi attorno al numero del
        # file: un frammento come « dalla cartella scaricata?» non e'
        # traducibile da solo, quindi ognuna e' ora una chiave intera.
        body_key = (
            "main_window.delete_folder_job_body" if is_folder_job
            else "main_window.delete_folder_body"
        )
        confirm = QMessageBox.question(
            self,
            t("main_window.delete_title"),
            t(body_key, file=file_id + 1),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._delete_folder_for(file_id)

    def _delete_folder_for(self, file_id: int) -> None:
        # Job nato dall'espansione di una cartella: la cartella su disco e'
        # CONDIVISA con gli altri file dello stesso albero (alcuni magari
        # ancora in corso o gia' completati). Si elimina solo questo file.
        folder_url = self._links_by_id.get(file_id)
        if folder_url is not None and parse_folder_job_url(folder_url) is not None:
            self._delete_folder_job_file(file_id, folder_url)
            return
        # Usa il path corrente dal modello se disponibile (la cartella potrebbe
        # essere stata rinominata col nome file dopo il resolve).
        path: Path | None = None
        job = self.jobs_panel.model.get_job(file_id)
        if job and job.output_path:
            p = Path(job.output_path)
            # output_path è il file finale: OUTPUT_DIR/<nome>_<id>/ciclo_N/<file>
            # La cartella base è 2 livelli sopra.
            candidate = p.parent.parent
            if candidate.is_dir():
                path = candidate
        if path is None:
            url = self._links_by_id.get(file_id)
            if url is None:
                log.warning("Delete folder: file_id=%d non trovato", file_id)
                return
            path = job_output_dir(url, file_id, self._active_output_root)
        if not path.exists():
            self._set_status_t(
                "main_window.delete_missing", file=file_id + 1
            )
            return
        try:
            shutil.rmtree(path)
            log.info("Cartella eliminata: %s", path)
            self._set_status_t(
                "main_window.delete_done", file=file_id + 1, name=path.name
            )
        except OSError as exc:
            log.exception("Impossibile eliminare %s", path)
            QMessageBox.warning(
                self,
                t("main_window.delete_failed_title"),
                t("main_window.delete_failed_body", path=path, error=exc),
            )

    def _delete_folder_job_file(self, file_id: int, url: str) -> None:
        """Elimina il singolo file di un job-cartella (mai l'albero condiviso).

        Rimuove il file finale, il `.part` e i sidecar di resume, poi pota le
        cartelle rimaste vuote risalendo fino alla radice dei download
        (esclusa): se altri file dell'albero esistono ancora, la potatura si
        ferma da sola alla prima cartella non vuota.
        """
        job = parse_folder_job_url(url)
        if job is None:
            return
        root = self._active_output_root or OUTPUT_DIR
        directory = folder_job_output_dir(job.rel_path, self._active_output_root)
        name = sanitize_file_name(job.file_name, fallback=f"mega_{job.node_handle}")
        targets = [
            directory / name,
            directory / f"{name}.part",
            directory / f"{name}.part.progress.json",
            directory / f"{name}.progress.json",   # sidecar del vecchio schema
        ]
        removed = 0
        for target in targets:
            try:
                if target.is_file():
                    target.unlink()
                    removed += 1
            except OSError as exc:
                log.warning("Impossibile eliminare %s: %s", target, exc)
        if removed == 0:
            self._set_status_t(
                "main_window.delete_nothing", file=file_id + 1
            )
            return
        # Potatura delle cartelle rimaste vuote (mai la radice dei download).
        current = directory
        try:
            root_resolved = root.resolve()
            while current.resolve() != root_resolved and current.is_dir():
                if any(current.iterdir()):
                    break
                parent = current.parent
                current.rmdir()
                log.info("Cartella vuota rimossa: %s", current)
                current = parent
        except OSError as exc:
            log.debug("Potatura cartelle interrotta su %s: %s", current, exc)
        log.info("File del job-cartella eliminato: %s", directory / name)
        self._set_status_t(
            "main_window.delete_file_done", file=file_id + 1, name=name
        )

    # ---- tema chiaro/scuro ----------------------------------------------

    def _on_theme_toggle(self, dark: bool) -> None:
        self._dark_theme = dark
        app = QApplication.instance()
        apply_theme(app, dark)
        save_dark_theme(dark)
        # Aggiorna i widget che usano colori inline (badge, card, KPI).
        self.jobs_panel.refresh_theme()
        self.stats_bar.refresh_theme()
        self.proxy_bar.refresh_theme()
        self._stats_panel.refresh_theme()
        self._restyle_dashboard_separator()

    # ---- lingua dell'interfaccia ----------------------------------------

    def _refresh_window_title(self) -> None:
        self.setWindowTitle(
            t("main_window.title", name=resolve_branding().name, version=APP_VERSION)
        )

    def _on_language_changed(self, lang: str) -> None:
        """Ritraduzione a caldo: gemello di `_on_theme_toggle`.

        Copre TUTTE le superfici persistenti della finestra: titolo,
        barra comandi, banner, cruscotto (StatsBar/ProxyBar/StatsPanel),
        elenco job, pannello link e riga di stato. I dialoghi non servono:
        nascono all'apertura e leggono i testi alla costruzione.

        Restano in italiano i testi che nascono dagli errori di
        `core`/`downloader` (fase Errori & Cronologia)."""
        log.info("Ritraduzione interfaccia in corso: %s", lang)
        self._refresh_window_title()
        self.controls.retranslate()
        self.update_banner.retranslate()
        self.stats_bar.retranslate()
        self.proxy_bar.retranslate()
        self._stats_panel.retranslate()
        self.jobs_panel.retranslate()
        self.link_panel.retranslate()
        self._refresh_status()

    def _restyle_dashboard_separator(self) -> None:
        p = _style.CURRENT_PALETTE
        self._dashboard_separator.setStyleSheet(
            f"QFrame {{ background-color: {p['border']}; border: none; }}"
        )

    # ---- riavvio job ----------------------------------------------------

    def _on_restart_job_requested(self, file_id: int) -> None:
        url = self._links_by_id.get(file_id)
        if url is None:
            self._set_status_t(
                "main_window.restart_no_url", file=file_id + 1
            )
            return
        if not self.jobs_panel.model.restart_job(file_id):
            return  # job non riavviabile (già in coda o running)
        # I due testi passati a mark_failed_fatal restano in italiano di
        # proposito: non sono cromo della finestra ma messaggi d'errore che
        # finiscono nel modello, insieme a quelli di core/downloader. Si
        # traducono tutti insieme nella fase Errori & Cronologia, con i codici.
        if self.orchestrator is None:
            self.jobs_panel.model.mark_failed_fatal(file_id, "Nessun orchestrator attivo")
            return
        if not self.orchestrator.restart_job(file_id, url):
            self.jobs_panel.model.mark_failed_fatal(file_id, "Riavvio rifiutato dall'orchestrator")
            self._set_status_t(
                "main_window.restart_failed", file=file_id + 1
            )
            return
        self._completed_files = max(0, self._completed_files - 1)
        self.controls.set_running(True)
        self.link_panel.set_running(True)
        self._set_status_t("main_window.restart_queued", file=file_id + 1)

    def _on_restart_all_failed_requested(self) -> None:
        if self.orchestrator is None:
            return
        # Raccogli prima di mutare il modello.
        restartable = list(self.jobs_panel.model.iter_restartable())
        if not restartable:
            return
        jobs: list[tuple[int, str]] = []
        for job in restartable:
            url = self._links_by_id.get(job.file_id)
            if url is not None:
                self.jobs_panel.model.restart_job(job.file_id)
                jobs.append((job.file_id, url))
        n_started = self.orchestrator.restart_all_failed(jobs)
        if n_started > 0:
            self._completed_files = max(0, self._completed_files - n_started)
            self.controls.set_running(True)
            self.link_panel.set_running(True)
            self._set_status_tn("main_window.restart_all_done", n_started)

    # ---- dettaglio job --------------------------------------------------

    def _open_detail(self, file_id: int) -> None:
        dlg = self._open_dialogs.get(file_id)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            return
        dlg = JobDetailDialog(self.jobs_panel.model, file_id, self)
        self._open_dialogs[file_id] = dlg
        dlg.show()

    # ---- chiusura -------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.orchestrator is not None:
            if not self.orchestrator.shutdown():
                log.warning("closeEvent: shutdown incompleto, chiudo comunque")
        if self._startup_update_worker is not None and self._startup_update_worker.isRunning():
            self._startup_update_worker.wait(2000)
        if self._speedtest_worker is not None and self._speedtest_worker.isRunning():
            self._speedtest_worker.wait(3000)
        if self._proxy_speedtest_worker is not None and self._proxy_speedtest_worker.isRunning():
            self._proxy_speedtest_worker.wait(3000)
        if self._folder_expander is not None and self._folder_expander.isRunning():
            # Zittisci i segnali PRIMA di attendere: la finestra sta sparendo e
            # uno slot che apre un QMessageBox durante la chiusura non ha senso.
            self._folder_expander.blockSignals(True)
            self._folder_expander.request_cancel()
            self._folder_expander.wait(3000)
        self._close_expand_dialog()
        # Marcatore di chiusura volontaria: se nel log compare un SESSION
        # START senza questo prima del successivo START, e' stato un crash o
        # un kill esterno (non una chiusura dall'utente).
        diagnostics.log_session_clean_exit()
        super().closeEvent(event)
