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
- Mantenere la rotazione di `app.log` (5MB×3). I log non devono crescere senza limite.

## Diagnostica crash
- Suite sempre attiva e passiva: faulthandler, hook eccezioni multi-thread, heartbeat
  (mem_rss, thread, download attivi, pool vivi), marcatori di sessione, handler messaggi Qt.
