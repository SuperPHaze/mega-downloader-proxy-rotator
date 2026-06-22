# Guida operativa — Mega Downloader Proxy Rotator (MDPR)

[English](OPERATING_GUIDE.md) · **Italiano**

Questa guida descrive cosa fa il programma, come è strutturato il download e quali comportamenti aspettarsi durante l'uso. È rivolta a un pubblico tecnico: l'obiettivo è spiegare il funzionamento reale del tool e il razionale delle sue scelte, senza ostentare tecnicismi ma senza nemmeno semplificare il cuore del sistema.

---

## 1. Scopo e ambito

MDPR è un'applicazione desktop per Windows (Python + PyQt6) che scarica file da Mega.nz instradando il traffico attraverso proxy HTTP pubblici e gratuiti. Il problema che affronta è il throttling che Mega applica per indirizzo IP: scaricando da un singolo IP si incontrano presto limiti di banda e di volume. MDPR aggira il vincolo distribuendo il trasferimento su più proxy, ciascuno con un IP di uscita diverso.

Il tool è single-user e single-process, senza backend. È nato come banco di prova per la rotazione degli IP (riscaricare lo stesso file più volte da proxy diversi per misurare il comportamento del rate-limit di Mega) ed è oggi un downloader a uso reale.

L'uso previsto è il download di file di cui si ha il diritto di disporre. I proxy pubblici sono gestiti da terze parti non identificate e non offrono garanzie di riservatezza: non vanno usati per dati sensibili.

---

## 2. Architettura del download in tre fasi

Ogni sessione di download si articola in tre fasi che operano in parallelo una volta avviate.

**Approvvigionamento del pool.** Prima di scaricare, il programma costruisce un insieme di proxy funzionanti: raccoglie liste da numerose fonti pubbliche e le sottopone a una validazione a due stadi (sezione 3). Se è disponibile una cache da una sessione precedente, parte "a caldo" da quella e valida in background.

**Download.** Il file viene risolto e diviso in una coda di chunk a dimensione fissa, scaricati da più connessioni HTTP Range parallele, ciascuna su un proxy diverso, decifrati in streaming e riassemblati (sezioni 4 e 6).

**Mantenimento del pool.** Per tutta la durata del download un componente in background monitora la dimensione e la qualità del pool e lo rifornisce quando i proxy si esauriscono o si degradano (sezione 7).

---

## 3. Il pool di proxy: raccolta, validazione, punteggio

Le liste pubbliche di proxy sono ampie e in larga parte composte da indirizzi non più operativi. Usarle senza filtro produrrebbe fallimenti continui. Il programma applica quindi una **validazione a due stadi**, dimensionata per scartare in fretta i candidati inutili e spendere le risorse di test più costose solo su quelli promettenti.

**Stadio 1 — raggiungibilità.** Pre-filtro veloce e ad alta concorrenza (fino a 100 worker, timeout 4 s) contro un endpoint di connettività ad alta affidabilità (`generate_204` di Google). Verifica solo che il proxy regga un round-trip HTTP; non giudica Mega. Serve a eliminare i proxy morti senza sprecare un test sulla capacità limitata dello stadio 2.

**Stadio 2 — raggiungibilità di Mega.** I superstiti vengono provati, con concorrenza moderata (60 worker) perché Mega rate-limita, contro l'host dell'API di download di Mega — lo stesso usato dalla risoluzione reale dei link, non la homepage. Il criterio di successo è qualsiasi risposta HTTP ricevuta dall'host, anche un errore applicativo: significa che il round-trip è arrivato a destinazione. Un criterio più severo scarterebbe proxy perfettamente validi per il download.

La validazione si arresta in anticipo al raggiungimento del numero obiettivo di proxy vivi (80) e comunque non supera un tetto di candidati (1000), per non trasformare l'avvio in minuti di attesa.

È atteso, e non è un difetto, che da centinaia o migliaia di candidati ne sopravvivano poche decine: i proxy gratuiti hanno una mortalità elevata, nell'ordine del 70%.

**Punteggio reputazionale.** Ogni proxy del pool ha un punteggio. Entra a 0; un successo lo incrementa (+5), un fallimento lo penalizza (−10), e sotto la soglia di −20 viene considerato morto e messo da parte (ma può rientrare a un refill successivo se ricompare nelle liste). La selezione è round-robin per punteggio; a parità di punteggio viene preferito il proxy con latenza inferiore.

Le penalità distinguono la causa: un rifiuto esplicito del CDN di Mega per saturazione dell'IP (403, 509, 503) è una penalità "dura", mentre un errore transitorio (timeout, throughput insufficiente, errore di rete) è una penalità "morbida". I successi — un chunk completato o un controllo dell'IP di uscita andato a buon fine — vengono registrati e alzano il punteggio.

---

## 4. Il download: chunk paralleli, decifratura, scrittura atomica

Un download diretto da Mega procede in un unico flusso, veloce quanto la singola connessione che lo serve: con un proxy gratuito lento, il download è lento. MDPR aggira il limite dividendo il file in **chunk a dimensione fissa** (8 MB di default) e scaricandoli con **più connessioni HTTP Range in parallelo** (4 di default), ciascuna instradata su un proxy diverso. I chunk completati vengono riassemblati nell'ordine corretto.

La rotazione è quindi per-chunk, non per-file: se un proxy cade, si perde al più il chunk in corso, non l'intero trasferimento. I file più piccoli della soglia di parallelizzazione (1 MiB) vengono scaricati in modo seriale, perché lo split non porterebbe vantaggi.

Il programma può inoltre lavorare su **più file contemporaneamente**: il valore di default è 1, regolabile dalla GUI fino a 5. Aumentarlo moltiplica però la pressione sul pool di proxy e può degradare tutti i download in corso, motivo per cui il default è sequenziale.

Il payload consegnato da Mega è cifrato. Il programma lo **decifra in streaming** (AES-CTR) man mano che i chunk arrivano, scrivendo direttamente sul file di destinazione: il consumo di RAM resta costante anche su file di molti GB e ciò che finisce sul disco è già il file finale utilizzabile.

La scrittura segue il pattern **`.part` + rename atomico**: il trasferimento avviene sempre su un file `<nome>.part`, affiancato da un sidecar `.progress.json` che registra i chunk completati. Solo a download completo il file viene rinominato (operazione atomica) sul nome definitivo. L'esistenza del nome definitivo è l'unico marcatore di completamento.

---

## 5. Funzioni sperimentali (opt-in)

Una scheda dedicata raccoglie opzioni avanzate, tutte **disattivate di default**: chi non le tocca ottiene il comportamento storico descritto nelle sezioni precedenti.

**Connessioni per file configurabili.** Il numero di connessioni HTTP Range parallele per singolo file (4 di default) diventa regolabile dall'utente entro un intervallo prefissato. Alzarlo accelera il singolo file solo se il pool dispone di proxy buoni in numero sufficiente: più connessioni significano più proxy "consumati" in parallelo, quindi su un pool povero il guadagno reale può essere nullo o negativo (più contesa, più tentativi falliti).

**Selezione dei proxy per velocità.** In alternativa alla selezione round-robin per punteggio (il default), il pool può preferire i proxy con il throughput osservato più alto, misurato con una media mobile esponenziale. La rotazione resta comunque fra i migliori (non sempre lo stesso singolo proxy), per non esporre un proxy veloce a un rate-limit di Mega concentrato su un solo IP.

---

## 6. Watchdog e gestione dei fallimenti

I proxy gratuiti falliscono spesso e in modi diversi; il programma è costruito per assorbirli senza fermarsi. Ogni tentativo di trasferimento di un chunk è sorvegliato da due limiti.

**Soglia di throughput.** Se la velocità media negli ultimi 20 secondi scende sotto un minimo utile (200 KB/s), dopo un periodo di grazia iniziale di 15 secondi (per lasciare spazio al TCP slow-start), il tentativo viene abortito e il chunk riprovato con un altro proxy. È la difesa contro i proxy che trasmettono a singhiozzo: inviano qualche byte quanto basta a non far scattare il timeout di lettura, ma di fatto non concluderebbero mai.

**Budget temporale assoluto.** Indipendentemente dal throughput istantaneo, un singolo tentativo non può durare più di 180 secondi. Evita di restare bloccati su un proxy che si mantiene appena sopra la soglia ma non finisce in tempi sensati.

Quando un tentativo fallisce, il programma riprova lo stesso chunk con un proxy diverso, fino a un numero massimo di tentativi per chunk (8). Se un numero eccessivo di chunk esaurisce tutti i tentativi, il download viene interrotto in modo soft: i chunk già completati restano salvati nel sidecar e il file viene ripreso dal punto raggiunto.

Esistono due limiti di salvaguardia a livello di file: una durata massima wall-clock per file (60 minuti, configurabile), superata la quale il file viene abbandonato e lo slot passa al successivo; e un numero massimo di tentativi consecutivi falliti per lo stesso link (15) prima di abbandonarlo, per non entrare in loop infiniti su file rimossi, hash non validi o regioni bloccate. I link abbandonati vengono registrati in un log dedicato.

I numerosi tentativi falliti visibili durante l'uso sono quindi un comportamento previsto, non un malfunzionamento: sono il costo dei proxy gratuiti, e il sistema è progettato per gestirli.

---

## 7. Mantenimento del pool

I proxy gratuiti si consumano: uno valido pochi minuti fa può non esserlo più. Se il programma usasse solo l'insieme raccolto all'avvio, finirebbe per restare a secco. Un **rifornitore in background** controlla a intervalli regolari (ogni 30 secondi) il numero di proxy vivi e, se scende sotto la soglia (40), avvia uno scrape e una validazione senza interrompere i download in corso. Per evitare raffiche di rifornimenti quando il pool oscilla appena intorno alla soglia, il rifornitore si "disarma" dopo ogni intervento e si riarma solo quando i proxy vivi tornano sopra una soglia più alta (80). Per intercettare il degrado silenzioso (proxy che rallentano progressivamente senza morire del tutto), forza comunque un rifornimento se l'ultimo è avvenuto da più di 5 minuti.

Se il pool si svuota in un momento critico, è il download stesso a richiedere un rifornimento e ad attendere il tempo necessario: in quei frangenti si può osservare una pausa, durante la quale il programma sta ricostruendo il pool prima di proseguire. Il tutto è automatico e non richiede intervento.

---

## 8. Memoria tra sessioni (avvio a caldo)

La prima costruzione del pool richiede tempo (indicativamente da mezzo minuto a un paio di minuti). Per evitare di ripeterla a ogni avvio, il programma persiste su disco i proxy migliori e li ricarica all'apertura successiva, riconvalidandoli rapidamente: i proxy ancora vivi sono subito disponibili (avvio "a caldo"), mentre una ricerca completa riparte comunque in background. Le voci della cache oltre il tempo di validità (6 ore) vengono scartate al caricamento. Dalla seconda sessione in poi l'avvio è quindi sensibilmente più rapido.

---

## 9. Controlli di sessione e resume

Durante una sessione i controlli disponibili sono pausa/ripresa e annullo, sia globali sia per singolo file dalla tabella. La pausa non comporta la perdita dei proxy: alla ripresa il lavoro riparte dal punto in cui era stato sospeso. L'annullo di un singolo file può, a scelta, rimuoverne anche i dati già scaricati dal disco.

Il resume copre anche le interruzioni non volontarie (chiusura del programma, blackout, errore). Grazie allo schema `.part` + sidecar, alla ripresa vengono riscaricati solo i chunk mancanti; un ciclo è considerato completo unicamente quando esiste il file finale rinominato, quindi un file interrotto non viene mai scambiato per completo.

---

## 10. Output, storico e log

I file scaricati vengono salvati in sottocartelle dedicate dentro la cartella `downloads` del progetto. Tutti i log diagnostici/operativi sono raccolti nella cartella `logs/` del progetto: lo storico dei download completati (con deduplica per handle Mega, usato per avvisare quando si reinserisce un link già scaricato), il registro dei link abbandonati, le metriche per-fonte dei proxy, un log tecnico generale dell'attività e un log strutturato universale (`logs/events.jsonl`). Non servono per l'uso ordinario, ma sono disponibili per la diagnostica.

Una **suite di diagnostica passiva**, sempre attiva, integra questi log: traceback dei crash nativi, cattura delle eccezioni su tutti i thread, un heartbeat periodico con uso di memoria e marcatori di avvio/chiusura della sessione. In caso di crash, lo strumento da riga di comando `tools/report.py` legge `logs/events.jsonl` e `logs/crash.log` e produce un report HTML leggibile in `logs/reports/`, utile per ricostruire cosa stava succedendo nel programma poco prima del problema.

---

## 11. Parametri principali e default

I valori sotto sono i default di fabbrica; quelli regolabili sono indicati nelle note.

| Parametro | Default | Note |
|---|---|---|
| Dimensione chunk | 8 MB | configurabile; chunk più piccoli resistono meglio al cambio proxy ma generano più richieste |
| Connessioni parallele per file | 4 | richieste HTTP Range simultanee, una per proxy |
| Download contemporanei | 1 | configurabile, range consigliato 1–5 |
| Soglia minima di parallelizzazione | 1 MiB | sotto questa dimensione il file va in seriale |
| Tentativi per chunk | 8 | prima di considerare il chunk fallito |
| Throughput minimo | 200 KB/s | misurato su finestra di 20 s, dopo 15 s di grazia |
| Budget per tentativo di chunk | 180 s | limite assoluto, indipendente dal throughput |
| Durata massima per file | 60 min | configurabile; oltre il limite il file è abbandonato |
| Tentativi falliti prima dell'abbandono | 15 | per singolo link, non si resetta tra cicli |
| Refresh pool | ogni 30 s | refill se proxy vivi < 40 (si riarma a 80); refresh forzato oltre 5 min |
| Validità cache proxy | 6 ore | voci più vecchie scartate all'avvio |
| Punteggio proxy | 0 / +5 / −10 / morto sotto −20 | iniziale / successo / fallimento / soglia |

---

## 12. Comportamenti attesi

Alcuni comportamenti possono sembrare anomalie ma sono parte del normale funzionamento:

- **Attesa all'avvio prima dell'inizio del download:** è la raccolta e validazione dei proxy. Dalla seconda sessione è più rapida grazie alla cache.
- **Molti tentativi falliti in scorrimento:** è il costo dei proxy gratuiti; conta il risultato finale, non i singoli errori.
- **Velocità variabile e spesso modesta:** dipende dalla qualità dei proxy, tipicamente da poche decine a qualche centinaio di KB/s. Il collo di bottiglia è esterno al programma.
- **Brevi pause durante il download:** è il rifornimento del pool in corso.
- **File occasionalmente abbandonati:** accade con link non più validi o file rimossi da Mega; il programma lo segnala e prosegue con gli altri.

---

## 13. Limiti noti

- I proxy gratuiti hanno mortalità elevata (~70%): la validazione ne scarta fisiologicamente la maggior parte.
- La velocità è determinata dai proxy, non dal programma.
- Mega può applicare rate-limit allo stesso file anche da IP diversi (403/509 dal CDN): è il comportamento che il tool è nato per misurare.
- La verifica dell'integrità tramite MAC del file scaricato non è ancora implementata: è una funzionalità pianificata.
