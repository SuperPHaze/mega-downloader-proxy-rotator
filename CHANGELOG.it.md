# Changelog

[English](CHANGELOG.md) · **Italiano**

Tutte le modifiche rilevanti del progetto. Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/); versioni secondo [SemVer](https://semver.org/lang/it/).

## [1.14.0] — 2026-07-01

### Modificato
- **I pulsanti filtro della lista download mostrano il conteggio dei file per stato.**
  Ogni pulsante riporta tra parentesi quanti file ricadono nella sua categoria —
  «In corso (N)» (in coda + in corso), «Completati (N)» e «Non completati (N)»
  (falliti + annullati + abbandonati). I conteggi si aggiornano in tempo reale a
  ogni cambio di stato dei download, così si vede a colpo d'occhio la composizione
  della sessione senza dover passare da un filtro all'altro.

### Corretto
- **Speed test che riportava valori di banda impossibili.** La misura del
  throughput poteva "esplodere" fino a migliaia di Mbit/s in due casi: quando un
  proxy scaricava l'intero file durante il TTFB e poi lo riversava in burst dal
  client (la finestra cronometrata collassava verso zero, contro un floor di
  appena 0,001 s), e quando il file di test veniva servito dalla cache di
  ISP/router/proxy a velocità di rete locale. Ora il throughput è calcolato con
  una finestra robusta (esclude connect+TTFB ma ricade sulla finestra completa se
  il corpo arriva in burst, con un minimo che evita la divisione per ~zero) e
  tutti gli speed test (linea, proxy e validazione) usano un URL con parametro
  anti-cache, così la banda mostrata resta realistica.

## [1.13.2] — 2026-06-29

### Aggiunto
- **Speed test "con proxy" nella zona proxy**, distinto dallo speed test della linea diretta. Ora ci
  sono due misure affiancate e differenziate a colpo d'occhio (colori diversi):
  - **Banda** (verde): banda della linea, download diretto **senza proxy** (la misura già esistente).
  - **Banda proxy** (blu): banda aggregata reale che il **pool di proxy live** riesce a erogare,
    misurata campionando i proxy migliori e scaricando attraverso di loro in parallelo.
  Il pulsante **↻ Banda proxy** è attivo solo durante una sessione (a riposo non ci sono proxy da
  testare). La misura è resiliente: un proxy lento o caduto contribuisce solo i byte effettivamente
  scaricati, senza far fallire l'intero test. Confrontare le due bande aiuta a capire quanto il pool
  di proxy si avvicina alla capacità della propria linea.

## [1.13.1] — 2026-06-29

### Corretto
- **Speed test (Selezione per velocità) che misurava valori non realistici**: il cronometro partiva
  prima della richiesta, quindi il tempo includeva la fase di connessione (connect + TLS +
  time-to-first-byte) attraverso il proxy. Con i proxy gratuiti questa latenza vale spesso secondi e su
  un download da appena 1 MB *domina* il calcolo: un proxy realmente da ~1 MB/s veniva misurato a
  ~260 KB/s (−75%). Ora si cronometra **solo il trasferimento del corpo** (il cronometro parte al primo
  byte ricevuto, escludendo la connessione), restituendo il throughput sostenuto reale (errore residuo
  ≈ 1%). I proxy veloci ma con alta latenza non vengono più scartati o ordinati male.

## [1.13.0] — 2026-06-28

### Modificato
- **Throughput dei download migliorato in modo netto** (≈ +148% sulla media nei test su file grandi,
  da ~5,8 a ~14,3 MB/s): il pool di proxy validati è molto più grande. Target proxy vivi **60 → 300**,
  candidati massimi alla validazione **3000 → 12000**, worker di validazione **100 → 200** (stadio 1) e
  **60 → 120** (stadio 2), soglie del refresher in background **15/30 → 80/160**. Più proxy vivi
  disponibili significa corsie più piene e, soprattutto, meno cali di velocità sulle sessioni lunghe
  (il pool non si "brucia" perché si rifornisce più in fretta).
- Watchdog di throughput riportato ai valori di riferimento (minimo **200 KB/s** su finestra **20 s**,
  grazia **15 s**) dopo un esperimento più aggressivo che era regredito (scartava troppi proxy troppo
  presto, lasciando le corsie vuote).

### Aggiunto
- **Telemetria "scatola nera"**: cattura strutturata e asincrona di ogni tentativo di chunk e di
  campioni a 1 Hz, su file separati per sessione in `logs/telemetry/`, a costo trascurabile sul
  download. Strumento da riga di comando `tools/analyze_telemetry.py` che la trasforma in un report
  HTML/Markdown + dataset CSV + un export compatto per l'analisi — utile per capire *dove* si perde
  velocità (qualità per-fonte, stragglers, utilizzo della linea, vincolo dominante).
- **Speed-admission** (sperimentale, da riga di comando `--speed-admission KB/s`): ammette nel pool
  solo i proxy che superano un test di velocità reale alla soglia data, mantenendo la selezione a
  punteggio e il numero di connessioni normale. Utile per privilegiare la qualità dei proxy.
- Flag del runner headless `tools/cli_download.py`: `--selection-mode`, `--connections`,
  `--concurrency` per test controllati senza interfaccia.

### Corretto
- **Gestione del `429 "Too Many Concurrent IP Addresses"` di Mega**: è un limite *per-file* sul numero
  di IP distinti che scaricano lo stesso file contemporaneamente. Prima veniva trattato come un errore
  generico e il programma passava a un altro proxy — aggiungendo un IP e *peggiorando* il limite, fino
  ad abbandonare il file. Ora **ri-prova lo stesso proxy** (stesso IP) dopo una breve attesa, senza
  penalizzarlo. Download più robusti e meno abbandoni.
- **Runner CLI headless appeso su link abbandonato**: non gestiva il segnale `abandoned`, quindi un
  link che esauriva i tentativi non veniva mai rimosso e il processo restava in attesa. Ora termina
  correttamente.

## [1.11.3] — 2026-06-27

### Aggiunto
- **Tasto "Reset cache" nella zona proxy**: cancella `proxy_cache.json` su richiesta,
  così il prossimo avvio rifà lo scrape da zero. Utile per test ripetuti di configurazione.
- **Widget Statistiche collassabile** con header riassuntivo sempre visibile (tempo,
  volume, throughput, conteggi job). Stato persistito nelle preferenze.

### Corretto
- **Filtro "In corso" non si aggiornava al completamento di un job**: la card spariva
  solo cambiando manualmente il filtro. Ora `JobsPanel` si abbona a `job_updated` e
  aggiorna la visibilità della singola card al cambio di stato, senza intervento
  dell'utente.
- **Cartelle di download rinominate col nome del file**: prima erano `downloads/<hash>_<id>/`.
  Al primo resolve riuscito la cartella viene rinominata in `<nome_file_sanitizzato>_<id>/`,
  così chi apre `downloads/` riconosce a colpo d'occhio cosa contiene. Sanitizzazione per
  Windows (rimuove `<>:"/\|?*` e caratteri di controllo, lunghezza max 120 char). Se la
  rinomina non è possibile (collisione, lock, permessi), il vecchio path viene mantenuto e
  loggato un warning — il download non viene interrotto.

## [1.11.2] — 2026-06-26

### Aggiunto
- **Fonte ProxyScrape JSON** (mirror GitHub, ~22k proxy aggiornati ogni 5 min): 3 endpoint
  separati per protocollo (http/socks5/socks4) con metadati pre-calcolati (`latency_ms`,
  `uptime_percent`, `anonymity`) allegati al dict del proxy fino al pool. Pre-filtro nello
  scraper che scarta i candidati con `uptime_percent < 50%` o `latency_ms > 3000` prima
  della validazione, risparmiando tempo di stage 1/2. Timeout di 30s per queste fonti
  (il JSON pesa diversi MB).
- **Soglia refill adattiva** (solo con selezione per velocità attiva): la soglia statica del
  refresher (15/30) viene sostituita da una soglia dinamica calcolata sul fabbisogno reale —
  `max(10, download_attivi * connessioni * 3)` per LOW, doppio per HIGH. Le soglie vengono
  aggiornate ogni volta che parte o termina un download, evitando refill inutili a carico
  basso e alzando il margine quando il carico cresce. Con flag OFF il comportamento resta
  identico (soglie statiche).
- **Widget Statistiche** con metriche complete di sessione: volume totale scaricato (inclusi
  parziali di job falliti/annullati), throughput effettivo (volume / tempo attivo), media
  aritmetica per-download, picco/minima di sessione, tempo attivo con auto-freeze a fine sessione,
  dettaglio riga-per-job, pulsante "Copia riepilogo" (testo plain negli appunti).
- **Media finale per-download** mostrata sulle card a job terminato (sotto il badge di stato):
  velocità media congelata, volume parziale e durata.

## [1.11.1] — 2026-06-26

### Aggiunto
- **Selezione per velocità** (Funzioni Sperimentali): profilo di download alternativo che attiva
  un terzo stadio di validazione (speed test reale da 1 MB), doppia soglia (ammissione fissa
  100 KB/s + preferenza configurabile, default 500 KB/s), 5000 candidati (anziché 3000),
  connessioni ridotte a 5, e selezione round-robin basata su throughput. I proxy lenti restano
  come riserva: il download degrada anziché fermarsi. Abilitabile dal pannello Funzioni
  Sperimentali con checkbox e spinbox soglia in KB/s.

## [1.11.0] — 2026-06-25

### Aggiunto
- Aggiunte ~20 fonti SOCKS4/SOCKS5 (TheSpeedX, monosans, ShiftyTR, jetkai, roosterkid, mmpx12, vakhov, zloi, rdavydov, Zaeem20, ErcinDedeoglu, Thordata, yemixzy, proxifly): aumentano la massa di candidati per alzare il numero di proxy che reggono Mega.
- Supporto proxy SOCKS4/SOCKS5 nel motore (schema `socks5h`/`socks4` via PySocks; lo scraper etichetta il protocollo per fonte). Le fonti SOCKS vengono aggiunte separatamente.
- Cattura dell'intero output del terminale in `logs/terminal-log.txt` (riazzerato a ogni avvio), per diagnosi rapida e condivisione.
- **Cooldown dei proxy su rate-limit Mega (403/509)**: messi a riposo per `PROXY_COOLDOWN_SECONDS` (90s) invece di essere scartati, per non svuotare il pool su sessioni lunghe.
- Riesposto nel tab Funzioni Sperimentali il controllo delle connessioni per file (per test).
- Tagli pezzo aggiuntivi 64 / 128 / 256 MB nella combo dimensione (default invariato a 32 MB).
- **Budget per pezzo configurabile** dal tab Funzioni Sperimentali (default invariato a 180 s): tempo massimo concesso a un proxy per completare un pezzo prima di cambiarlo.
- **Descrizione breve + icona "i"** su entrambi i controlli del tab Funzioni Sperimentali (connessioni per file, budget per pezzo): la spiegazione estesa si apre al clic, senza appesantire il dialog.

### Modificato
- **Pool proxy ingrandito**: aumentato il numero di candidati validati a **3000** (aggiunte ~20 nuove fonti HTTP/HTTPS). Il target di proxy vivi è stato fissato a **60**, e le soglie di rifornimento a **15/30**, valori realistici per la validazione contro Mega.
- La dimensione di default di un chunk è ora **32 MB**, e le connessioni parallele per file sono **10**.
- Il cooldown per i proxy che subiscono un rate-limit da Mega (403/509) è impostato a **90 secondi**.

### Corretto
- **Starvation del pool**: risolto il problema per cui un proxy in cooldown (rate-limit 403/509) contava ancora come "vivo", quindi quando quasi tutto il pool andava in cooldown insieme `size()` restava > 0 e `refill_blocking()` veniva saltato all'infinito mentre `get_next()` non aveva più nulla di selezionabile, inchiodando il pool a 1-2 proxy. Ora un proxy in cooldown non conta come vivo finché non scade.
- La fonte `hookzof-socks5` era trattata come http, ora correttamente SOCKS5.

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
