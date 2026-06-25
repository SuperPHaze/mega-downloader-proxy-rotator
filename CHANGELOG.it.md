# Changelog

[English](CHANGELOG.md) · **Italiano**

Tutte le modifiche rilevanti del progetto. Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/); versioni secondo [SemVer](https://semver.org/lang/it/).

## [Non rilasciato]

### Aggiunto
- Cattura dell'intero output del terminale in `logs/terminal-log.txt` (riazzerato a ogni avvio), per diagnosi rapida e condivisione.
- **Cooldown dei proxy su rate-limit Mega (403/509)**: messi a riposo per `PROXY_COOLDOWN_SECONDS` (90s) invece di essere scartati, per non svuotare il pool su sessioni lunghe.
- Riesposto nel tab Funzioni Sperimentali il controllo delle connessioni per file (per test).
- Tagli pezzo aggiuntivi 64 / 128 / 256 MB nella combo dimensione (default invariato a 32 MB).
- **Budget per pezzo configurabile** dal tab Funzioni Sperimentali (default invariato a 180 s): tempo massimo concesso a un proxy per completare un pezzo prima di cambiarlo.
- **Descrizione breve + icona "i"** su entrambi i controlli del tab Funzioni Sperimentali (connessioni per file, budget per pezzo): la spiegazione estesa si apre al clic, senza appesantire il dialog.

### Modificato
- **Pool proxy ingrandito**: target proxy vivi 80→200, candidati validati 1000→3000, soglie di rifornimento 40/80→100/180 (coerenti col nuovo target); aggiunte ~20 nuove fonti HTTP/HTTPS. La validazione iniziale/di refill è più lunga ma gira in background; obiettivo: reggere sessioni lunghe con molte connessioni senza svuotare il pool.

## [1.10.0] — 2026-06-24

### Aggiunto
- **Metriche di velocità di sessione**: media, picco e minima (sui campioni con download attivo) accanto alla velocità istantanea, nel cruscotto.
- **Barra segmentata** per lo stato dei job (in corso/in coda/completati/falliti, proporzionale).
- **Zona proxy** dedicata (nuovo widget `ProxyBar`), con salute del pool a card compatte: proxy vivi, esito validazione, proxy scartati in sessione (transizioni vivo→morto), numero di ricariche del pool e tempo dall'ultima ricarica.

### Modificato
- **Cruscotto riorganizzato su un'unica riga a 3 zone** (velocità · download · proxy), compatte e separate da linee verticali interne: zona velocità con **anello radiale** (`RadialGauge`, velocità corrente come % del picco di sessione, valore al centro) più picco/media/minima/ETA/tempo; zona "Download" (rinominata da "Job") con totale, barra segmentata e conteggi; zona proxy a card.
- **Filtri della lista job da tendina a pulsanti**: "In corso" / "Completati" / "Non completati" come pulsanti a selezione esclusiva, senza etichetta "Mostra:".

### Corretto
- **Picco di velocità di sessione**: eliminato lo spike da GB sui download ripresi (il campionatore partiva da `prev_bytes=0` contando i byte già scaricati). Aggiunta una guardia anti-campione-assurdo (non finito, negativo o sopra un tetto di sicurezza) sia su `SessionSpeedStats` che sul feed di velocità del cruscotto.
- **Smoke test dell'installer** (`install.ps1`): eseguito da file temporaneo invece che via `python -c`, risolto `SyntaxError` dovuto al passaggio dello script multi-riga in PowerShell.

## [1.9.0] — 2026-06-22

### Aggiunto
- **Log strutturato universale** (`logs/events.jsonl`, JSON Lines a livello DEBUG): ogni record di logging viene scritto anche in forma strutturata, senza filtri a monte. Sorgente primaria per la nuova diagnostica.
- **Nuovo strumento `tools/report.py`**: legge `logs/events.jsonl` e `logs/crash.log` (solo lettura, in streaming) e genera un report HTML in `logs/reports/` con sessioni, timeline heartbeat, errori/anomalie, eventi download e crash nativi.

### Modificato
- **Tutti i log, il crash log e i report generati sono consolidati nella cartella `logs/`** (prima erano sparsi nella root del progetto): `app.log`, `crash.log`, `failed_links.log`, `download_history.log`, `proxy_sources_stats.log`, `events.jsonl`, `reports/`.
- **Nuovi default di download**: dimensione chunk 8 → **32 MB**, connessioni parallele per file 4 → **10**. Il download paralleli (file) resta 1; la selezione proxy per velocità resta disattivata (modalità "score").

### Rimosso
- `tools/analyze_crashlog.py`, sostituito da `tools/report.py` (sorgente primaria events.jsonl invece di app.log/crash.log).
- **Funzioni sperimentali ritirate dall'interfaccia**: i controlli "connessioni per file" e "selezione per velocità" sono stati rimossi dal pannello "Funzioni Sperimentali", che resta presente ma vuoto (segnaposto). Il motore di download (parametri `selection_mode` e `connections_per_file`) non è stato toccato: resta disponibile per riuso futuro. Eventuali preferenze sperimentali salvate da versioni precedenti vengono ignorate.

## [1.8.3] — 2026-06-22

### Aggiunto
- **Funzioni Sperimentali** — nuovo pannello dedicato, con tutte le opzioni **disattivate di default**:
  - connessioni parallele per file **configurabili** (default 4);
  - **selezione dei proxy per velocità**: il pool misura il throughput reale di ogni proxy e preferisce i più rapidi, ruotandoli sui migliori per non farli bloccare da Mega.
- **Suite di diagnostica crash** (passiva, sempre attiva): traceback dei crash nativi (`faulthandler`), cattura delle eccezioni su tutti i thread, heartbeat periodico con uso di memoria, marcatori di sessione (avvio / chiusura pulita), instradamento dei messaggi Qt nel log.
- **Analizzatore dei log di crash** con report HTML (`tools/analyze_crashlog.py`).

### Corretto
- Numero di versione riportato a 1.8.3
- **Stabilizzata la concorrenza di validazione proxy**, causa di un crash nativo (access violation) sotto carico: tetto worker Stage 1 abbassato (200 → 100) e isteresi armato/disarmato sul refresher in background per eliminare le raffiche di refill ripetuti (osservate fino a 66 in una sessione, con picchi di ~200 thread). Le connessioni di download non sono toccate: nessun impatto sulla velocità.
- **Riparata la sonda di memoria dell'heartbeat diagnostico**: il fallback Windows (ctypes/psapi) non impostava `restype`/`argtypes` sulle funzioni di sistema, causando un errore di handle silenzioso e il valore sempre `mem_rss=n/d` nei log. Ora riporta un numero reale.
- **Risolto un crash nativo (access violation) in `SessionState.is_cancelled`** sotto alta concorrenza: decine di thread di download (`ThreadPoolExecutor`, non `QThread`) che martellavano lo stato condiviso tramite primitive Qt (`QMutex`/`QWaitCondition`) potevano corrompere la memoria. Migrato a `threading.Lock`/`threading.Condition` (stdlib), API e semantica pausa/annullo invariate.

### Modificato
- **Disciplina dei log**: riclassificati da ERROR a WARNING i fallimenti attesi/transitori dei proxy gratuiti (chunk falliti dopo retry esauriti, link abbandonato dopo il cap di tentativi) — sono fisiologici, non bug. Aggiunta una riga `CONFIG` a inizio sessione con i parametri operativi attivi (connessioni, dimensione chunk, selezione per velocità, file paralleli, worker di validazione) per correlare configurazione e crash nei log raccolti dagli utenti. Formalizzata la regola in `.claude/rules/logging.md`.

## [1.8.2] — 2026-06-21

### Aggiunto
- Documentazione **bilingue EN/IT** con selettore di lingua: README e guida operativa.
- **Sito web bilingue** (inglese di default + italiano) con toggle di lingua.
- Messaggi degli script `install.ps1` e `package.ps1` **bilingui** (inglese di default, `-Lang IT` per l'italiano).

### Modificato
- Nome ufficiale uniformato in tutto il progetto e nel titolo della finestra: **"Mega Downloader Proxy Rotator (MDPR)"**.
- Terminologia uniformata su **"chunk"** in documenti e sito.
- Guida operativa riscritta con i valori allineati al codice.

### Note
- Ripubblicazione della repository con cronologia git pulita.

## [1.8.1]

### Aggiunto
- Prima release pubblica. Motore: coda di chunk a dimensione fissa scaricati da connessioni HTTP Range parallele su proxy diversi, pool di proxy validato a due stadi e con punteggio reputazionale, cache per l'avvio "a caldo", decifratura AES integrata in streaming, GUI a schede con temi chiaro/scuro, storico download con avviso sui duplicati, modalità CLI.
