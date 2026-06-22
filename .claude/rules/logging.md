---
paths: ["src/**/*.py"]
---

# Regole di logging

## Livelli (significato vincolante)
- DEBUG: dettaglio diagnostico fine, ripetitivo. Non per l'uso normale.
- INFO: eventi di flusso normali (avvio/chiusura sessione, refill pool, download completato, heartbeat, riga CONFIG).
- WARNING: fallimenti ATTESI e transitori, non bug — proxy lento/timeout, abort di un chunk, retry esauriti su un proxy, rate-limit del CDN, link abbandonato. Fisiologici con i proxy gratuiti.
- ERROR: errori VERI e inattesi (eccezioni non gestite, condizioni che non dovrebbero accadere).
- CRITICAL: fatale, l'app non può proseguire.
Regola d'oro: se tra gli ERROR non vedi solo problemi reali, stai loggando troppo alto. I fallimenti dei proxy NON sono ERROR.

## Riga CONFIG a inizio sessione
A ogni avvio, una riga INFO con i parametri operativi e le selezioni sperimentali:
`CONFIG connessioni=<n> chunk_mb=<n> selezione_velocita=<on|off> file_paralleli=<n> validator_stage1=<n>`.

## Volume e rotazione
- Niente log in loop stretti a INFO/ERROR; il dettaglio ripetitivo va a DEBUG.
- Mantenere la rotazione di `app.log` (5MB×3) e di `events.jsonl` (20MB×5). I log non devono crescere senza limite.

## Cartella log e log strutturato universale
- Tutti i log diagnostici/operativi vivono in `logs/` (`LOGS_DIR`/`REPORTS_DIR` in `core/config.py`); le cache (`proxy_cache.json`, `branding_cache.json`, `branding_logo.*`) restano in root.
- Ogni record di logging, a livello DEBUG e senza filtri a monte, viene scritto anche in `logs/events.jsonl` (JSON Lines, un record per riga) via `JsonLinesFormatter` in `core/logging_setup.py`. Il filtraggio è compito del tool a valle (`tools/report.py`), non della cattura.
- Per arricchire un punto di log con campi strutturati (consumati solo dal JSONL, il formatter testuale di `app.log` li ignora), passa `extra={"event_type": "...", ...}` sulla chiamata `log.*` esistente. Punti già instrumentati: `session_start`, `session_clean_exit`, `heartbeat`, `config`, `download_completed`, `download_abandoned`, `download_cancelled` (vedi `core/diagnostics.py` e `downloader/orchestrator.py`).
- Non inventare `event_type` nuovi senza un consumatore reale nel report: il filtraggio sta a valle, ma i campi extra devono comunque corrispondere a dati realmente disponibili nel contesto della chiamata.

## Diagnostica crash
- Suite sempre attiva e passiva: faulthandler, hook eccezioni multi-thread, heartbeat
  (mem_rss, thread, download attivi, pool vivi), marcatori di sessione, handler messaggi Qt.
- Report diagnostico: `tools/report.py` (sola lettura, stdlib) legge `logs/events.jsonl` + `logs/crash.log` in streaming e genera un report HTML in `logs/reports/`.
