---
paths: ["src/core/**/*.py"]
---

# Regole per il layer core

## SessionState (state.py)
- È condiviso fra GUI e tutti i `DownloadWorker`: DEVE restare thread-safe.
- Implementato con `threading.Lock`/`threading.Condition` (stdlib), NON con `QMutex`/`QWaitCondition`:
  sotto alta concorrenza (decine di thread Python puri in un `ThreadPoolExecutor`, non `QThread`)
  le primitive Qt hanno causato un access violation nativo intermittente in `is_cancelled()`.
- Ogni accesso a `_paused`, `_cancelled`, `_running` passa attraverso `self._lock`.
- `wait_if_paused()` usa `threading.Condition.wait()` per non fare busy-wait.
- `cancel()` deve fare `notify_all()` per sbloccare worker in pausa che altrimenti resterebbero appesi.
- Non aggiungere stato applicativo qui (es. lista link, contatori): tenerlo nell'orchestrator.

## config.py
- SOLO costanti. Nessuna funzione, nessuna classe, nessun side effect a import-time (a parte la creazione di `Path` literal).
- Modificare una costante qui significa cambiare comportamento globale: documentare il perché nel commit.
- `APP_VERSION` (semver `"MAJOR.MINOR.PATCH"`): è la versione dell'app, usata da `package.ps1` per il nome dello zip distribuibile. Aggiornarla solo su conferma esplicita dell'utente.

## events.py
- `EventBus` è opzionale e attualmente non usato dal flusso principale (i segnali viaggiano direttamente sui worker).
- Se viene usato, i subscriber lo trattano come read-only: si ABBONANO al segnale `event`, non chiamano metodi sull'EventBus per modificare stato.
- Mai usare `EventBus` come canale GUI → worker: per quello c'è `SessionState`.

## Dipendenze
- `core/` può importare solo dalla stdlib e da PyQt6.
- Vietato importare da `src.proxy`, `src.downloader`, `src.gui` qui dentro: il core è la base.
