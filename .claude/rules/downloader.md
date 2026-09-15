---
paths: ["src/downloader/**/*.py"]
---

# Regole per il layer downloader

## Errori: codice, non frase
- Ogni `raise` che l'utente puo' leggere passa da un **codice** del catalogo
  (`core/error_catalog.py`) piu' parametri nominati: vedi `rules/core.md`. `MegaApiError`,
  `MegaFolderError`, `MegaCryptoDependencyError` e le tre basi `UserFacing*Error` lo portano gia'.
- **`str(exc)` resta la frase italiana**: e' quello che finisce nei log e dentro le stringhe che
  lo incorporano (`worker.py`, l'aggregato dei chunk in `parallel_client.py`).
- Restano senza codice **solo** le violazioni di contratto interno (parametri obbligatori
  mancanti): non sono errori d'uso, se un utente le vede e' un bug nostro. Se ne aggiungi una,
  il test di copertura te lo fa notare: o e' user-facing e va codificata, o va dichiarata li'.
- I segnali `failed_detail` / `fatal_detail` / `abandoned_detail` di `DownloadWorker` portano
  `code` + `params` **accanto** ai segnali di sempre, che continuano a portare la stringa
  italiana. Chi aggiunge un percorso d'errore emette entrambi, altrimenti la GUI ricasca sul
  testo grezzo e quell'errore non sara' traducibile.
- **Un'eccezione NOSTRA incorporata in una cornice viaggia come PAYLOAD, non come frase.**
  Dove i parametri di una cornice contengono `str(exc)` e `exc` e' una `UserFacingError`, va
  passato anche `"cause": error_payload(exc)` (cosi' fanno `download_failed_paren`,
  `config_error`, `disk_full_short`). Il testo resta identico — `format_it` ignora il parametro
  in piu' — ma senza il payload la GUI in inglese mostra una cornice inglese attorno a un
  errore italiano, e il controllo di fedelta' NON se ne accorge (in italiano il testo coincide
  comunque). Stessa cosa per una LISTA di cause: `chunks_failed` porta `children`.
  Se `exc` viene da una libreria (`requests`, `OSError`), il payload non serve: il suo testo e'
  gia' inglese e resta tale in tutte e due le lingue.

## Mega API e proxy (post-vendoring)
- `mega.py` NON è più una dipendenza. Le primitive crypto (`mega_crypto.py`) e l'API pubblica (`mega_api.py`) sono vendorizzate localmente.
- `MegaPublicClient` (in `mega_api.py`) risolve un link pubblico Mega via API `cs?g=1` ritornando handle, URL CDN, dimensione, nome file decifrato. Usa `requests.Session` per-istanza con `session.proxies` nativi: nessun monkey-patch globale, nessun `threading.local`. Retry esplicito su `-3` (EAGAIN) bounded a 5 tentativi.
- `mega_crypto.py` espone solo helper puri (no I/O, no stato globale): `base64_to_a32`, `a32_to_str`, `base64_url_decode`, `decrypt_attr` (AES-CBC sugli attributi), `derive_file_key` (split chiave a 8 word → k+iv per AES-CTR del payload).
- `MegaClient` (in `mega_client.py`) usa `MegaPublicClient` per il resolve e `requests.get(stream=True)` per il transfer; decifra a blocchi con AES-CTR direttamente sul file finale (nessun temp file, nessun WinError 32 da gestire).
- L'import di `pycryptodome` resta locale dentro `MegaClient.download()` / `ParallelMegaDownloader.download()` per non rallentare l'avvio della GUI.
- Se l'import di `Crypto` fallisce, sollevare `MegaCryptoDependencyError` (errore d'ambiente permanente, non transitorio): il worker lo cattura PRIMA di `Exception` e non chiama `mark_dead()` sul proxy innocente.

## Link a cartella Mega (`/folder/`)
- Un link cartella NON è scaricabile com'è: `mega_api._parse_url` lo rifiuta con un messaggio
  esplicito. Va prima ESPANSO in job-file auto-contenuti (`mega_folder.expand_folder_link`).
- L'espansione avviene UNA sola volta per cartella, prima dell'avvio dei worker. Mai ri-elencare
  la cartella a ogni retry: moltiplicherebbe le chiamate API e imporrebbe una cache condivisa fra
  thread. Ogni job deve essere self-describing come già lo è un link a file singolo.
- Forma interna del job (costruita/riconosciuta SOLO da `core/mega_links.py`):
  `https://mega.nz/folder/<folder_id>/file/<node>?p=<b64url(rel_path)>&s=<byte>#<chiave_8_word>`.
  Il job resta una STRINGA: `session_store`, `download_history` e `worker` non cambiano contratto.
  `&s=` e' la dimensione attesa: il worker la confronta con quella del file gia' presente prima
  di dichiararlo completo. Senza, un file OMONIMO lasciato da un'altra cartella Mega (nell'albero
  il path e' stabile fra le sessioni) verrebbe scambiato per il nostro e il download risulterebbe
  completato senza aver scaricato niente. `&s=` e' opzionale in lettura (job vecchio stile).
- Richiesta `g` per un nodo di cartella: `n` ha DUE significati diversi nella stessa chiamata —
  handle del NODO nel payload, id della CARTELLA nella query (`_api_request(..., extra_params)`).
  Non è un refuso: documentarlo se si tocca quel codice.
- Il nome del file di un job-cartella viene dal job, NON dagli attributi della risposta `g`: è già
  stato sanificato e de-collisionato in espansione, e il path su disco deve restare stabile fra i
  retry.
- `decrypt_key` (in `mega_crypto.py`) decifra a blocchi INDIPENDENTI da 16 byte (ECB). Una singola
  CBC su 32 byte sbaglierebbe il secondo blocco: è l'errore classico nell'implementare le cartelle.

## Layout su disco dei job-cartella
- Albero: `<output_root>/<Nome cartella Mega>/<sottocartelle>/<file>` — niente suffisso
  `_<file_id>`, niente livello `ciclo_N` (`DownloadWorker._cycle_dir`).
- La cartella è CONDIVISA con gli altri file dello stesso albero. Conseguenze vincolanti: il check
  di resume deve guardare il NOME ESATTO del file (non "un file finale qualsiasi nella cartella"),
  e la pulizia dei temporanei `megapy_*` va saltata (non sono nostri).
- Cancellare/eliminare un job-cartella rimuove SOLO quel file (+ `.part` + sidecar) e pota le
  cartelle rimaste vuote fino alla radice dei download esclusa: mai `rmtree` dell'albero condiviso.
- **Due job non possono condividere la destinazione su disco.** La de-collisione dentro una
  cartella la fa `build_folder_expansion`; quella GLOBALE (piu' cartelle nello stesso avvio) la fa
  `deduplicate_job_urls`, chiamata dal `FolderExpandWorker` perche' e' l'unico punto che vede
  l'insieme completo dei job. Tre casi coperti: stesso nodo incollato due volte (si scarta il
  doppione), due share diverse con lo stesso nome di radice (la seconda va in `<nome> (2)`, cosi'
  gli alberi non si mescolano), file che si chiamerebbe come una cartella sorella (vince la
  cartella). I link a FILE SINGOLO passano invariati: i loro duplicati sono leciti (finiscono in
  cartelle distinte grazie al suffisso `_<file_id>`) e li governa la checkbox «Consenti duplicati».
- Il suffisso di de-collisione va calcolato con il BUDGET di lunghezza del nome
  (`_suffixed_name` per i file su `MAX_FILE_NAME_LEN`, `_suffixed_folder_name` per le cartelle su
  `_TREE_SEGMENT_MAX_LEN`): accodarlo e basta lo farebbe ritagliare via dalla ri-sanificazione a
  valle, riportando la collisione e mandando il ciclo di dedup in LOOP INFINITO.

## Segnali emessi da DownloadWorker
Tutti i segnali hanno `file_id: int` come primo parametro per permettere alla GUI di indirizzare l'update:
- `progress(file_id, ciclo, percent)` — `percent` in 0..100
- `ip_logged(file_id, ciclo, ip)` — IP uscente catturato via `IP_CHECK_URL`
- `cycle_completed(file_id, ciclo)`
- `failed(file_id, ciclo, motivo)` — il worker prosegue col ciclo successivo
- `fatal_error(file_id, motivo)` — errore permanente d'ambiente (es. `MegaCryptoDependencyError`): il worker termina senza emettere `all_done`. L'orchestrator libera lo slot.
- `all_done(file_id)` — emesso una sola volta a fine ciclo N
- `completed_info(file_id, url, file_name, file_size, path)` — metadati del download riuscito, emesso UNA volta subito prima di `all_done`. `file_size` è tipato `object` per non troncare file > 2 GB. L'orchestrator lo persiste in `download_history.log` (JSONL, dedup per handle Mega).
- `cancelled(file_id)` — emesso SOLO in caso di cancellazione locale per-job (flag `_local_cancelled`), MAI per annullo globale (gia' coperto da `SessionState`). Permette all'orchestrator di liberare lo slot e alla GUI di rimuovere la cartella di lavoro.
- `abandoned(file_id, url, attempts, last_error)` — emesso quando il cap `MAX_ATTEMPTS_PER_FILE` viene raggiunto: l'orchestrator persiste l'evento in `failed_links.log` (JSONL) e libera lo slot.

## Cancellazione per-job
- `DownloadWorker.request_cancel()` setta solo il flag locale `_local_cancelled`. Non emette nulla direttamente.
- I checkpoint del worker e il `ParallelMegaDownloader` non leggono `session_state` direttamente: usano `_EffectiveSessionState`, che fa OR fra flag locale e stato globale. Quando si aggiunge un nuovo checkpoint nel worker, usare `self._effective_state`, mai `self.session_state`.
- Il segnale `cancelled` viene emesso nel `finally` di `run()` e solo se `_local_cancelled and not session_state.is_cancelled()`.
- La formula del path di output di un job (`downloads/<sha1(url)[:12]>_<file_id>/`) e' centralizzata in `worker.job_output_dir(url, file_id)`: usare quella funzione, non duplicare l'hashing.

## Identificativi dei job: mai riusati

- Il `file_id` lo assegna **solo** `DownloadOrchestrator._allocate_file_id()`, un contatore
  monotono azzerato esclusivamente da `start()` (che apre una sessione nuova, dove anche la GUI
  ricrea le righe da zero). Nessun altro punto deve calcolarlo, e in particolare **mai** con un
  `enumerate()` sulla lista corrente: due infornate di link darebbero gli stessi numeri.
- **Non e' un dettaglio estetico**: il `file_id` entra nel nome della cartella di destinazione
  (`downloads/<sha1(url)[:12]>_<file_id>/`, vedi `worker.job_output_dir`) ed e' la chiave con cui
  la GUI indirizza righe, dialoghi di dettaglio e cancellazioni. Riusarne uno fa scrivere due
  download nello stesso posto e fa aggiornare la riga sbagliata.
- Il contatore **sopravvive** ad annullamenti e riavvii dei job: `restart_job` riusa di proposito
  il PROPRIO identificativo (stesso job, stessa cartella, resume dei `.part` gia' scritti), non ne
  chiede uno nuovo.

## Aggiungere job a una sessione gia' avviata

- `add_jobs(links, at_top=False)` accoda a caldo e ritorna gli identificativi assegnati, cosi' la
  GUI puo' registrare le righe corrispondenti. `restart_job` e `add_jobs` sono la stessa operazione
  a meno dell'identificativo: la riattivazione di sessione, ricaricatore e timer sta in
  `_reactivate_session()`, punto unico condiviso. Se ne nascono due copie, divergono.
- **Due finestre temporali, non una.** Prima che i worker partano la coda non esiste: e'
  `_spawn_workers` a COSTRUIRLA da `_pending_jobs`, quindi un link aggiunto mentre il setup
  raccoglie i proxy va messo li' dentro, non in `_queue` (che verrebbe sovrascritta). Dopo, va
  nella coda vera. E' il difetto piu' probabile di questa funzione e si manifesta come
  "ho aggiunto un link e non e' mai partito": `tests/test_orchestrator_add_jobs.py` lo sorveglia.
- **Niente thread e niente lucchetti.** `add_jobs`, `restart_job`, `cancel_job` e `_on_slot_freed`
  arrivano tutte dal filo dell'interfaccia tramite segnali accodati: la coda non e' condivisa con
  altri thread e non va protetta.
- Quando la coda si svuota, `_on_slot_freed` spegne ricaricatore e timer. Un'aggiunta subito dopo
  deve rimetterli in moto — e' esattamente quello che fa `_reactivate_session()`.

## Contratto con SessionState
- Prima di ogni step potenzialmente lungo: `if session_state.is_cancelled(): return` poi `session_state.wait_if_paused()`.
- Il worker NON deve mai mettere in pausa o cancellare se stesso — può solo OSSERVARE lo stato.
- Il worker NON deve emettere `all_done` se è stato cancellato (early return).

## Retry per ciclo (invariant nuovo)
- Ogni ciclo gira in `_run_cycle_until_success()`: ritenta con un proxy diverso finché non riesce.
- L'unica uscita anticipata legittima è `session_state.is_cancelled()`.
- Il segnale `failed(file_id, cycle, motivo)` indica un TENTATIVO fallito, NON un ciclo abbandonato. Il motivo è prefissato con `"Tentativo N: ..."` per la GUI.
- `cycle_completed` viene emesso una sola volta per ciclo, al primo tentativo riuscito.
- Se il pool si svuota, il worker chiama `pool.refill_blocking()` (vedi rules/proxy.md) e attende; se anche il refill non porta proxy, attende 5s (interrompibili) e riprova.

## Struttura output
`./downloads/<sha1(url)[:12]>/ciclo_<n>/<file_originale>`. La cartella va creata da `MegaClient.download()` (`mkdir parents=True, exist_ok=True`).

## Orchestrator
- È un `QObject`, non un `QThread`: la fase di scraping/validazione gira sul thread del chiamante. In futuro, se diventa pesante per la GUI, spostarla in un `QThread` dedicato (non `threading.Thread`).
- Detiene la lista dei worker per impedirne la garbage collection mentre girano.

## Parallel client — watchdog e gestione errori CDN
- Ogni tentativo di segmento ha DUE limiti di vita:
  1. Throughput minimo `PARALLEL_MIN_THROUGHPUT_BPS` (default 200 KB/s) misurato su finestra `PARALLEL_THROUGHPUT_WINDOW` dopo un grace di `PARALLEL_THROUGHPUT_GRACE`. Sotto soglia → abort + mark dead.
  2. Budget temporale assoluto `PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S` (default 180s): superato il budget, abort anche se il throughput è sopra soglia. Difesa contro proxy "appena sopra la riga" che non finiscono mai un file grande.
- Gestione codici HTTP dal CDN Mega in `_download_segment`:
  - **403 / 509**: rate-limit per IP del proxy, temporaneo. `pool.cooldown(proxy)` (NON `penalize`/mark dead: il proxy resta vivo, solo escluso dalla rotazione per `PROXY_COOLDOWN_SECONDS`), NO re-resolve URL (ritornerebbe lo stesso host), consuma il tentativo.
  - **503**: marca dead (`penalize(hard=True)`) + tenta re-resolve come fallback (può essere overload Mega o URL scaduta).
  - Altri codici: warning standard, mark dead a fine loop come per gli errori di rete.
- `cdn_error = True` significa "ho già gestito il proxy in questo branch" (cooldown o mark dead): serve a evitare la doppia penalità nel cleanup finale.
