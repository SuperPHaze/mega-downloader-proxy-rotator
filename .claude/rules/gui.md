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
  un widget con testo lo aggiunge in **tutti e due** i punti. I dialoghi creati su richiesta
  (`AboutDialog`, `ExperimentalFeaturesDialog`, `JobDetailDialog`, `PasteLinksDialog`) non ne
  hanno bisogno: leggono i testi alla costruzione.
- Non si traducono: unità di misura (`"32 MB"`, `"MB/s"`), emoji/icone e la spaziatura di
  impaginazione (resta nel codice, non nei dizionari), e i nomi delle lingue nel selettore
  (`Italiano`/`English` sono uguali nei due dizionari).
- **I log restano in italiano**: sono diagnostici e devono restare stabili nel tempo. Non passare
  mai un testo tradotto a `log.*`, e non "completare il lavoro" traducendoli.
- **Migrazione in corso** (piano: `MyDocs/i18n-gui-2.0.0-design.md`): F1 ha convertito
  `ControlsBar` e il titolo della finestra; F2a `UpdateBanner` (persistente, con
  `retranslate()`) e i dialoghi `about_dialog`/`experimental_dialog`/`paste_links_dialog`
  (creati su richiesta, nessun `retranslate()`); F2b `proxy_bar`, `stats_bar`, `stats_panel`,
  `jobs_panel` e `format_helpers`, con le due CASCATE: `retranslate()` di `ProxyBar` ricasca su
  ogni `_MetricCard` e quello di `JobsPanel` su `_EmptyState` e su ogni `_JobCard`, esattamente
  dove ricasca `refresh_theme()`. Restano in italiano hard-coded `link_panel`,
  `folder_expand_worker` e `main_window` (F2c). **`jobs_model` e `job_detail_dialog` sono
  fuori dal percorso F2**: i loro testi sono cronologia e messaggi d'errore che nascono in
  `core/`/`downloader/`, e vanno affrontati insieme nella fase «Errori & Cronologia» (con
  codici d'errore). Se tocchi un file ancora da migrare, convertilo invece di aggiungere
  altre stringhe fisse.
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
- `JobsPanel` è una **lista a righe-card**: `QScrollArea` con un widget `_JobCard` per job (ha
  sostituito la vecchia `QTableView`). `JobsModel` resta la fonte dati e le sue colonne sono
  definite in `jobs_model.py` come costanti `COL_*`; **non usare indici letterali**.
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
