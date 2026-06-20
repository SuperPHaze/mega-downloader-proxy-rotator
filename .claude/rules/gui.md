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
- `MainWindow` assembla in colonna: `LinkPanel`, `ControlsBar`, `StatsBar`, `JobsPanel`, `LogView`.
- `JobsPanel` è una `QTableView` su `JobsModel`. Le colonne sono definite in `jobs_model.py` come costanti `COL_*`; **non usare indici letterali**, aggiornare le costanti se si aggiungono/spostano colonne.
  - `COL_ACTION = 0` ospita la X rossa di cancellazione (delegate `DeleteButtonDelegate`). Click → `JobsPanel.cancel_job_requested(file_id, True)` se job attivo, `delete_folder_requested(file_id)` se job terminato.
- Status bar (`QStatusBar`) per messaggi brevi (stato del pool, pausa, annullo, errori non bloccanti).
- `QMessageBox` per errori bloccanti che richiedono attenzione (es. nessun link inserito) e per conferme distruttive (eliminazione cartella di job terminati).
