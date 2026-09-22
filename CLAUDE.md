# Mega Downloader Proxy Rotator (MDPR)

> Regole permanenti (non negoziabili, da leggere prima di toccare GUI o documentazione): GUI
> bilingue in sync — `.claude/rules/gui.md` · Doc bilingue in sync — `.claude/rules/docs-i18n.md` ·
> Doc sempre allineata al codice — `.claude/rules/documentazione-e-rilascio.md` ·
> Demo runner allineato — `.claude/rules/demo-runner.md`.

## Scopo del progetto
App desktop Python+PyQt6 che scarica file da Mega.nz attraverso proxy HTTP gratuiti, con una coda di chunk a dimensione fissa (default 32 MB) scaricati da N connessioni parallele (default 10), ciascuna su un proxy diverso, e più file in parallelo (default 1, configurabile fino a 5).
Origine: test tecnico di rotazione IP (DOWNLOAD_CYCLES=3, completato e superato il 2026-05-31). Ora `DOWNLOAD_CYCLES=1`: uso normale come downloader.
Single-user, single-process, niente backend.

## Mappa moduli
```
src/
├── main.py                # entry point: QApplication + MainWindow
├── core/
│   ├── config.py          # costanti globali (timeout, soglie, paths, UA); include SPEED_SELECTION_* e VALIDATOR_SPEED_TEST_* per la selezione per velocità
│   ├── state.py           # SessionState thread-safe (pausa/annullo)
│   ├── errors.py          # UserFacingError: le eccezioni che l'utente legge portano `error_code` + `params`; `str(exc)` resta la frase ITALIANA (e' cio' che finisce nei log). `format_it()` non solleva mai (gira dentro la gestione degli errori); `error_payload()` da' codice+parametri anche per le eccezioni non nostre (ripiego `unexpected`). Le basi miste vogliono UserFacingError per PRIMO: con OSError davanti, il suo __new__ intercetta la costruzione
│   ├── error_catalog.py   # ERROR_TEXTS_IT: i 50 testi italiani degli errori, indicizzati per codice. Vive in core/ e non nei dizionari GUI perche' serve ai LOG, che restano italiani anche con l'interfaccia in inglese; `strings_it.py` li innesta come chiavi `err.*`
│   ├── telemetry.py       # telemetria "scatola nera": recorder asincrono (writer daemon) di tentativi-chunk + campioni 1Hz in logs/telemetry/<id>/; no-op se TELEMETRY_ENABLED=False
│   ├── diagnostics.py     # heartbeat periodico (INFO), RSS via psutil se disponibile / fallback GetProcessMemoryInfo (psapi) su Windows, marcatori di sessione, riga CONFIG a inizio sessione
│   ├── events.py          # EventBus opzionale (non usato dal flusso)
│   ├── logging_setup.py   # setup root logger + sys.excepthook + tee di stdout/stderr su terminal-log.txt.
│   │                     #   `_TeeStream` regge un flusso originale ASSENTE (`None`): con `pythonw.exe`
│   │                     #   non c'è console e `sys.stdout`/`sys.stderr` valgono None — senza guardia la
│   │                     #   prima riga di log ucciderebbe l'app prima della finestra. Senza tee E senza
│   │                     #   stderr, l'handler di console non viene nemmeno aggiunto.
│   │                     #   `log_unhandled_main_exception()` porta in crash.log anche le eccezioni non
│   │                     #   gestite del thread PRINCIPALE (gemello di `_threading_excepthook`): senza
│   │                     #   console è l'unico posto dove il traceback resta, e lo legge `tools/report.py`
│   │                     #   `reset_log_file(path)` azzera un log TENUTO APERTO (su Windows
│   │                     #   `unlink` su un file aperto fallisce): chiude il flusso del canale,
│   │                     #   tronca e riapre; `terminal-log.txt` si tronca IN POSTO perché
│   │                     #   `_TeeStream` ha catturato quell'oggetto file. Lo usa `maintenance.py`
│   ├── failed_log.py      # logger JSONL dei link abbandonati
│   ├── download_history.py # storico JSONL download completati + extract_handle
│   ├── sources_stats.py   # logger JSONL metriche per-fonte
│   ├── version_compare.py # parse_semver/is_newer, puro stdlib (no I/O)
│   ├── branding.py        # Branding (nome/acronimo/autore/nick/link/logo): default -> cache -> remoto
│   ├── icon_loader.py     # build_app_icon(): QIcon robusta .ico->fallback .png, mai null senza log. I fotogrammi
│   │                     #   del .ico si leggono UNO PER UNO con QImageReader e si aggiungono con addPixmap: la
│   │                     #   sola `addFile()` lascia al lettore ICO di Qt la scelta di quante dimensioni esporre
│   │                     #   (con Qt 6.11 le espone tutte e 7 — misurato — ma non è un contratto). Il controllo
│   │                     #   di riuscita è `availableSizes()`, non `isNull()`
│   ├── file_naming.py     # sanitize_folder_name() + sanitize_file_name() (nome file sicuro per Windows: caratteri riservati + device name CON/NUL/…, estensione preservata; applicata alla SORGENTE in mega_api.resolve_public_url) + final_output_dir(file_name, file_id, output_root): path finale del download (output_root = cartella scelta dall'utente, None=default); rinomina la cartella hash-based al primo resolve riuscito; + folder_job_output_dir(rel_path, output_root): cartella di destinazione ad ALBERO per i job nati da un link cartella (ri-sanifica i segmenti: è il confine col filesystem)
│   ├── disk.py            # ensure_free_space()/free_space_bytes() + InsufficientDiskSpaceError (UserFacingError+OSError, codice `disk_full`): check spazio disco PRIMA del download (errore d'ambiente: il worker abbandona subito senza bruciare i tentativi). Solo stdlib
│   ├── mega_links.py      # FONTE UNICA delle forme di URL Mega (stdlib puro, niente I/O né Crypto):
│   │                     #   file singolo, legacy, cartella `/folder/#key`, cartella con nodo selezionato
│   │                     #   (`/file/<n>`, `/folder/<n>`, legacy `#F!id!key!node`) e la forma INTERNA dei
│   │                     #   job-cartella. Ordine di match dal più specifico al più generico.
│   │                     #   `extract_handle` vive qui (download_history vi delega)
│   ├── maintenance.py     # manutenzione: MISURA (survey/survey_all: quanti file, quante voci,
│   │                     #   quanto spazio) e CANCELLA (clear/clear_items) i dati lasciati su
│   │                     #   disco — storico, stato di sessione, cartella download, log. Non sa
│   │                     #   nulla della GUI. `SESSION_LOCKED_ITEMS` = le due voci che NON si
│   │                     #   azzerano a sessione viva. Fuori perimetro di proposito:
│   │                     #   `preferences.json` (l'app lo riscriverebbe), `crash.log` e la
│   │                     #   telemetria, e la cache proxy (vive in `src/proxy/`, che core non
│   │                     #   può importare: la chiama la finestra, con `delete_proxy_cache`)
│   ├── session_store.py   # persistenza JSON dei link NON completati della sessione (save/load/clear, mai solleva) per il prompt "Riprendi sessione precedente?" all'avvio; i .part fanno il resume a livello byte
│   └── proxy_url.py       # build_proxy_url/build_proxies_dict: schema URL in base al campo protocol (http/socks4/socks5 -> socks5h) + prefisso user:pass@ opzionale se il proxy porta credenziali, solo stdlib, usato da proxy/ e downloader/; include anche cache_bust_url() (parametro query anti-cache per gli speed test) e sustained_throughput_bps() (misura pura del throughput: finestra del corpo con fallback alla finestra completa sul burst-da-buffer, evita le "bande impossibili")
├── proxy/
│   ├── sources.py         # 74 fonti pubbliche (4 html, 64 plain, 6 json/jsonl); per protocollo: 52 http, 16 socks5, 6 socks4 (campo opzionale "protocol" per fonte)
│   ├── scraper.py         # ProxyScraper.fetch_all() multi-source; _fetch_source etichetta ogni proxy col "protocol" della fonte (sovrascrive l'"http" scritto dai parser)
│   ├── validator.py       # 2-stage (o 3 con selezione per velocità attiva): stage1 alive + stage2 Mega + stage3 opzionale speed test (throughput via sustained_throughput_bps + URL cache-busted, niente più valori impossibili dal burst-da-buffer)
│   ├── pool.py            # ProxyPool score-based round-robin; cooldown() mette un proxy a riposo N secondi (rate-limit 403/509) senza toccare lo score, ma MENTRE è in cooldown NON conta come vivo in size()/_count_alive_unlocked() (solo non selezionabile finché non scade — altrimenti size()>0 mentre get_next() non ha nulla, e il refill viene saltato all'infinito); contatori di sessione per la GUI (discarded_count/refill_count/seconds_since_last_refill, alimentati da note_refill()); ammissione centralizzata in _admit_unlocked() (usata da add_many/refill_blocking) che semina lo score via _seed_score(): dalla cache si ripristina solo la reputazione BUONA e DECADUTA (POOL_SCORE_CACHE_DECAY, metà surplus), mai penalità né morti gonfiati
│   ├── refresher.py       # BackgroundPoolRefresher (thread daemon)
│   └── proxy_cache.py     # cache proxy persistente JSON (hot-start)
├── downloader/
│   ├── mega_crypto.py     # primitive AES-CBC/CTR vendorizzate + decrypt_key() (chiavi dei nodi di una
│   │                     #   cartella condivisa: AES a blocchi INDIPENDENTI da 16 byte, non una CBC unica)
│   ├── mega_api.py        # MegaPublicClient: resolve URL pubblica Mega + `list_folder()` (elenco
│   │                     #   ricorsivo dei nodi di una cartella) + ramo di resolve per i job-cartella
│   │                     #   (`_resolve_folder_node`); `_api_request(payload, extra_params)` permette il
│   │                     #   parametro di QUERY `n=<folder_id>`; backoff dei retry (-3/errore rete) cappato a 30s e INTERROMPIBILE via should_abort (cancellazione cooperativa durante il resolve); nome file sanitizzato alla sorgente
│   ├── mega_folder.py     # espansione di un link cartella in N job-file AUTO-CONTENUTI: elenco nodi
│   │                     #   (1 sola chiamata), decifratura chiavi/attributi, ricostruzione dell'albero,
│   │                     #   sanificazione per segmento + dedup collisioni (anche file-vs-cartella),
│   │                     #   `deduplicate_job_urls()` per la de-collisione GLOBALE fra piu' cartelle
│   │                     #   (nome di radice distinto per share), cap MEGA_FOLDER_MAX_FILES
│   │                     #   (loggato, mai silenzioso). `build_folder_expansion` è puro rispetto alla
│   │                     #   rete (testabile con nodi fabbricati)
│   ├── mega_client.py     # MegaClient seriale (single-stream via proxy); check spazio disco (ensure_free_space) prima del transfer
│   ├── parallel_client.py # ParallelMegaDownloader (coda chunk a dimensione fissa, HTTP Range N parallele); check disco pre-allocazione; file da 0 byte gestito a parte; Retry-After onorato su 403/509/429; should_abort passato al re-resolve
│   ├── worker.py          # DownloadWorker(QThread) — 1 link, N cicli; ramo job-cartella (_folder_job):
│   │                     #   destinazione ad albero senza `ciclo_N` (_cycle_dir), niente rinomina,
│   │                     #   resume sul NOME ESATTO del file (la cartella è condivisa con gli altri job); cartella base rinominata da hash a nome file al primo resolve (_current_base_dir aggiornato da _resolved_cb); riceve output_root (cartella download scelta dall'utente); InsufficientDiskSpaceError = abbandono immediato (non retry)
│   └── orchestrator.py    # DownloadOrchestrator(QObject) — coordina tutto; `add_jobs(links, at_top)`
│                          #   `has_active_workers()` dice se un thread di download è ancora VIVO (non è
│                          #   lo stato dei job: dopo l'annullo globale sono già tutti annullati mentre i
│                          #   .part si scrivono ancora) — lo chiede la finestra Manutenzione;
│                          #   aggiunge link a una sessione GIA' avviata (ritorna i file_id assegnati) e
│                          #   `restart_job` riavvia un job terminato: condividono `_reactivate_session()`,
│                          #   che rimette in moto sessione/ricaricatore/timer (due copie divergerebbero).
│                          #   Gli identificativi li assegna SOLO `_allocate_file_id()`, monotono per tutta
│                          #   la sessione (azzerato da `start()`): entrano nel nome della cartella di
│                          #   destinazione, riusarne uno farebbe scrivere due download nello stesso posto.
│                          #   `_pending_jobs` porta il file_id definitivo gia' prima che i worker partano,
│                          #   cosi' un'aggiunta arrivata durante la raccolta dei proxy sopravvive a
│                          #   `_spawn_workers`, che COSTRUISCE la coda; segnale proxy_stats(discarded, refill_count, seconds_since_last_refill) emesso insieme a pool_size_changed nel poll periodico; propaga output_root ai worker (start(output_root=...)); relay dei canali TIPATI del worker (failed_detail/fatal_detail/abandoned_detail) accanto ai segnali-stringa; `SETUP_TEXTS_IT` + `setup_text_it()` = testo ITALIANO delle 6 righe di stato del setup (serve a log e CLI), emesse su due canali: `setup_status`/`pool_failed` (stringa italiana) e `setup_status_t`/`pool_failed_t` (codice + parametri, per la GUI)
└── gui/
    ├── main_window.py     # MainWindow (QMainWindow); `_on_add_links_requested` e' il gate del
    │                      #   pulsante «Aggiungi link»: fuori sessione riempie la lista da avviare, a
    │                      #   sessione viva accoda a caldo (`_add_links_to_session` ->
    │                      #   `orchestrator.add_jobs`), a coda esaurita chiede prima se proseguire o
    │                      #   ripartire pulito. `_register_added_jobs` ESTENDE la contabilita' (righe,
    │                      #   `_links_by_id`, `_session_incomplete` col salvataggio su disco,
    │                      #   `_expected_files`, `_queue_done_notified`) invece di ricrearla come fa
    │                      #   `_start_with_links`;
    │                      #   _on_start fa da gate: se ci sono link cartella
    │                      #   avvia FolderExpandWorker e il flusso riprende in _start_with_links;
    │                      #   `_begin_folder_expansion(links, hot_position)` serve entrambi i casi: a
    │                      #   caldo la finestra di avanzamento e' NON modale (i download proseguono) e
    │                      #   Avvia NON va riabilitato a fine espansione;
    │                      #   _delete_folder_job_file elimina il SINGOLO file di un job-cartella
    │                      #   (+ .part + sidecar) e pota le cartelle vuote, mai l'albero condiviso; ripristino sessione all'avvio (prompt "Riprendi sessione precedente?" da session_store, differito con QTimer.singleShot); propaga la cartella download scelta a orchestrator.start(output_root=...) e la usa per il delete cartella; _on_language_changed fa il fan-out della ritraduzione su TUTTE le superfici persistenti (gemello di _on_theme_toggle), riga di stato compresa: _set_status_t/_set_status_tn ricordano chiave+parametri in _status_source e _refresh_status la riscrive, mentre _set_status (grezzo) azzera la memoria;
    │                      #   changeEvent intercetta la RIDUZIONE A ICONA e differisce la decisione con
    │                      #   QTimer.singleShot(0) (dentro il gestore dell'evento la finestra sta ancora
    │                      #   cambiando stato): _handle_minimized chiede o applica la preferenza,
    │                      #   _hide_to_tray nasconde finestra E finestre figlie (il dettaglio di un job non
    │                      #   sparisce da solo: misurato), _restore_from_tray le rimette com'erano;
    │                      #   `_open_maintenance_dialog` apre la finestra Manutenzione passandole le due
    │                      #   cose che solo la finestra principale sa: la cartella di download configurata
    │                      #   e `_session_is_running()` — che è `has_active_workers()` OR job non tutti
    │                      #   terminati, perché l'annullo globale marca i job all'istante ma i thread
    │                      #   escono al checkpoint dopo e fino a lì scrivono ancora sui .part;
    │                      #   closeEvent smonta l'icona (fantasma nell'area di notifica) e chiude
    │                      #   l'APPLICAZIONE — serve perché main.py disattiva setQuitOnLastWindowClosed
    ├── link_panel.py      # gestore lista link (nascosto nell'UI, API get_links/set_links/open_paste_dialog);
    │                      #   `confirm_already_downloaded` (storico dei download PASSATI) e
    │                      #   `confirm_session_duplicates` (sessione IN CORSO) sono due controlli distinti
    │                      #   e possono comparire tutti e due: rispondono a domande diverse. Il confronto
    │                      #   passa da `dedup_key()` = handle Mega, con ripiego sull'URL esatto per le
    │                      #   cartelle non espanse; `find_session_duplicates` e' puro (niente Qt); i suoi widget non si vedono, ma i dialoghi che apre sì (import da file, avviso «già scaricati»); i18n: t()/tn() + retranslate(), contatore link al singolare/plurale
    ├── paste_links_dialog.py # dialog modale incolla/edita lista link; contatori Validi/Non validi/Duplicati/Cartelle (i18n: t("paste.*"), conteggi come parametro {n});
    │                      #   con `show_position=True` chiede anche DOVE mettere i link (POSITION_TOP/
    │                      #   POSITION_BOTTOM, letti da `selected_position()`): solo a sessione in corso,
    │                      #   perche' fuori sessione la coda non esiste ancora
    ├── jobs_model.py      # JobsModel (QObject) + Job (throughput/file_name/output_path);
    │                      #   `append_jobs()` e' il gemello di `reset()` che ACCODA senza cancellare
    │                      #   (aggiunta a caldo) e non rinumera nulla: gli id arrivano dall'orchestrator.
    │                      #   NON formatta testo:
    │                      #   la cronologia e' (ts, livello, CHIAVE `job_log.*`, parametri) e `Job.last_error` e'
    │                      #   il payload (codice, parametri) di E1 — rende chi disegna, quindi niente `retranslate()`.
    │                      #   Non e' piu' un QAbstractTableModel: senza view a tabella, `HEADERS`/`data()`/`headerData()`
    │                      #   e le costanti `COL_*` erano superficie morta (testo utente solo all'apparenza) e sono state rimosse
    ├── jobs_panel.py      # lista job a righe-card (QScrollArea + _JobCard widget per riga);
    │                      #   `append_jobs()` aggiunge card senza toccare quelle esistenti (l'ordine resta
    │                      #   cronologico anche per i link messi in TESTA alla coda: chi sta scaricando lo
    │                      #   dice il proprio stato); filtri a pulsanti esclusivi (QButtonGroup), senza etichetta; ogni pulsante mostra il conteggio file per categoria ("In corso (N)"/"Completati (N)"/"Non completati (N)"), aggiornato da _update_filter_counts su aggregates_changed; i18n: retranslate() ricasca su _EmptyState e su ogni _JobCard; le card rendono l'ultimo errore dal PAYLOAD del modello con error_render.render_error(), e on_abandoned applica ABANDON_ALIASES al confine col segnale
    ├── job_detail_dialog.py # dialog non-modale dettaglio job (doppio clic); UNICO dialogo PERSISTENTE del progetto:
    │                      #   ha `retranslate()` ed e' nel fan-out di `_on_language_changed`. `_refresh(force=True)` e'
    │                      #   obbligatorio al cambio lingua: il ridisegno normale salta log e tabella IP quando il NUMERO
    │                      #   di voci non cambia, e cambiando lingua cambia il testo, non il conteggio
    ├── error_render.py    # resa degli errori a video: `render_error(code, params)` da codice+parametri al testo nella
    │                      #   lingua corrente (chiave `err.<codice>`; un codice CON il punto e' gia' una chiave i18n
    │                      #   intera, forma usata dagli errori che nascono nella GUI). Rende in profondita' i payload
    │                      #   annidati di E1 (`cause` -> {error}, `children` -> {detail}), con tetto di ricorsione.
    │                      #   `ABANDON_ALIASES`: il canale `abandoned_detail` porta il codice del canale `failed`
    │                      #   (con le PARENTESI) mentre l'abbandono si legge coi DUE PUNTI — l'alias rimette la
    │                      #   formulazione giusta al confine. `resolve_payloads()` per la riga di stato
    ├── radial_gauge.py    # RadialGauge: anello/donut riusabile (velocita' come % del picco); matematica pura in gauge_fraction() (no Qt, testabile)
    ├── segment_bar.py     # SegmentBar: barra orizzontale a segmenti proporzionali riusabile; matematica pura in segment_widths() (no Qt, testabile)
    ├── format_helpers.py  # helper di formattazione condivisi: fmt_speed/fmt_bytes/fmt_mmss/fmt_hhmmss (puro, no Qt); build_header_summary passa da t() → dipende dalla lingua (le unità di misura no)
    ├── session_clock.py   # SessionClock: tempo sessione con auto-freeze a fine sessione (puro, no Qt/I/O)
    ├── session_speed.py   # SessionSpeedStats: media/picco/minima di sessione (puro, no Qt/I/O), campionato 1x/s da StatsBar
    ├── stats_bar.py       # cruscotto "spinta" compatto: zona velocita' (RadialGauge con % del picco + picco/media/minima/ETA/tempo) e zona Download (totale + SegmentBar + conteggi), separate da una linea verticale interna
    ├── stats_panel.py     # StatsPanel: cruscotto Statistiche collassabile (header riassuntivo sempre visibile + corpo espandibile); metriche: volume, throughput effettivo, media per-download, picco/min, durata con auto-freeze, dettaglio per-job, pulsante copia riepilogo
    ├── proxy_bar.py       # (i18n: retranslate() ricasca su ogni _MetricCard, che tiene la CHIAVE dell'etichetta) ProxyBar: zona proxy in stile "conservativo" — griglia 2x4 di card compatte su due righe (vivi/validazione/scartati/ricariche/ultimo refill/banda/banda proxy; min width 112px = etichetta più lunga non tagliata al resize) + colonna verticale di pulsanti "↻ Banda" (speed test linea diretta), "↻ Banda proxy" (speed test attraverso il pool live, abilitato solo con proxy vivi) e "Reset cache"; popolata da pool_size_changed/setup_progress/proxy_stats dell'orchestrator. Card "Banda" verde (accent_ok) vs "Banda proxy" blu (accent_info) per differenziare le due misure
    ├── speedtest_worker.py # SpeedTestWorker (banda linea diretta, senza proxy) + ProxySpeedTestWorker (banda aggregata del pool live, uno stream per proxy campionato, resiliente ai proxy lenti/caduti); entrambi QThread, emettono finished_test(mbit, ok)
    ├── controls.py        # barra comandi: Avvia/Pausa/Annulla/Paralleli/Incolla/Tema/Info; menu Impostazioni con Paralleli/Limite/Pezzo/"Cartella download:" (QFileDialog, getter get_download_dir, segnale download_dir_changed) + "Lingua:" (QComboBox Automatica/Italiano/English → TR.set_preference); PRIMO pannello migrato a i18n: testi via t("controls.*") e retranslate() per il cambio a caldo
    │                      #   + "Manutenzione:" (pulsante «Azzera dati…» → segnale maintenance_requested,
    │                      #   apre MaintenanceDialog). NB: `set_running(True)` disabilita il pulsante
    │                      #   Impostazioni, quindi a sessione VIVA il menu — e con esso la manutenzione —
    │                      #   non è raggiungibile: il rifiuto per voce serve dopo un Annulla globale,
    │                      #   quando i comandi tornano attivi ma i worker stanno ancora scrivendo
    ├── experimental_dialog.py # ExperimentalFeaturesDialog: 3 controlli con descrizione breve inline e icona "i" (QToolButton) → QMessageBox estesa: "Connessioni per file" (spinbox), "Budget per pezzo (s)" (spinbox), "Selezione per velocità" (checkbox + spinbox soglia KB/s); tutti persistono in preferences.json; i18n: t("experimental.*"), le descrizioni brevi/estese stanno nei dizionari
    ├── folder_expand_worker.py # FolderExpandWorker(QThread): espande i link cartella prima dell'avvio; le righe di report passano da t()/tn() (clausole opzionali autonome: separatore incluso nella chiave)
    │                      #   (rete fuori dal thread GUI); i link non-cartella passano invariati e
    │                      #   nell'ordine originale
    ├── tray.py            # icona nell'area di notifica (QSystemTrayIcon): menu «Mostra la finestra»/«Esci»,
    │                      #   doppio clic, avvisi a comparsa, suggerimento con lo stato. Due funzioni PURE
    │                      #   (testabili senza area di notifica, che la piattaforma Qt offscreen non ha):
    │                      #   `resolve_minimize_action(pref, tray_available)` e `tooltip_text(...)`;
    │                      #   `ask_minimize_target()` è il dialogo modale della domanda alla riduzione.
    │                      #   `TrayController` è INERTE se `isSystemTrayAvailable()` è False (nessuna
    │                      #   condizione nei chiamanti) ed è una superficie PERSISTENTE: ha `retranslate()`
    │                      #   ed è nel fan-out di `_on_language_changed`. I valori di `MINIMIZE_TARGETS`
    │                      #   sono ripetuti in `preferences.py` (importarli sarebbe un ciclo): li tiene
    │                      #   allineati `tests/test_tray.py`
    ├── maintenance_dialog.py # MaintenanceDialog: finestra «Manutenzione» (modale, creata su
    │                      #   richiesta: legge i testi alla costruzione, niente retranslate()).
    │                      #   Cinque caselle TUTTE non spuntate, conteggio+spazio reali accanto a
    │                      #   ognuna, elenco riga per riga prima di cancellare col predefinito su
    │                      #   ANNULLA, resoconto nella finestra + riga INFO nel log. La misura e la
    │                      #   cancellazione stanno in `core/maintenance.py`; la sola cache proxy
    │                      #   passa da `delete_proxy_cache()`, la funzione che esiste già.
    │                      #   `session_running` arriva da MainWindow._session_is_running()
    ├── preferences.py     # carica/salva preferenze utente (tema, lingua GUI ("auto"/"it"/"en"), check aggiornamenti all'avvio, selezione per velocità abilitata + soglia KB/s, stats_panel_expanded, download_dir, minimize_target "ask"/"tray"/"taskbar") in preferences.json
    ├── i18n.py            # motore di traduzione GUI: Translator(QObject) con language_changed(str), singleton di modulo TR (come CURRENT_PALETTE), t(key, **params) e tn(key, n, **params); risolve "auto" dal locale (QLocale → prefisso → it, altrimenti en), persiste via preferences, installa qtbase_<lang>.qm via QLibraryInfo. Chiave mancante in EN → testo IT + WARNING una volta sola; mai eccezione
    ├── strings_it.py      # dizionario piatto IT — è la FONTE del testo utente; INNESTA `ERROR_TEXTS_IT` di
    │                      #   `core/error_catalog.py` come chiavi `err.*` (una sola fonte per l'italiano degli errori,
    │                      #   che serve anche ai log). Direzione `gui -> core`, permessa
    ├── strings_en.py      # dizionario piatto EN — traduzione: stesse chiavi e stessi {parametri} (test di parità in tests/test_i18n.py)
    ├── about_dialog.py    # AboutDialog: nome/acronimo/autore/nick/link/logo (da branding) + licenza + controllo aggiornamenti manuale (i18n: t("about.*"))
    ├── update_check.py    # UpdateCheckWorker(QThread): GET releases/latest GitHub, fuori dal thread GUI
    ├── update_banner.py   # UpdateBanner: barra sottile richiudibile ("nuova versione disponibile"); superficie PERSISTENTE: ha retranslate() e tiene la versione annunciata in _version per riscrivere l'etichetta al cambio lingua
    ├── branding_fetch.py  # BrandingFetchWorker(QThread): GET manifest.json + logo remoti, size-limited, fuori dal thread GUI
    └── style.py           # PALETTE_LIGHT/DARK, CURRENT_PALETTE, build_qss(), apply_theme()

tools/
├── cli_download.py        # runner CLI senza GUI (riusa Orchestrator); flag --selection-mode/--connections/--concurrency/--speed-admission
├── monitor_gui.py         # GUI live monitor velocita' download
├── monitor_speed.py       # CLI polling cartella downloads/
├── analyze_telemetry.py   # analizzatore offline della telemetria scatola nera (sola lettura): CSV + report HTML/MD + export AI; --link-mbit per la % di linea usata
├── report.py              # report HTML diagnostico (sola lettura) da logs/events.jsonl + logs/crash.log
├── pulizia-preferenze.py  # reset dello stato utente da riga di comando (--yes/--dry-run), a
│                          #   programma chiuso. Copre le due voci che la GUI NON tocca di
│                          #   proposito (`preferences.json`, `branding_cache.json`) più le voci
│                          #   condivise, che delega a `core/maintenance.py`: una sola logica di
│                          #   cancellazione, non due copie che divergono
└── demo/
    └── demo_runner.py     # genera video demo + galleria bilingue (IT/EN) per il sito e le release:
                            #   pilota la MainWindow vera via slot Qt reali (nessun mouse simulato),
                            #   registra con ffmpeg (gdigrab), fa scaricare per davvero due link Mega
                            #   dati, produce un taglio a velocita' variabile + screenshot agli eventi.
                            #   `--dry-run` (<5s) valida import/slot/i18n senza eseguire nulla di vero.
                            #   Cittadino di prima classe: tenuto in sync via
                            #   `.claude/rules/demo-runner.md` + `pytest tests/test_demo_runner_smoke.py`.
                            #   La sezione "Contratto con MDPR" in cima al file elenca ESATTAMENTE
                            #   ogni punto della GUI da cui dipende (imports, slot privati, campi di
                            #   `Job`, nessun segnale Qt — lo stato dei job si legge per polling).

scripts/
├── bench_cache.py         # bench cold vs hot start (cache)
├── download_once.py       # CLI one-shot: scarica un link una volta
└── download_n.py          # CLI multi-ciclo: scarica un link N volte

install.ps1                # installer: crea venv, pip install, smoke test, launcher
package.ps1                # packaging: crea dist/MegaProxyRotator-X.Y.Z.zip
```

## Entry point
`src/main.py` → `QApplication` → `setQuitOnLastWindowClosed(False)` → `TR.initialize()` (lingua GUI,
PRIMA della finestra) → `MainWindow` → `DownloadOrchestrator`.
`setQuitOnLastWindowClosed(False)` serve perché nascondere la finestra nell'area di notifica non
uccida il processo: da lì in poi l'uscita è ESPLICITA e passa tutta da `MainWindow.closeEvent`
(sia la X sia la voce «Esci» dell'icona, che chiama `close()`).

## Flusso dati
1. Utente incolla link Mega in `LinkPanel` → clic "Avvia".
1-bis. Se fra i link c'è una **cartella** (`is_folder_link`), `MainWindow._on_start` avvia prima
   `FolderExpandWorker` (QThread): `mega_folder.expand_folder_link()` elenca la cartella UNA volta
   (connessione diretta: a questo punto il pool proxy non esiste ancora) e la espande in job-file
   auto-contenuti. Il flusso riprende in `_on_expansion_done` → `_start_with_links()`.
2. `MainWindow._start_with_links` istanzia `DownloadOrchestrator(SessionState)` e gli passa la lista link.
3. `Orchestrator.start()`: hot-start da `proxy_cache.load()` se disponibile, altrimenti `ProxyScraper.fetch_all()` → `ProxyValidator.validate_against_mega()` → `ProxyPool.add_many()`. Se la selezione per velocità è attiva (preferenze GUI *oppure* flag CLI `--speed-admission` di `tools/cli_download.py`, disaccoppiati), la validazione include uno stage 3 di speed test e il tetto candidati si riduce a 5000. In modalità CLI, `--speed-admission KB/s` ammette solo i proxy oltre la soglia mantenendo la selezione a punteggio normale (nessun cambio del numero di connessioni).
4. Per ogni link viene avviato un `DownloadWorker(QThread)` che esegue `DOWNLOAD_CYCLES` cicli.
5. A ogni ciclo: `ProxyPool.get_next()` → `MegaClient(proxy).get_egress_ip()` → se `PARALLEL_CONNECTIONS_PER_FILE > 1` (default 10) usa `ParallelMegaDownloader.download()`, altrimenti `MegaClient.download()`.
6. Worker emette `progress / ip_logged / cycle_completed / failed / fatal_error / completed_info / all_done / cancelled / abandoned / throughput` → `JobsPanel` (via `JobsModel`). Su `completed_info` l'orchestrator persiste lo storico in `download_history.log` e lo riemette alla GUI per aggiornare nome file e path nelle card.
7. Worker controlla `is_cancelled()` / `wait_if_paused()` su un `_EffectiveSessionState` che combina `SessionState` globale + flag locale (cancellazione per-job).
7-bis. **Aggiunta a caldo**: il pulsante «Aggiungi link» resta attivo durante la sessione.
   `MainWindow._on_add_links_requested` → (eventuale `FolderExpandWorker`, non modale) →
   `_add_links_to_session` → `DownloadOrchestrator.add_jobs(links, at_top)`, che assegna
   identificativi NUOVI e li mette in coda (o in `_pending_jobs`, se il setup sta ancora
   raccogliendo i proxy) senza toccare i worker vivi. La GUI registra le righe con
   `_register_added_jobs`. Il numero di file in parallelo NON cambia: gli aggiunti aspettano
   il loro turno.
8. Cancellazione per-job: utente clicca la X rossa in colonna 0 → `JobsPanel.cancel_job_requested` → `MainWindow` → `DownloadOrchestrator.cancel_job(file_id)`. Se in coda viene rimosso, se in corso `worker.request_cancel()` setta il flag locale e il worker esce al prossimo checkpoint emettendo `cancelled`. La cartella di lavoro (`downloads/<nome_file>_<file_id>/` dopo il rename, oppure `downloads/<sha1>_<file_id>/` se il rename non è ancora avvenuto) viene rimossa lato GUI dopo la terminazione del worker, leggendo `output_path` dal model.

## Convenzioni
- GUI bilingue IT/EN; codice (variabili/funzioni/classi) e commenti in inglese/italiano come già in uso.
  **L'italiano è la fonte** (`gui/strings_it.py`), l'inglese la traduzione (`gui/strings_en.py`).
  Nessuna stringa utente hard-coded: si passa da `t()`/`tn()` di `gui/i18n.py` e si espone
  `retranslate()` per il cambio a caldo. **Traduzione dell'interfaccia COMPLETA**
  (F1 `ControlsBar` + titolo, F2a `UpdateBanner` + dialoghi Info/Sperimentali/Incolla,
  F2b cruscotto con le cascate su `_MetricCard` e `_JobCard`, F2c `link_panel`,
  `folder_expand_worker` e `main_window` con i plurali via `tn()`, E1+E2 errori, cronologia
  del job, dettaglio del job e righe di stato del setup).
  I **log restano in italiano** e non si traducono mai (sono diagnostici e devono restare stabili).
- **Testo utente che nasce fuori dalla GUI**: non viaggia mai come frase già composta, ma come
  **codice + parametri nominati** su un segnale parallelo a quello di sempre. Gli errori usano i
  codici del catalogo (`core/error_catalog.py`, resi con `gui/error_render.render_error`); le
  righe di stato del setup usano i codici `setup.*` di `orchestrator.SETUP_TEXTS_IT`. Il segnale
  gemello che porta la stringa **italiana** resta, ed è quello che alimentano log, telemetria,
  `failed_links.log` e la CLI: chi aggiunge un percorso li emette **entrambi**, altrimenti o la
  GUI mostra testo non traducibile o i log perdono la loro frase.
  Quando una cornice **incorpora un'altra eccezione nostra**, questa viaggia come payload
  (`cause=error_payload(exc)`, o `children=[...]` per una lista) accanto al suo `str(exc)`:
  senza, la GUI in inglese incastona una frase italiana dentro una cornice inglese — e il
  controllo di fedeltà non lo vede, perché in italiano il testo coincide comunque.
- Downloader: pattern `.part` + rename atomico. Si scarica SEMPRE su `<nome>.part` (sidecar `.progress.json` riferito al `.part`, include `chunk_size` per validare compatibilità del resume); `os.replace` sul nome finale solo a download completo e verificato. L'esistenza del nome finale è l'UNICO marker di completamento usato dal check di resume del worker. I `.part` non vanno mai cancellati al cleanup (servono al resume: i chunk completati restano scritti e vengono skippati al retry).
- Pool scoring: i call-site devono registrare anche i successi (`record_success` su segmento completato / IP check ok) e usare `penalize(hard=True)` solo per 503 dal CDN; errori transitori (timeout, throughput basso, connection error) → `penalize(hard=False)`. Mai usare `mark_dead` (alias deprecato).
- Pool cooldown vs penalize: il rate-limit 403/509 dal CDN Mega chiama `pool.cooldown(proxy)`, NON `penalize(hard=True)` — lo score non viene toccato (la reputazione resta intatta) ma il proxy è escluso sia da `get_next()` sia dal conteggio `size()`/`_count_alive_unlocked()` per `PROXY_COOLDOWN_SECONDS` (90s), poi torna selezionabile e contato. Se contasse come vivo mentre è a riposo, `size() > 0` farebbe saltare `refill_blocking(force=False)` anche quando il pool è di fatto inutilizzabile (starvation osservata con quasi tutti i proxy in cooldown insieme).
- URL del proxy (schema): costruire SEMPRE con `build_proxy_url`/`build_proxies_dict` (`core/proxy_url.py`), mai con un f-string a mano — è l'unico punto che sa come mappare `protocol` (http/socks4/socks5) sullo schema giusto (socks5 → `socks5h://`, DNS risolto lato proxy). Richiede la dipendenza `PySocks` (in `requirements.txt`) perché `requests` parli gli schemi `socks4://`/`socks5h://`.
- Sessioni: prima di creare un nuovo `DownloadOrchestrator` chiamare SEMPRE `shutdown()` su quello precedente (teardown worker/refresher/timer); se ritorna False non avviare e mantenere il riferimento (distruggere QThread vivi = crash).
- **Cancellare dati dell'utente**: si passa SEMPRE da `core/maintenance.py` (misura + cancella,
  senza sapere nulla della GUI) e dalle tre regole della superficie — nessuna voce attiva per
  default, elenco esatto di cio' che sparisce PRIMA di procedere, riga nel log DOPO. Un log
  tenuto aperto non si cancella da fuori (su Windows `unlink` fallisce): si tronca con
  `logging_setup.reset_log_file`. Chi cancella file su disco chiede prima `_session_is_running()`:
  con un worker vivo, cartella download e log NON si toccano.
- Comunicazione GUI↔worker SOLO via PyQt signals (mai chiamate dirette dalla GUI ai worker).
- `SessionState` è l'UNICA fonte di verità per pausa/annullo.
- Nuovo proxy source → aggiungere voce in `proxy/sources.py` (campo opzionale `"protocol"`: http/socks4/socks5, default http) + parser dedicato in `scraper.py` se serve un nuovo `kind`.
- **Suffissi di de-collisione**: vanno calcolati accorciando PRIMA il nome per fare posto al
  suffisso (`_suffixed_name` per i file, `_suffixed_folder_name` per le cartelle). Accodare
  ` (n)` a un nome gia' al limite di lunghezza lo fa ritagliare via dalla sanificazione, che
  restituisce di nuovo il nome base: la collisione torna e il ciclo di de-collisione non termina
  piu'. E' successo due volte in questa feature, su file e su cartelle.
- **URL Mega (parsing)**: ogni riconoscimento di forma di link passa da `core/mega_links.py`, mai
  regex nuove sparse nei moduli. L'ordine di match è vincolante (dal più specifico al più generico):
  la forma interna dei job contiene sia `/folder/` sia `/file/` e verrebbe catturata dalle regex
  generiche se testata per ultima. Il `?p=` prima del fragment non è decorativo: impedisce a
  `_FILE_RE` (che vuole `#` subito dopo l'handle) di scambiare un job-cartella per un file pubblico.
- **Chiave di un nodo in una cartella condivisa**: il campo `k` può contenere PIÙ voci
  `<owner>:<blob>` separate da `/`, e l'owner NON coincide necessariamente con l'id della cartella
  nel link (osservato sul campo). Non scegliere "la prima" né "quella col folder_id": provarle tutte
  e tenere quella i cui ATTRIBUTI si decifrano (`decrypt_attr` valida da sé col magic `MEGA{"`).
  Un file la cui chiave non è verificabile va SALTATO: scaricarlo darebbe byte corrotti dopo
  l'AES-CTR, senza alcun errore visibile.
- Nuovo provider cloud (oltre Mega) → nuovo modulo in `downloader/`, mai patch a `mega_client.py`.
- I segnali da QThread alla GUI vanno connessi con `Qt.ConnectionType.QueuedConnection`.

## Anomalie note
- I proxy gratuiti hanno tasso di mortalità ~70%: è normale che `ProxyValidator` scarti la maggioranza.
- mega.py è stato vendorizzato: le primitive crypto e l'API pubblica sono in `src/downloader/mega_crypto.py` e `src/downloader/mega_api.py`. Nessuna dipendenza esterna `mega.py`, nessun conflitto tenacity/pathlib.
- Mega può rate-limitare lo stesso file anche da IP diversi: è atteso, è proprio ciò che il test misura.
- **403/509 dal CDN Mega indica rate-limit del proxy, NON scadenza URL**: un re-resolve dell'URL CDN ritorna sistematicamente lo stesso host. Il proxy va messo in cooldown (`pool.cooldown`, temporaneo: torna in rotazione dopo `PROXY_COOLDOWN_SECONDS`), non marcato dead; il re-resolve va riservato ai casi di URL effettivamente cambiata (es. 503 di overload).
- **429 "Too Many Concurrent IP Addresses" è un limite PER-FILE di Mega** (numero di IP distinti che scaricano lo stesso file contemporaneamente), NON un problema del singolo proxy. In `parallel_client._download_chunk` il 429 NON penalizza e NON fa cooldown: ri-prova lo STESSO proxy (`sticky_proxy`) dopo un backoff (`PARALLEL_HTTP_429_BACKOFF_S/MAX_S`). Cambiare proxy aggiungerebbe un IP e peggiorerebbe il limite (spirale → abbandono). Conseguenza architetturale: aumentare le corsie o concentrare i proxy sullo stesso file regredisce oltre una certa soglia (misurato). I 20 MB/s su file singolo sono limitati da questo tetto + dalla qualità dei free-proxy (vedi `MyDocs/autonomous-mission-report.md`).
- **Elenco di una cartella pubblica: il nodo `t == 2` può mancare del tutto.** Su una cartella reale
  (link di test `lDsUgAAL`, 205 file) la risposta `f` contiene solo nodi `t in (0, 1)`:
  `_resolve_root` scende quindi per fallback (tipo 2 → handle == id del link → nodo senza genitore
  nell'elenco, preferendo una cartella e in modo deterministico).
- L'import di `pycryptodome` (pesante) avviene localmente dentro `MegaClient.download()` e `ParallelMegaDownloader.download()` per non rallentare l'avvio della GUI.
- **Blob attributi Mega: il padding dell'ultimo blocco AES non è sempre zero.** Un file rinominato lato Mega può lasciare residuo di cifratura del nome precedente dopo il terminatore `}` (byte non-zero, osservato su un caso reale). `decrypt_attr` (`mega_crypto.py`) usa `json.JSONDecoder().raw_decode()` per fermarsi al primo oggetto JSON valido invece di pretendere che l'intera stringa decifrata sia JSON: un `json.loads` sull'intera coda falliva con "Extra data" anche a chiave e nome giusti, facendo ripiegare il nome file su `mega_<handle>` (bug corretto). La decodifica è UTF-8 (non più latin-1): preserva i nomi accentati.

## Logging
- Configurato in `core/logging_setup.py`. Tutti i log diagnostici/operativi vivono in `logs/` (vedi `LOGS_DIR`/`REPORTS_DIR` in `core/config.py`); restano in root solo le cache (`proxy_cache.json`, `branding_cache.json`, `branding_logo.*`).
- File human-readable: `logs/app.log` (rotante 5 MB × 3 backup). Livello DEBUG su tutti i moduli; `urllib3` e `requests` capped a WARNING.
- **Log strutturato universale**: `logs/events.jsonl` (JSON Lines, rotante 20 MB × 5 backup, sempre a DEBUG senza filtri a monte). Ogni record di logging viene scritto anche qui via `JsonLinesFormatter` (campi base `ts/level/logger/thread/msg` + ogni attributo `extra={...}` passato dal chiamante). Sorgente primaria per `tools/report.py`.
- `setup_logging()` viene chiamato in `src/main.py` prima della creazione di `QApplication`; crea `logs/` se assente.
- Hook globale `sys.excepthook` cattura le eccezioni non gestite nel thread principale.
- Log dedicati JSONL in `logs/`: `failed_links.log` (link abbandonati), `download_history.log` (download completati, dedup per handle), `proxy_sources_stats.log` (survival per-fonte).
- `logs/terminal-log.txt`: tee grezzo di stdout/stderr della sessione corrente (riazzerato a ogni avvio, mode `"w"`). Diagnostico, non strutturato: contiene le stesse righe viste a video (console handler del logging + eventuali print/tracce).
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
- **`install.ps1` per default installa TUTTO**, non solo l'app: dopo `requirements.txt` installa anche
  `requirements-dev.txt` (serve a `pytest` e a `tools/demo/demo_runner.py`) e verifica/installa **ffmpeg**
  via winget (`Gyan.FFmpeg`, richiesto solo dal demo runner in modalità video — l'app stessa non lo usa;
  se winget manca o l'installazione fallisce, solo un warning bilingue, mai un errore bloccante). Flag
  `-Minimal` salta entrambi (requirements-dev.txt e ffmpeg): solo l'app di base. Lo smoke test finale
  (righe ~245-290) genera la lista dei moduli da importare dall'inventario reale delle dipendenze
  (6 pacchetti di `requirements.txt` + `pytest` se non `-Minimal`), non da una lista hard-coded.
- **Dipendenze "invisibili" a un grep sugli import**: `lxml` e `PySocks` sono runtime reali (dichiarate
  in `requirements.txt`) ma non vengono MAI importate direttamente dal codice del progetto — `lxml` è
  selezionata per nome-parser stringa (`BeautifulSoup(html, "lxml")` in `proxy/scraper.py`), `PySocks`
  è importata internamente da `requests`/`urllib3` quando l'URL del proxy usa uno schema `socks5h://`/
  `socks4://` (costruito in `core/proxy_url.py`). Un audit basato solo su `import` letterali le
  dichiarerebbe erroneamente "non usate": vanno cercate per come sono effettivamente consumate.
- `tools/`, `scripts/` e i test non introducono NESSUNA dipendenza third-party oltre a quelle già in
  `requirements.txt` (più `pytest` da `requirements-dev.txt` per i test): l'unico pacchetto pip
  importato direttamente sotto `tools/` è `PyQt6` (già in `requirements.txt`). Prima di aggiungere un
  nuovo file in quelle cartelle con un import pip nuovo, aggiornare `requirements-dev.txt` (o
  `requirements.txt` se serve anche all'app) e lo smoke test di `install.ps1` nello stesso ciclo.

## Versioning e packaging
- La versione dell'app è definita in `src/core/config.py` come `APP_VERSION` (semver `MAJOR.MINOR.PATCH`).
- `APP_VERSION` viene mostrata nel titolo della finestra principale (`MainWindow`).
- `package.ps1` legge `APP_VERSION` e produce `dist/MegaProxyRotator-X.Y.Z.zip` escludendo `venv`, `dist`, `downloads`, `__pycache__`, `.git`, `.claude`, log e cache.
- L'utente che riceve lo zip esegue `install.ps1` (crea venv + dipendenze) e poi `avvia.bat`
  (avvio silenzioso con `pythonw.exe`) oppure `avvia-debug.bat` (terminale visibile, per capire
  perche' non parte). `install.ps1` genera ENTRAMBI: cambiando uno dei due file in root va
  cambiato anche il testo che l'installer scrive, altrimenti la prossima installazione lo
  riporta indietro. `package.ps1` prende i file da `git ls-files` e fallisce se trova
  `.py`/`.bat` nuovi non tracciati (finirebbero fuori dallo zip).
- **Regola obbligatoria**: al termine di ogni task, chiedere all'utente se vuole aggiornare `APP_VERSION`.

## File da NON modificare senza motivo
- `src/core/state.py` — logica di concorrenza (QMutex + QWaitCondition) delicata; ogni modifica deve preservare gli invariants pausa/annullo.
