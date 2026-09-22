# Changelog

[English](CHANGELOG.md) · **Italiano**

Tutte le modifiche rilevanti del progetto. Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/); versioni secondo [SemVer](https://semver.org/lang/it/).

## [Non rilasciato]

### Aggiunto
- **Finestra «Manutenzione», per azzerare i dati che il programma lascia su disco.** Si apre da
  **Impostazioni → «Manutenzione:» → «Azzera dati…»** e copre cinque voci: storico dei download,
  stato della sessione da riprendere, cartella dei download, log e statistiche delle fonti, cache
  dei proxy. Accanto a ogni voce c'è il **conteggio e lo spazio reali** letti dal disco in quel
  momento (quante voci ha lo storico, quanti link sono in sospeso, quanti file e quanti frammenti
  `.part` ci sono, quanto occupano i log), e quello che si legge è esattamente quello che sparisce.
- **Nessuna casella spuntata all'apertura, elenco prima di cancellare, resoconto dopo.** Premuto il
  pulsante, una seconda finestra elenca riga per riga i file che verranno cancellati con le loro
  dimensioni, e il pulsante predefinito è **Annulla**. A operazione fatta, il resoconto di cosa è
  stato azzerato e di quanto spazio è stato liberato resta nella finestra e finisce anche nel log
  dell'applicazione. Se una voce non riesce, le altre proseguono e il resoconto dice quale e perché.
- **Cartella dei download e log non si azzerano a sessione in corso**: la finestra li mostra
  disattivati e spiega il motivo (cancellare un file mentre viene scritto manda in errore i
  download e penalizza i proxy). Storico e stato della sessione restano invece azzerabili anche
  mentre si scarica. Il blocco vale anche nei secondi dopo un **Annulla** globale, finché i
  download non hanno davvero smesso di scrivere.

### Modificato
- Le **impostazioni** (`preferences.json`) restano fuori dalla finestra di proposito: il programma
  le tiene in memoria e le riscriverebbe subito, lasciando uno stato incoerente. Per quelle resta
  lo strumento da riga di comando `tools/pulizia-preferenze.py`, che ora usa le **stesse funzioni**
  della finestra Manutenzione invece di una copia propria della logica.

## [2.2.0] — 2026-09-14

### Aggiunto
- **Aggiungere link a una sessione in corso, senza interrompere i download.** Il pulsante
  **Aggiungi link** resta attivo mentre si scarica: i nuovi link entrano nella coda della
  sessione corrente senza fermare i file in corso e senza rifare la raccolta dei proxy, che è
  la parte lenta dell'avvio. Il numero di file scaricati contemporaneamente non cambia: gli
  aggiunti aspettano il loro turno.
- **Scelta della posizione al momento dell'aggiunta**: *in fondo alla coda* oppure *subito dopo
  il download in corso*, per farli passare davanti ai link già in attesa.
- **Avviso sui link già presenti nella sessione.** Se un link è già in coda, in download o già
  concluso, viene elencato con il suo stato e serve una conferma per aggiungerlo comunque. Il
  confronto è per handle Mega: riconosce lo stesso file anche incollato in una forma di URL
  diversa.
- **A coda già finita l'aggiunta chiede cosa fare**: proseguire la stessa sessione — tenendo
  elenco, statistiche, cronometro e i proxy già validati — oppure ripartire pulito come un
  avvio nuovo.
- Un **link a cartella** aggiunto a caldo viene elencato con una finestra di avanzamento **non
  modale**, che dichiara che i download in corso proseguono: pausa, annullo e dettaglio dei file
  restano raggiungibili mentre la cartella viene letta.

## [2.1.0] — 2026-09-14

### Aggiunto
- **Icona nell'area di notifica, accanto all'orologio.** Riducendo la finestra a icona il
  programma chiede dove metterla — **area di notifica** oppure **barra delle applicazioni**,
  com'era prima — e la finestra di domanda ha una casella **«Ricorda la scelta»**. Dall'icona:
  doppio clic per riaprire la finestra, menu con **«Mostra la finestra»** ed **«Esci»**,
  suggerimento del mouse con lo stato della sessione (file in corso, completati, velocità).
  Quando l'app è nell'area di notifica non compare più nella barra delle applicazioni, e con lei
  spariscono anche le finestre di dettaglio aperte (tornano al ripristino, come stavano). Nuovi
  **avvisi a comparsa**: a ogni file completato, a ogni file non riuscito e a coda completata.
  Il pulsante di chiusura della finestra (la X) resta quello di sempre: chiude l'applicazione.
  Se l'area di notifica non è disponibile, nessuna domanda e nessuna icona: la riduzione resta
  quella di prima.
- **Menu Impostazioni → «Riduzione a icona:»**, con il pulsante **«Chiedi ogni volta»**: rimette
  la domanda dopo che è stata messa a tacere con «Ricorda la scelta». Il suggerimento del mouse
  dice qual è la scelta attualmente in vigore.
- **Avvio senza finestra del terminale.** `avvia.bat` ora lancia il programma con `pythonw.exe`:
  nessuna finestra nera che resta aperta accanto all'applicazione. Il nuovo **`avvia-debug.bat`**
  fa l'opposto e mantiene il terminale visibile: è il lancio di riserva da usare quando l'app non
  parte e si vuole vedere perché. `install.ps1` crea entrambi i file.

### Corretto
- **Icona dell'applicazione caricata in modo esplicito a tutte le sue dimensioni.** Il file
  `assets/icon.ico` ne contiene sette (16, 24, 32, 48, 64, 128, 256 pixel): ora vengono lette e
  registrate una per una, invece di lasciare al lettore di immagini la scelta di quante
  esporne. Il ripiego al `.png` scatta anche quando il `.ico` esiste ma non è leggibile (prima
  il controllo si affidava a un dettaglio interno della libreria grafica), e l'avviso nel log
  quando non si carica nulla è ora coperto da un test.
- **Avvio silenzioso senza console: la cattura dell'output non si rompe più.** Senza terminale
  `sys.stdout`/`sys.stderr` non esistono, e la prima riga di log avrebbe fatto cadere il
  programma prima ancora che la finestra comparisse. Ora `logs/terminal-log.txt` resta l'unica
  copia di ciò che si vedeva a video e continua a essere scritto, e un'eccezione non gestita del
  thread principale finisce anche in `logs/crash.log` — dove la legge `tools/report.py` — invece
  di svanire insieme al terminale che non c'è.
- **`package.ps1` si accorge anche dei file `.bat` nuovi non tracciati da git**, non solo dei
  `.py`: i due file di avvio sono in prima linea per chi riceve il pacchetto, e uno nuovo
  sarebbe finito fuori dallo zip senza che nessuno se ne accorgesse fino al doppio clic
  mancato.
- **`install.ps1` prepara davvero tutto in un solo passaggio**: oltre a `requirements.txt` installa
  ora anche `requirements-dev.txt` (serve a `pytest` e a `tools/demo/demo_runner.py`, prima andava
  installato a mano) e verifica/installa **ffmpeg** via winget (richiesto solo dal demo runner in
  modalità video; solo un avviso, mai un errore bloccante, se manca o winget non è disponibile).
  Nuovo flag `-Minimal` per chi vuole solo l'app di base, senza dipendenze di test/strumenti né
  ffmpeg. Lo smoke test finale ora genera la lista dei moduli da un inventario reale delle
  dipendenze invece di una lista fissa nel codice.

## [2.0.0] — 2026-08-21

### Aggiunto
- **Interfaccia in italiano e inglese.** All'avvio il programma segue la lingua del sistema
  (italiano se il sistema è in italiano, inglese in tutti gli altri casi) e nel menu
  **Impostazioni** compare la voce **Lingua** con «Automatica / Italiano / English». La scelta si
  applica **subito**, senza riavviare, e viene ricordata al riavvio successivo. Sono tradotte
  la **barra dei comandi**, il **titolo della finestra**, la barra «nuova versione disponibile»,
  le finestre **Info**, **Funzioni Sperimentali** e **Incolla link Mega**, l'intero cruscotto
  (**zona proxy**, **statistiche**, **elenco dei download** con filtri, schede e stato vuoto),
  il **pannello dei link**, la **lettura delle cartelle Mega** e tutti i messaggi della
  **finestra principale**: avvisi di avvio, ripristino della sessione precedente, conferme di
  eliminazione dal disco e riga di stato in basso. Singolare e plurale sono corretti in
  entrambe le lingue («1 link pronto» / «2 link pronti», «1 subfolder» / «3 subfolders»).
  Sono tradotti anche la **finestra di dettaglio di un download** (riepilogo, cronologia degli
  IP, log dei tentativi) e i **messaggi d'errore** dei singoli file, comprese le righe di stato
  della raccolta dei proxy: se si cambia lingua con una finestra di dettaglio aperta, anche il
  log già scritto viene riscritto nella lingua nuova. I messaggi nei file di log restano in
  italiano: servono alla diagnosi e devono restare stabili.

### Modificato
- **Ritocchi ai testi inglesi dell'interfaccia**: «Selection by speed» è diventato
  «Speed-based selection» (lo stesso termine che usa la guida), «Limit min/file:» è diventato
  «Time limit (min/file):», e il pulsante che apre la finestra delle informazioni si chiama
  «About», come la finestra stessa.

### Corretto
- **Nome del file singolo letto correttamente** (`mega_<handle>` invece del nome vero). Alcuni
  file Mega hanno il blob degli attributi con residuo non-zero dopo il nome (es. file rinominati
  lato Mega): la lettura pretendeva che l'intera stringa decifrata fosse JSON valido e falliva,
  facendo ripiegare il nome sul segnaposto pur con chiave e contenuto corretti. Ora si estrae solo
  l'oggetto JSON valido, ignorando il residuo. Colta l'occasione, la decodifica del blob è passata
  da latin-1 a UTF-8: i nomi accentati non rischiano più il mojibake.
- Nella cronologia di un download la riga di un tentativo fallito ripeteva due volte
  «Tentativo N:» («Tentativo 1: Tentativo 1: download fallito…»). Ora compare una volta sola.
- **Singolari italiani sgrammaticati.** Quando il conteggio era 1 alcuni messaggi restavano al
  plurale: «1 sottocartelle», «1 file pronti al download», «1 file duplicati … sono stati
  rimossi», «1 file NON verranno scaricati», «dopo 1 tentativi», «chiusa con 1 link non
  completati», «Ripristinati 1 link», «Riavviati 1 download». Ora la frase è al singolare.
- **Lo stato di un download non compare più in forma grezza.** Nella finestra di dettaglio si
  leggeva «in_corso», «abbandonato» — il valore interno del programma — invece di «In corso»,
  «Abbandonato». Ora usa le stesse etichette della lista dei download, in entrambe le lingue.
- **L'etichetta di stato non viene più tagliata**: la più lunga («Abbandonato») non entrava nel
  riquadro e si leggeva a metà.

## [1.21.0] — 2026-08-18

### Aggiunto
- **Supporto ai link cartella Mega (`/folder/`).** Si può incollare direttamente il link di una
  cartella condivisa: premendo Avvia il programma ne legge l'elenco e la **espande nei singoli
  file**, che vengono poi scaricati dal motore di sempre (rotazione proxy, pezzi paralleli,
  ripresa dei download interrotti, storico). Sono riconosciuti tutti i formati: cartella intera
  (`/folder/<id>#<chiave>`), formato legacy (`#F!<id>!<chiave>`) e link che puntano a un singolo
  file o a una sottocartella dentro la cartella condivisa. Nello stesso incolla si possono
  mescolare link a cartelle e link a file singoli.
- **I file di una cartella vengono salvati ad albero**, sotto un'unica cartella che porta il nome
  della cartella Mega e con le sottocartelle originali preservate
  (`<cartella download>/<Nome cartella Mega>/<sottocartella>/<file>`). I nomi non validi per
  Windows vengono corretti e i doppioni ricevono un suffisso numerico, senza mai sovrascrivere.
  Se si incollano **due cartelle diverse con lo stesso nome**, la seconda finisce in
  «Nome (2)»: i due alberi restano separati invece di mescolarsi.
- **Eliminazione mirata dei file di una cartella.** Annullando o eliminando un file proveniente
  da una cartella viene rimosso **solo quel file** (con i suoi file temporanei); gli altri file
  della stessa cartella restano al loro posto.
- Nella finestra «Incolla link Mega» un contatore **«Cartelle»** distingue i link a cartella dai
  link a file singolo.

## [1.20.1] — 2026-07-02

### Modificato
- **Zona proxy più compatta.** I pulsanti «↻ Banda», «↻ Banda proxy» e «Reset cache» sono ora
  impilati in verticale a destra delle statistiche del pool, per occupare meno spazio in larghezza.
- **Statistiche della zona proxy su due righe.** I sette riquadri (Vivi, Validazione, Scartati,
  Ricariche, Ultimo refill, Banda, Banda proxy) sono ora disposti su due righe (griglia 4+3)
  invece di un'unica fila: ogni riquadro ha spazio per la propria etichetta senza tagli, anche
  quando la finestra viene ridimensionata.

## [1.20.0] — 2026-07-02

### Aggiunto
- **Cartella di download scegliibile dalla GUI.** Dal menu **Impostazioni → «Cartella
  download:»** si può scegliere dove salvare i file; la scelta è ricordata tra le sessioni.
  Se non si sceglie nulla resta la cartella predefinita (`downloads/` del programma). Se la
  cartella scelta non è scrivibile, il programma avvisa e torna alla predefinita.
- **Ripristino della sessione all'avvio.** Se il programma si chiude (o va in crash) con dei
  download non completati, alla riapertura propone di **ricaricare i link rimasti**. I pezzi già
  scaricati vengono ripresi automaticamente: basta premere Avvia.
- **Controllo dello spazio su disco prima di iniziare.** Se non c'è spazio sufficiente per il
  file (più un margine di sicurezza) il download viene abbandonato subito con un messaggio chiaro,
  invece di fallire in modo criptico a metà con il disco pieno.
- **Rispetto dell'header `Retry-After` del CDN Mega.** Sui rate-limit (403/509) e sul limite di IP
  concorrenti (429), se il server indica quanto attendere, l'attesa segue quel valore (entro un
  tetto) invece di un'attesa "alla cieca".
- **Integrazione continua (CI).** Un workflow GitHub Actions esegue automaticamente la suite di
  test su Windows (Python 3.11 e 3.13) a ogni push e pull request.
- **Supporto ai proxy con autenticazione** (`utente:password`) nella costruzione dell'URL del
  proxy. Le liste gratuite non ne hanno bisogno: è predisposizione per eventuali liste autenticate.

### Modificato
- **Ripristino prudente della reputazione dei proxy dalla cache.** All'avvio a caldo, i proxy che
  in una sessione precedente avevano una buona reputazione ripartono avvantaggiati ma con il
  punteggio **dimezzato verso il neutro** (i proxy gratuiti cambiano qualità di continuo); i proxy
  neutri o penalizzati ripartono da zero, senza ereditare penalità né "resuscitare" gonfiati.
- **Nomi file più robusti su Windows.** Il nome del file scaricato viene ripulito dai caratteri
  vietati (`: ? * " < > |`) e dai nomi di dispositivo riservati (`CON`, `NUL`, …), preservando
  l'estensione. Prima un nome del genere faceva fallire il salvataggio e sprecava tutti i
  tentativi, con un errore fuorviante che sembrava colpa dei proxy.
- **Annullo più reattivo durante la risoluzione del link.** Un «Annulla» che arriva mentre il
  programma sta risolvendo un link Mega (con i suoi ritentativi) ora viene onorato subito, senza
  restare appeso fino a decine di secondi.

### Corretto
- **File da 0 byte non più abbandonati.** Un file vuoto su Mega veniva richiesto con un intervallo
  di byte non valido e falliva a ripetizione fino all'abbandono; ora viene creato correttamente
  come file vuoto.

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
