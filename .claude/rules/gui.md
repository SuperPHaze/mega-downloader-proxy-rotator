---
paths: ["src/gui/**/*.py"]
---

# Regole per il layer GUI

## Toolkit
- SOLO PyQt6. Niente Tkinter, niente PySide6, niente wxPython.
- Importare i widget da `PyQt6.QtWidgets`, i tipi core da `PyQt6.QtCore`.

## Lingua
- **GUI bilingue IT/EN.** Nessuna stringa visibile all'utente (label, placeholder, titoli finestra,
  messaggi di errore, tooltip, status bar) va scritta hard-coded: si passa SEMPRE da
  `t("<superficie>.<elemento>")` / `tn(...)` di `gui/i18n.py`, con la voce aggiunta in
  **entrambi** i dizionari `gui/strings_it.py` (fonte) e `gui/strings_en.py` (traduzione).
- **Chiavi**: slug stabile `"<superficie>.<elemento>"`, mai la stringa italiana come chiave
  (cambiare il testo IT non deve invalidare la traduzione EN). **Parametri sempre nominati**
  (`{name}`, `{path}`): in inglese l'ordine delle parti della frase cambia.
- **Cambio a caldo**: ogni superficie persistente espone `retranslate()` — l'elenco dei
  `setText`/`setToolTip` che il costruttore già esegue, richiamato anche da
  `MainWindow._on_language_changed`. È il gemello di `refresh_theme()` per il tema; chi aggiunge
  un widget con testo lo aggiunge in **tutti e due** i punti. I dialoghi **modali** creati su
  richiesta (`AboutDialog`, `ExperimentalFeaturesDialog`, `PasteLinksDialog`) non ne hanno
  bisogno: nascono, si leggono e si chiudono. **`JobDetailDialog` sì**: non è modale e resta
  aperto mentre il download prosegue, quindi è una superficie persistente a tutti gli effetti
  (`MainWindow._retranslate_open_details` lo ricasca su tutti i dettagli aperti).
- **Ridisegno «solo se cambia il conteggio» e cambio lingua**: dove `_refresh()` salta la
  ricostruzione quando il numero di elementi non è cambiato (log e tabella IP di
  `JobDetailDialog`, corpo di `StatsPanel`), il `retranslate()` deve chiamarlo con `force=True`.
  Al cambio lingua cambia il **testo**, non il conteggio: senza il `force` la superficie resta
  nella lingua vecchia fino al prossimo evento, ed è un difetto che a video non si nota subito.
- Non si traducono: unità di misura (`"32 MB"`, `"MB/s"`), emoji/icone e la spaziatura di
  impaginazione (resta nel codice, non nei dizionari), e i nomi delle lingue nel selettore
  (`Italiano`/`English` sono uguali nei due dizionari).
- **I log restano in italiano**: sono diagnostici e devono restare stabili nel tempo. Non passare
  mai un testo tradotto a `log.*`, e non "completare il lavoro" traducendoli.
- **Plurali**: quando il testo cambia con un conteggio si usa `tn(chiave, n, ...)` e la voce
  diventa un dict `{"one": ..., "other": ...}` in **entrambi** i dizionari. `tn()` passa `n` da
  se': la chiave lo scrive come `{n}` senza che il chiamante lo ripeta. Se nella frase compare
  anche un altro numero (il progressivo del file), quello si chiama `{file}`: `{n}` è riservato
  al conteggio che sceglie la forma, altrimenti i due si sovrascrivono.
  I singolari italiani sono stati corretti in **F3** («1 sottocartella», «1 file pronto»): fino
  ad allora ripetevano il plurale, difetto preesistente che le fasi di traduzione avevano tenuto
  invariato di proposito per non cambiare il testo IT mentre si migrava. Restano con `one`
  identico a `other` solo le voci in cui la parola italiana è davvero invariabile («1 file»,
  «1 link») e le `err.*`, il cui testo viene dal catalogo del motore ed è anche il testo dei LOG:
  `test_no_italian_plural_entry_repeats_itself` blocca l'elenco delle eccezioni ammesse.
- **Testo composto per concatenazione**: non si traduce a pezzi. Una frase costruita con `+` o
  con f-string spezzate diventa **una chiave sola con parametri nominati** (un frammento come
  « dalla cartella scaricata?» non ha senso da solo). Fanno eccezione le clausole opzionali
  che restano autonome anche isolate e includono il proprio separatore (le code della riga di
  report in `folder_expand_worker`): l'alternativa sarebbe una chiave per ogni combinazione.
- **Riga di stato della finestra**: `MainWindow._set_status_t()` / `_set_status_tn()` memorizzano
  chiave e parametri in `_status_source`, così `_refresh_status()` la riscrive al cambio lingua.
  Un parametro può essere il **payload** di un errore (`{"code": ..., "params": ...}`) invece di
  un testo: `resolve_payloads()` lo rende al disegno, così cornice e contenuto cambiano lingua
  insieme — memorizzando il testo già reso, la cornice si tradurrebbe e l'errore no.
  Non esiste più un `_set_status()` grezzo: con E2 anche le righe che nascono nell'orchestrator
  arrivano come codice + parametri, quindi ogni testo della riga di stato ha una chiave.
- **Errori e cronologia dei job**: `jobs_model` è un **modello di dati e non formatta testo** —
  la cronologia è `(ts, livello, chiave `job_log.*`, parametri)` e `Job.last_error` è il payload
  `(codice, parametri)`. Chi disegna rende con `t()`/`gui/error_render.render_error()`; per
  questo `JobsModel` non ha (e non deve avere) un `retranslate()`. Chi aggiunge una voce di
  cronologia aggiunge una **chiave**, mai una frase.
- **Codici d'errore che nascono nella GUI** (es. i due messaggi che `main_window` passa a
  `mark_failed_fatal`): si passa la **chiave i18n intera**, col punto
  (`"main_window.restart_refused"`). `render_error` distingue dal punto: senza punto è uno slug
  del catalogo del motore e diventa `err.<slug>`, con il punto è già una chiave. Così anche
  questi errori seguono la lingua invece di restare congelati al momento in cui sono nati.
- **Traduzione dell'interfaccia COMPLETA** (piani: `MyDocs/i18n-gui-2.0.0-design.md` e
  `MyDocs/errori-cronologia-2.0.0-design.md`): F1
  `ControlsBar` e titolo della finestra; F2a `UpdateBanner` (persistente, con `retranslate()`) e
  i dialoghi `about_dialog`/`experimental_dialog`/`paste_links_dialog` (creati su richiesta,
  nessun `retranslate()`); F2b `proxy_bar`, `stats_bar`, `stats_panel`, `jobs_panel` e
  `format_helpers`, con le due CASCATE: `retranslate()` di `ProxyBar` ricasca su ogni
  `_MetricCard` e quello di `JobsPanel` su `_EmptyState` e su ogni `_JobCard`, esattamente dove
  ricasca `refresh_theme()`; F2c `link_panel` (persistente), `folder_expand_worker` (testi
  transienti del report) e `main_window` (dialoghi + riga di stato).
  Fase «Errori & Cronologia»: **E1** ha messo i codici sotto agli errori nel motore, **E2** li
  rende nella GUI — `jobs_model` (cronologia come chiavi), `jobs_panel` (la card rende il
  payload), `job_detail_dialog` (l'unico dialogo persistente), i due messaggi che `main_window`
  passa a `mark_failed_fatal` e le 6 righe di stato del setup proxy.
- Nomi di variabili, funzioni, classi, file e segnali in inglese.
- I commenti del codice sono in italiano.

## Concorrenza
- Mai bloccare il thread GUI: nessuna chiamata di rete, scraping, validazione o download dentro slot della GUI.
- Tutto il lavoro pesante gira in `QThread` (vedi `DownloadWorker`) o nell'orchestrator.
- I segnali emessi dai worker vanno connessi alla GUI con `Qt.ConnectionType.QueuedConnection` per attraversare correttamente il confine tra thread.

## Comunicazione coi worker
- La GUI parla coi worker SOLO tramite:
  - segnali Qt (worker → GUI)
  - `SessionState` (GUI → worker, per pausa/annullo globali)
  - `DownloadOrchestrator.cancel_job(file_id)` (GUI → orchestrator → `worker.request_cancel()`, per cancellazione per-job)
- Mai chiamare metodi di un worker direttamente dalla GUI (`worker.do_something()` è vietato): la cancellazione per-job passa SEMPRE dall'orchestrator.

## Layout
- `MainWindow` assembla in colonna: `UpdateBanner`, `ControlsBar`, la riga cruscotto
  (`StatsBar` | separatore verticale | `ProxyBar`), `StatsPanel`, `JobsPanel`. `LinkPanel` NON è nel
  layout: è un gestore senza superficie propria (API `get_links`/`set_links`/`open_paste_dialog`),
  pilotato dal pulsante Incolla della `ControlsBar`.
- **Lo stato di un job si rende con `jobs_panel.status_label()`**, mai col valore grezzo del
  modello (`job.status` vale `"in_corso"`, non «In corso»). La mappa stato→chiave è una sola e
  vive in `jobs_panel`: la usano il badge della card e il riepilogo di `JobDetailDialog`. Una
  seconda mappa sarebbero due elenchi da tenere allineati a mano.
- `JobsPanel` è una **lista a righe-card**: `QScrollArea` con un widget `_JobCard` per job (ha
  sostituito la vecchia `QTableView`). `JobsModel` resta la fonte dati e si legge con
  `get_job()`/`jobs_iter()`/`aggregates()`: **non è più un `QAbstractTableModel`** (niente
  colonne, niente `data()`, niente `dataChanged`) perché senza view a tabella quell'API non
  aveva più un chiamante. Gli aggiornamenti passano da `job_updated(file_id)` e
  `aggregates_changed()`.
- Ogni card porta i propri comandi (annulla, apri cartella, riavvia, copia URL): non ci sono piu'
  delegate di cella. Click sull'annullo → `JobsPanel.cancel_job_requested(file_id, True)` se il job
  è attivo, `delete_folder_requested(file_id)` se è terminato.
- Status bar (`QStatusBar`) per messaggi brevi (stato del pool, pausa, annullo, errori non bloccanti).
- `QMessageBox` per errori bloccanti che richiedono attenzione (es. nessun link inserito) e per conferme distruttive (eliminazione cartella di job terminati).
- **Eliminare un job nato da un link cartella cancella SOLO quel file** (+ `.part` + sidecar) e pota
  le cartelle rimaste vuote: l'albero è condiviso con gli altri file della stessa cartella Mega, un
  `rmtree` cancellerebbe roba altrui. Vedi `_delete_folder_job_file` in `main_window.py` e la regola
  d'area `downloader.md`.

## Thread di GUI e chiusura della finestra
Oltre ai worker dell'orchestrator, la `MainWindow` possiede dei `QThread` propri per il lavoro di
rete che non appartiene a una sessione di download: `UpdateCheckWorker`, `SpeedTestWorker`,
`ProxySpeedTestWorker`, `FolderExpandWorker`.

- Ogni thread di GUI va **atteso in `closeEvent`** con un `wait(<timeout>)`: distruggere un `QThread`
  ancora vivo fa crashare l'applicazione.
- Se lo slot collegato può aprire un dialogo, chiama **`blockSignals(True)` PRIMA di attendere**: a
  finestra che si sta chiudendo, un `QMessageBox` che compare è un bug, non un avviso.
- Un thread annullabile espone `request_cancel()` + `is_cancelled()`; l'annullamento richiesto
  dall'utente non è un errore e non deve produrre popup.

## Fasi di rete prima della sessione
Alcune azioni fanno rete **prima** che l'orchestrator esista (es. l'espansione di un link cartella
in `_on_start`, prima di `_start_with_links`). In quella finestra temporale:
- disabilita **solo Avvia** con `ControlsBar.set_start_enabled(False)`, **non** `set_running(True)`:
  Pausa e Annulla agiscono su `SessionState`, che qui non c'è ancora, e mostrarli attivi mente
  all'utente;
- dai comunque una via d'uscita (es. `QProgressDialog` con Annulla cablato su `request_cancel()`):
  senza sessione, i comandi globali non possono fermare nulla.
