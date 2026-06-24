# Mega Downloader Proxy Rotator (MDPR)

## Scopo del progetto
App desktop Python+PyQt6 che scarica file da Mega.nz attraverso proxy HTTP gratuiti, con una coda di chunk a dimensione fissa (default 32 MB) scaricati da N connessioni parallele (default 10), ciascuna su un proxy diverso, e più file in parallelo (default 1, configurabile fino a 5).
Origine: test tecnico di rotazione IP (DOWNLOAD_CYCLES=3, completato e superato il 2026-05-31). Ora `DOWNLOAD_CYCLES=1`: uso normale come downloader.
Single-user, single-process, niente backend.

## Mappa moduli
```
src/
├── main.py                # entry point: QApplication + MainWindow
├── core/
│   ├── config.py          # costanti globali (timeout, soglie, paths, UA)
│   ├── state.py           # SessionState thread-safe (pausa/annullo)
│   ├── events.py          # EventBus opzionale (non usato dal flusso)
│   ├── logging_setup.py   # setup root logger + sys.excepthook
│   ├── failed_log.py      # logger JSONL dei link abbandonati
│   ├── download_history.py # storico JSONL download completati + extract_handle
│   ├── sources_stats.py   # logger JSONL metriche per-fonte
│   ├── version_compare.py # parse_semver/is_newer, puro stdlib (no I/O)
│   ├── branding.py        # Branding (nome/acronimo/autore/nick/link/logo): default -> cache -> remoto
│   └── icon_loader.py     # build_app_icon(): QIcon robusta .ico->fallback .png, mai null senza log
├── proxy/
│   ├── sources.py         # 32 fonti pubbliche (4 html, 25 plain, 3 json/jsonl)
│   ├── scraper.py         # ProxyScraper.fetch_all() multi-source
│   ├── validator.py       # 2-stage: stage1 alive + stage2 Mega
│   ├── pool.py            # ProxyPool score-based round-robin; contatori di sessione per la GUI (discarded_count/refill_count/seconds_since_last_refill, alimentati da note_refill())
│   ├── refresher.py       # BackgroundPoolRefresher (thread daemon)
│   └── proxy_cache.py     # cache proxy persistente JSON (hot-start)
├── downloader/
│   ├── mega_crypto.py     # primitive AES-CBC/CTR vendorizzate
│   ├── mega_api.py        # MegaPublicClient (resolve URL pubblica Mega)
│   ├── mega_client.py     # MegaClient seriale (single-stream via proxy)
│   ├── parallel_client.py # ParallelMegaDownloader (coda chunk a dimensione fissa, HTTP Range N parallele)
│   ├── worker.py          # DownloadWorker(QThread) — 1 link, N cicli
│   └── orchestrator.py    # DownloadOrchestrator(QObject) — coordina tutto; segnale proxy_stats(discarded, refill_count, seconds_since_last_refill) emesso insieme a pool_size_changed nel poll periodico
└── gui/
    ├── main_window.py     # MainWindow (QMainWindow)
    ├── link_panel.py      # gestore lista link (nascosto nell'UI, API get_links/open_paste_dialog)
    ├── paste_links_dialog.py # dialog modale incolla/edita lista link
    ├── jobs_model.py      # JobsModel (QAbstractTableModel) + Job (throughput/file_name/output_path)
    ├── jobs_panel.py      # lista job a righe-card (QScrollArea + _JobCard widget per riga); filtri "Mostra:" a pulsanti esclusivi (QButtonGroup)
    ├── job_detail_dialog.py # dialog non-modale dettaglio job (doppio clic)
    ├── sparkline.py       # Sparkline: micro-grafico a linea riusabile; matematica pura in sparkline_points() (no Qt, testabile)
    ├── segment_bar.py     # SegmentBar: barra orizzontale a segmenti proporzionali riusabile; matematica pura in segment_widths() (no Qt, testabile)
    ├── session_speed.py   # SessionSpeedStats: media/picco/minima di sessione (puro, no Qt/I/O), campionato 1x/s da StatsBar
    ├── stats_bar.py       # cruscotto "spinta" compatto: zona velocita' (valore + Sparkline + media/picco/minima/ETA/tempo) e zona Download (totale + SegmentBar + conteggi), separate da una linea verticale interna
    ├── proxy_bar.py       # ProxyBar: zona proxy in stile "conservativo" — riga di card compatte (vivi/validazione/scartati/ricariche/ultimo refill), niente sparkline; popolata da pool_size_changed/setup_progress/proxy_stats dell'orchestrator
    ├── controls.py        # barra comandi: Avvia/Pausa/Annulla/Paralleli/Incolla/Tema/Info (in menu Impostazioni)
    ├── experimental_dialog.py # ExperimentalFeaturesDialog: dalla 1.9.0 segnaposto vuoto (nessuna leva attiva in UI); motore (selection_mode/connections_per_file) invariato
    ├── preferences.py     # carica/salva preferenze utente (tema, check aggiornamenti all'avvio) in preferences.json
    ├── about_dialog.py    # AboutDialog: nome/acronimo/autore/nick/link/logo (da branding) + licenza + controllo aggiornamenti manuale
    ├── update_check.py    # UpdateCheckWorker(QThread): GET releases/latest GitHub, fuori dal thread GUI
    ├── update_banner.py   # UpdateBanner: barra sottile richiudibile ("nuova versione disponibile")
    ├── branding_fetch.py  # BrandingFetchWorker(QThread): GET manifest.json + logo remoti, size-limited, fuori dal thread GUI
    └── style.py           # PALETTE_LIGHT/DARK, CURRENT_PALETTE, build_qss(), apply_theme()

tools/
├── cli_download.py        # runner CLI senza GUI (riusa Orchestrator)
├── monitor_gui.py         # GUI live monitor velocita' download
├── monitor_speed.py       # CLI polling cartella downloads/
└── report.py              # report HTML diagnostico (sola lettura) da logs/events.jsonl + logs/crash.log

scripts/
├── bench_cache.py         # bench cold vs hot start (cache)
├── download_once.py       # CLI one-shot: scarica un link una volta
└── download_n.py          # CLI multi-ciclo: scarica un link N volte

install.ps1                # installer: crea venv, pip install, smoke test, launcher
package.ps1                # packaging: crea dist/MegaProxyRotator-X.Y.Z.zip
```

## Entry point
`src/main.py` → `MainWindow` → `DownloadOrchestrator`.

## Flusso dati
1. Utente incolla link Mega in `LinkPanel` → clic "Avvia".
2. `MainWindow._on_start` istanzia `DownloadOrchestrator(SessionState)` e gli passa la lista link.
3. `Orchestrator.start()`: hot-start da `proxy_cache.load()` se disponibile, altrimenti `ProxyScraper.fetch_all()` → `ProxyValidator.validate_against_mega()` → `ProxyPool.add_many()`.
4. Per ogni link viene avviato un `DownloadWorker(QThread)` che esegue `DOWNLOAD_CYCLES` cicli.
5. A ogni ciclo: `ProxyPool.get_next()` → `MegaClient(proxy).get_egress_ip()` → se `PARALLEL_CONNECTIONS_PER_FILE > 1` (default 4) usa `ParallelMegaDownloader.download()`, altrimenti `MegaClient.download()`.
6. Worker emette `progress / ip_logged / cycle_completed / failed / fatal_error / completed_info / all_done / cancelled / abandoned / throughput` → `JobsPanel` (via `JobsModel`). Su `completed_info` l'orchestrator persiste lo storico in `download_history.log` e lo riemette alla GUI per aggiornare nome file e path nelle card.
7. Worker controlla `is_cancelled()` / `wait_if_paused()` su un `_EffectiveSessionState` che combina `SessionState` globale + flag locale (cancellazione per-job).
8. Cancellazione per-job: utente clicca la X rossa in colonna 0 → `JobsPanel.cancel_job_requested` → `MainWindow` → `DownloadOrchestrator.cancel_job(file_id)`. Se in coda viene rimosso, se in corso `worker.request_cancel()` setta il flag locale e il worker esce al prossimo checkpoint emettendo `cancelled`. La cartella `downloads/<sha1>_<file_id>/` viene rimossa lato GUI dopo la terminazione del worker.

## Convenzioni
- GUI in italiano; codice (variabili/funzioni/classi) in inglese.
- Downloader: pattern `.part` + rename atomico. Si scarica SEMPRE su `<nome>.part` (sidecar `.progress.json` riferito al `.part`, include `chunk_size` per validare compatibilità del resume); `os.replace` sul nome finale solo a download completo e verificato. L'esistenza del nome finale è l'UNICO marker di completamento usato dal check di resume del worker. I `.part` non vanno mai cancellati al cleanup (servono al resume: i chunk completati restano scritti e vengono skippati al retry).
- Pool scoring: i call-site devono registrare anche i successi (`record_success` su segmento completato / IP check ok) e usare `penalize(hard=True)` solo per 403/509/503 dal CDN; errori transitori (timeout, throughput basso, connection error) → `penalize(hard=False)`. Mai usare `mark_dead` (alias deprecato).
- Sessioni: prima di creare un nuovo `DownloadOrchestrator` chiamare SEMPRE `shutdown()` su quello precedente (teardown worker/refresher/timer); se ritorna False non avviare e mantenere il riferimento (distruggere QThread vivi = crash).
- Comunicazione GUI↔worker SOLO via PyQt signals (mai chiamate dirette dalla GUI ai worker).
- `SessionState` è l'UNICA fonte di verità per pausa/annullo.
- Nuovo proxy source → aggiungere voce in `proxy/sources.py` + parser dedicato in `scraper.py`.
- Nuovo provider cloud (oltre Mega) → nuovo modulo in `downloader/`, mai patch a `mega_client.py`.
- I segnali da QThread alla GUI vanno connessi con `Qt.ConnectionType.QueuedConnection`.

## Anomalie note
- I proxy gratuiti hanno tasso di mortalità ~70%: è normale che `ProxyValidator` scarti la maggioranza.
- mega.py è stato vendorizzato: le primitive crypto e l'API pubblica sono in `src/downloader/mega_crypto.py` e `src/downloader/mega_api.py`. Nessuna dipendenza esterna `mega.py`, nessun conflitto tenacity/pathlib.
- Mega può rate-limitare lo stesso file anche da IP diversi: è atteso, è proprio ciò che il test misura.
- **403/509 dal CDN Mega indica rate-limit del proxy, NON scadenza URL**: un re-resolve dell'URL CDN ritorna sistematicamente lo stesso host. Il proxy va marcato dead; il re-resolve va riservato ai casi di URL effettivamente cambiata (es. 503 di overload).
- L'import di `pycryptodome` (pesante) avviene localmente dentro `MegaClient.download()` e `ParallelMegaDownloader.download()` per non rallentare l'avvio della GUI.

## Logging
- Configurato in `core/logging_setup.py`. Tutti i log diagnostici/operativi vivono in `logs/` (vedi `LOGS_DIR`/`REPORTS_DIR` in `core/config.py`); restano in root solo le cache (`proxy_cache.json`, `branding_cache.json`, `branding_logo.*`).
- File human-readable: `logs/app.log` (rotante 5 MB × 3 backup). Livello DEBUG su tutti i moduli; `urllib3` e `requests` capped a WARNING.
- **Log strutturato universale**: `logs/events.jsonl` (JSON Lines, rotante 20 MB × 5 backup, sempre a DEBUG senza filtri a monte). Ogni record di logging viene scritto anche qui via `JsonLinesFormatter` (campi base `ts/level/logger/thread/msg` + ogni attributo `extra={...}` passato dal chiamante). Sorgente primaria per `tools/report.py`.
- `setup_logging()` viene chiamato in `src/main.py` prima della creazione di `QApplication`; crea `logs/` se assente.
- Hook globale `sys.excepthook` cattura le eccezioni non gestite nel thread principale.
- Log dedicati JSONL in `logs/`: `failed_links.log` (link abbandonati), `download_history.log` (download completati, dedup per handle), `proxy_sources_stats.log` (survival per-fonte).
- `tools/report.py` legge `logs/events.jsonl` + `logs/crash.log` (sola lettura) e genera un report HTML in `logs/reports/`.

## Setup ambiente (Windows + Python 3.11–3.14)
```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m src.main
```
Comandi sempre dalla root `mega-proxy-downloader\`, mai da `src\`.
- **L'upgrade di pip PRIMA di requirements.txt è obbligatorio**: il pip bundled (es. 22.3 con Python 3.11) non risolve i wheel PyQt6-sip recenti → `ResolutionImpossible` su PyQt6. `install.ps1` lo fa già; su macchina nuova usare `install.bat` (wrapper cmd/doppio-clic di `install.ps1`) o `install.ps1` direttamente.
- I venv NON sono portabili tra macchine (pyvenv.cfg punta al Python d'origine): mai copiare `venv`, ricrearla sempre. `package.ps1` la esclude già dallo zip.

## Versioning e packaging
- La versione dell'app è definita in `src/core/config.py` come `APP_VERSION` (semver `MAJOR.MINOR.PATCH`).
- `APP_VERSION` viene mostrata nel titolo della finestra principale (`MainWindow`).
- `package.ps1` legge `APP_VERSION` e produce `dist/MegaProxyRotator-X.Y.Z.zip` escludendo `venv`, `dist`, `downloads`, `__pycache__`, `.git`, `.claude`, log e cache.
- L'utente che riceve lo zip esegue `install.ps1` (crea venv + dipendenze) e poi `avvia.bat`.
- **Regola obbligatoria**: al termine di ogni task, chiedere all'utente se vuole aggiornare `APP_VERSION`.

## File da NON modificare senza motivo
- `src/core/state.py` — logica di concorrenza (QMutex + QWaitCondition) delicata; ogni modifica deve preservare gli invariants pausa/annullo.
