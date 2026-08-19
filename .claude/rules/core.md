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

## Errori che l'utente legge (errors.py + error_catalog.py)
- **Ogni eccezione user-facing nasce con un CODICE**, non con una frase. Si solleva
  `MegaApiError("url_not_parsable", url=url)`, mai `MegaApiError(f"URL non parsabile: {url}")`:
  il testo italiano vive in `core/error_catalog.py`, il codice e' l'identificatore stabile che
  sopravvive alla riscrittura del testo ed e' cio' che la GUI traduce.
- **`str(exc)` resta la frase ITALIANA**, prodotta dal catalogo. E' la proprieta' che tiene in
  piedi tutto il resto: i `f"...({exc})"` sparsi nel worker, nei log, nella telemetria e nella
  concatenazione degli errori di chunk continuano a funzionare identici. Non toccarla.
- **I log ricevono l'italiano da `str(exc)`**, sempre, anche con l'interfaccia in inglese. Mai
  passare a `log.*` un testo che e' passato da `t()` della GUI. La garanzia strutturale e' che
  `core/` e `downloader/` non importano `src.gui` (c'e' un test che lo verifica).
- **Parametri sempre nominati** (`{url}`, `{words}`), mai posizionali: in inglese l'ordine della
  frase cambia. Gli specificatori di formato (`{required:,}`, `{kbps:.1f}`) fanno parte del testo
  e vanno riprodotti nel catalogo, altrimenti il messaggio cambia.
- **`format_it()` non solleva MAI**: gira dentro la gestione degli errori, dove un'eccezione
  maschererebbe l'errore vero. Codice sconosciuto -> si usa il codice come testo; parametri che
  non combaciano -> si mostra il template. Chi la modifica mantenga questa proprieta'.
- **Le basi miste vogliono `UserFacingError` per PRIMO**
  (`class UserFacingOSError(UserFacingError, OSError)`). Con `OSError` davanti, il suo `__new__`
  intercetta la costruzione e l'eccezione muore con «takes no keyword arguments». L'ordine non e'
  estetico: e' l'unico che funziona.
- **Aggiungere una base non deve cambiare quale `except` cattura l'eccezione**: i rami di
  `worker.py` distinguono fatale / abbandono / ritenta proprio sulle classi. Se serve un
  `except UserFacingError`, va messo DOPO quelli specifici, mai prima.
- Un codice nuovo va aggiunto al catalogo *e* usato: `tests/test_error_catalog.py` fallisce sia
  sui codici morti sia sui `raise` user-facing rimasti con un testo scritto a mano.

## Dipendenze
- `core/` può importare solo dalla stdlib e da PyQt6.
- Vietato importare da `src.proxy`, `src.downloader`, `src.gui` qui dentro: il core è la base.
