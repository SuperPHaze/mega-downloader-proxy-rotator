---
paths: ["src/downloader/**/*.py"]
---

# Regole per il layer downloader

## Mega API e proxy (post-vendoring)
- `mega.py` NON è più una dipendenza. Le primitive crypto (`mega_crypto.py`) e l'API pubblica (`mega_api.py`) sono vendorizzate localmente.
- `MegaPublicClient` (in `mega_api.py`) risolve un link pubblico Mega via API `cs?g=1` ritornando handle, URL CDN, dimensione, nome file decifrato. Usa `requests.Session` per-istanza con `session.proxies` nativi: nessun monkey-patch globale, nessun `threading.local`. Retry esplicito su `-3` (EAGAIN) bounded a 5 tentativi.
- `mega_crypto.py` espone solo helper puri (no I/O, no stato globale): `base64_to_a32`, `a32_to_str`, `base64_url_decode`, `decrypt_attr` (AES-CBC sugli attributi), `derive_file_key` (split chiave a 8 word → k+iv per AES-CTR del payload).
- `MegaClient` (in `mega_client.py`) usa `MegaPublicClient` per il resolve e `requests.get(stream=True)` per il transfer; decifra a blocchi con AES-CTR direttamente sul file finale (nessun temp file, nessun WinError 32 da gestire).
- L'import di `pycryptodome` resta locale dentro `MegaClient.download()` / `ParallelMegaDownloader.download()` per non rallentare l'avvio della GUI.
- Se l'import di `Crypto` fallisce, sollevare `MegaCryptoDependencyError` (errore d'ambiente permanente, non transitorio): il worker lo cattura PRIMA di `Exception` e non chiama `mark_dead()` sul proxy innocente.

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
