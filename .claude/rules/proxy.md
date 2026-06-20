---
paths: ["src/proxy/**/*.py"]
---

# Regole per il layer proxy

## Aggiungere una nuova fonte
1. Aggiungere una voce in `PROXY_SOURCES` (`src/proxy/sources.py`) con `name`, `url`, `kind`. Oggi sono 32 fonti registrate.
2. `kind` supportati e dispatchati in `ProxyScraper._fetch_source`: `html_table`, `plain_text`, `geonode_json`, `databay_json`, `jsonl`. Se serve un nuovo `kind`, aggiungere un parser dedicato in `ProxyScraper` e wire-up nel dispatch.
3. Il parser DEVE restituire `list[dict]` con chiavi esatte: `host` (str), `port` (str numerica), `protocol` (`"http"` / `"https"` / `"socks5"`).
4. Mai sollevare eccezioni dal parser: una fonte rotta non deve bloccare le altre — già gestito a livello di `fetch_all`.

## Validazione (a due stadi)
- `ProxyValidator.validate_against_mega` esegue Stage 1 ("il proxy funziona?" su `VALIDATOR_STAGE1_URL` = `http://www.gstatic.com/generate_204`, `VALIDATOR_STAGE1_WORKERS=200`, timeout `VALIDATOR_STAGE1_TIMEOUT=4s`) poi Stage 2 ("il proxy raggiunge l'infrastruttura di download Mega?" su `VALIDATOR_STAGE2_URL` = host dell'API Mega `https://g.api.mega.co.nz/cs`, `VALIDATOR_STAGE2_WORKERS=60`, timeout `VALIDATOR_STAGE2_TIMEOUT=PROXY_TIMEOUT=8s`).
- Solo i proxy che passano Stage 1 vengono testati allo Stage 2.
- Stage 2 ha cortocircuito: se `VALIDATOR_TARGET_ALIVE` (default 80) viene raggiunto, i future rimanenti vengono cancellati.
- Stage 1: valido un 2xx/3xx (l'endpoint risponde 204 per design). Stage 2: valida QUALSIASI risposta HTTP ricevuta dall'host API (anche un errore applicativo Mega, es. `-2`), non necessariamente 200 — un criterio più severo scarterebbe falsi negativi (proxy che funzionano benissimo per il download ma a cui Mega risponde con un errore applicativo sulla GET di test, che non e' una vera chiamata `g=1`). Niente redirect seguiti in nessuno dei due stage (`allow_redirects=False`): vogliamo la risposta diretta dell'host testato, non quella di un eventuale hop successivo.
- Stage 1 popola `proxy["latency_ms"]` su successo: il pool lo usa come tiebreaker fra proxy a parità di score.
- `progress_callback(done, total, alive)` viene chiamato dopo ogni check (utile per status bar / progress bar). `return_stage_breakdown=True` restituisce dict `{stage1_alive, stage2_alive}` per telemetria per-fonte.

## Cache proxy (hot-start)
- `proxy/proxy_cache.py` persiste su `proxy_cache.json` (root progetto) un elenco serializzabile di proxy validi tra sessioni.
- Schema versionato (`PROXY_CACHE_SCHEMA_VERSION`): un payload con schema diverso viene ignorato e `load()` ritorna `[]`. TTL per-entry (`PROXY_CACHE_TTL_S`, default 6h): entry oltre TTL scartate al load.
- `save()` è atomic (`tmp + os.replace`); load/save/clear NON sollevano mai (warning + return coerente).
- L'orchestrator riempie il pool con la cache prima dello scrape; lo scrape completo parte comunque in background come rinforzo (`BackgroundPoolRefresher.start(initial_force=True)`).

## Pool (score-based)
- `ProxyPool` è thread-safe (lock interno `_lock`). Tutti i metodi pubblici devono prenderlo.
- Ogni proxy ha uno `score` (inizialmente `POOL_SCORE_INITIAL`): `record_success` lo incrementa, `record_failure` lo decrementa. Sotto `POOL_SCORE_DEAD_THRESHOLD` il proxy è escluso da `get_next()`.
- `get_next()` è round-robin filtrato sui proxy con score sopra soglia. Se due hanno lo stesso score top, `POOL_LATENCY_TIEBREAKER` ordina per latency ascending (None in fondo). Se nessuno è eligibile ritorna `None` — il worker deve gestirlo via `refill_blocking()`.
- `penalize(proxy, hard=False)` = `record_failure`. `penalize(proxy, hard=True)` forza lo score sotto soglia (equivalente al vecchio `mark_dead`).
- `mark_dead(proxy)` esiste come alias deprecato di `penalize(hard=True)` per backward compatibility; codice nuovo deve usare `record_failure` / `penalize`.
- `refill_blocking(force=False)` rifà scrape+validate via `refill_fn` (iniettato dall'`Orchestrator`). Serializzato da `_refill_lock`: se più worker arrivano insieme, solo il primo esegue il refill, gli altri lo saltano e trovano il pool già popolato. Con `force=True` aggiunge sempre anche se il pool ha già contenuto (usato dal refresher background).
- `_refill_lock` ≠ `_lock`: il primo serializza l'operazione di refill (lunga, I/O), il secondo protegge `_proxies` / `_score` / `_latency` / `_index`. Non fonderli.
- `export_for_cache(min_score=0)` produce uno snapshot serializzabile (host, port, protocol, score, latency_ms) per `proxy_cache.save()`; dedup su (host, port).

## Refresher in background
- `BackgroundPoolRefresher` (in `proxy/refresher.py`) tiene il pool sopra `POOL_REFRESH_THRESHOLD` rinfrescando in background senza bloccare i worker.
- Doppia condizione (OR) per scatenare un refill:
  1. `pool.size() < POOL_REFRESH_THRESHOLD` (soglia quantitativa)
  2. `now - last_refill_ts > POOL_REFRESH_MAX_INTERVAL_S` (soglia temporale, default 300s)
- La condizione tempo-based copre il caso in cui il pool oscilla appena sopra soglia ma i proxy si degradano silenziosamente (rate-limit progressivo, captive portal). Non rimuovere la condizione 1: rispondere solo alla 2 lascerebbe il pool scoperto se cala bruscamente.
- `start(initial_force=True)` salta il primo wait e forza un refill immediato: usato dopo un hot-start da cache per rinforzare il pool con uno scrape completo.

## Cap di validazione
- Cap di `MAX_PROXIES_TO_VALIDATE = 1000` (definito in `core/config.py`): le fonti aggregate ritornano decine di migliaia di entry, validarle tutte significa minuti di attesa. Se serve più copertura aumentare il cap, non rimuoverlo.

## Cose da NON fare
- Non importare nulla da `src.gui` o `src.downloader` qui: il layer proxy deve restare riusabile in isolamento.
- Non loggare host:port dei proxy a stdout in produzione (rumoroso e poco utile).
