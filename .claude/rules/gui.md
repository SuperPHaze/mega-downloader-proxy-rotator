---
paths: ["src/gui/**/*.py"]
---

# Regole per il layer GUI

## Toolkit
- SOLO PyQt6. Niente Tkinter, niente PySide6, niente wxPython.
- Importare i widget da `PyQt6.QtWidgets`, i tipi core da `PyQt6.QtCore`.

## Lingua
- TUTTE le stringhe visibili all'utente (label, placeholder, titoli finestra, messaggi di errore, status bar) devono essere in italiano.
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
