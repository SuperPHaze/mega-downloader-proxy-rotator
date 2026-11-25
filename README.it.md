<div align="center">

# Mega Downloader Proxy Rotator · MDPR

[English](README.md) · **Italiano**

**Scarica da Mega.nz più di 5 GB al giorno** — spezzando il download in tanti chunk, ognuno instradato su un **proxy gratuito diverso** e in parallelo, non ci sono limiti.

<!-- DEMO: caricare qui il video (demo.mp4) trascinandolo nell'editor web di GitHub dopo la pubblicazione -->






https://github.com/user-attachments/assets/275c6fbe-3792-4178-8a75-dc8f4610df3e








![version](https://img.shields.io/badge/version-2.3.0-blue)
![python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![gui](https://img.shields.io/badge/GUI-PyQt6-green)
![license](https://img.shields.io/badge/license-MIT-green)

[Sito](https://superphaze.github.io/mega-downloader-proxy-rotator) · [Scarica](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) · [Come funziona](#-come-funziona) · [Segnala un bug](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues)

</div>

---

## 🚀 Panoramica

App **desktop per Windows e macOS** (Python + PyQt6) che scarica file **e intere cartelle** da Mega.nz instradando il traffico su proxy HTTP pubblici e gratuiti. Il file viene diviso in una **coda di chunk a dimensione fissa**, scaricati in parallelo ognuno su un proxy diverso, decifrati al volo e riassemblati. Nata come test tecnico di rotazione IP, oggi è un downloader a uso reale, single-user e single-process. L'interfaccia è **bilingue, italiano e inglese**.

## ✨ Perché è diversa

- **Specifica per Mega** — resolve del link pubblico e decifratura AES integrati (nessuna dipendenza da `mega.py`).
- **Pool di proxy gratuiti validato e con punteggio** — scraping da decine di fonti (circa 70), validazione a due stadi (opzionalmente a tre con test di velocità), reputazione per proxy, cache su disco, rigenerazione in background.
- **Un proxy diverso per ogni chunk** — la rotazione è per-chunk, non per-file: se un proxy cade, perdi al massimo un chunk.
- **Resume granulare** — i chunk completati sopravvivono a crash, cambio proxy e cambio numero di connessioni.

## 🧩 Caratteristiche

- Coda di **chunk a dimensione fissa** (default 32 MB, configurabile) da 10 connessioni HTTP Range parallele, con supporto a più file contemporaneamente (configurabile; vedi la guida per i parametri).
- **Decifratura in streaming** su disco (RAM costante anche su file da molti GB), pattern `.part` + rinomina atomica.
- **Resume** dei download interrotti e **riavvio** di falliti/abbandonati/annullati (riprende solo i chunk mancanti).
- **Limite di tempo per file** configurabile; oltre la soglia il file viene abbandonato.
- **Recupera download** è disponibile anche con la coda vuota. Seleziona un file interrotto nella cartella di destinazione per vedere i byte salvati e riprendere i blocchi mancanti. Se manca il registro dei blocchi, puoi confermare **Ricomincia da zero**. A coda aperta, trovi lo stesso elenco in **Parziali**.
- **Storico** mostra i download completati nelle sessioni precedenti e in quella corrente. Cerca un file per nome, controlla data e dimensione o apri la cartella in cui è stato salvato.
- **Aggiunta di link a sessione in corso**: i nuovi link entrano in coda senza fermare i download né rifare la raccolta dei proxy; si sceglie se metterli in fondo o subito dopo il file in corso, e i link già presenti nella sessione vengono segnalati prima di aggiungerli.
- Un **link a file** salva il file nella destinazione scelta. Un **link a cartella** conserva il nome e le sottocartelle originali. Se il nome di un file è occupato, la nuova copia diventa `Film (2).mkv`, poi `Film (3).mkv`.
- **Watchdog per chunk**: scarta i proxy troppo lenti o che non finiscono in tempo.
- **Pannello "Funzioni sperimentali"** con connessioni per file, budget per pezzo e selezione per velocità con soglia configurabile (test di velocità reale + selezione proxy per throughput).
- **Diagnostica crash passiva** sempre attiva (heartbeat di memoria, traceback multi-thread), log strutturato universale (`logs/events.jsonl`) e un generatore di report HTML (`tools/report.py`).
- **Coda di download** con anteprima dei link, filtri per stato, velocità e tempo rimanente. Puoi aprire **Dettagli sessione** sotto la coda per consultare statistiche e connessione.
- **Interfaccia bilingue italiano/inglese**: al primo avvio segue la lingua del sistema, poi si sceglie da Impostazioni (Automatica / Italiano / English) e il cambio è immediato, senza riavviare. È tradotta tutta l'interfaccia, messaggi d'errore compresi; i messaggi nei file di log restano in italiano perché servono alla diagnosi.
- **Riduzione della finestra** nel Dock su macOS. Su Windows puoi scegliere tra barra delle applicazioni e area di notifica. Il menu dell’icona permette di riaprire la finestra.
- **Manutenzione dei dati su disco**: da Impostazioni si azzerano storico dei download, sessione salvata, cartella dei download, log e cache dei proxy. Ogni voce mostra quanto occupa davvero, niente è pre-selezionato, l'elenco di ciò che sparisce viene mostrato prima di cancellare e con un download in corso le voci pericolose sono disattivate.
- **Modalità CLI** per macchine headless.

## ⚡ Installazione rapida (Windows 10/11)

**Per usarla** — scarica il pacchetto pronto:
1. Vai alla [Release più recente](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) e scarica lo `.zip`.
2. Estrai, doppio clic su **`install.bat`** (crea l'ambiente e installa tutto: app, test e strumenti in `tools/`).
3. Apri il collegamento **Mega Downloader Proxy Rotator** creato dall’installer. Premi **Debug** nella barra in basso per mostrare o nascondere il log sotto la coda.

**Dai sorgenti** — richiede Python 3.11–3.14 nel PATH:
```bash
git clone https://github.com/SuperPHaze/mega-downloader-proxy-rotator
cd mega-downloader-proxy-rotator
install.bat
```

Un solo comando prepara tutto: dipendenze runtime (`requirements.txt`), dipendenze di test/strumenti (`requirements-dev.txt`, servono a `pytest` e a `tools/demo/demo_runner.py`) e verifica/installazione di **ffmpeg** (richiesto solo dal demo runner in modalità video; l'app vera e propria non lo usa). Per installare solo l'app di base, senza test/strumenti né ffmpeg: `powershell -ExecutionPolicy Bypass -File install.ps1 -Minimal`.

> Il `venv` non è portabile tra macchine: se sposti il progetto, non copiare `venv/` e riesegui `install.bat`.

> **Lingua degli script** — `install.ps1` e `package.ps1` mostrano i messaggi in **inglese per impostazione predefinita**. Per l'italiano, eseguili con `-Lang IT`, es. `powershell -ExecutionPolicy Bypass -File install.ps1 -Lang IT`.

## Avvio su macOS

Con Python 3.11–3.14 installato, apri **Mega Downloader Proxy Rotator.app** dal Finder. Tieni l’app nella cartella estratta, accanto a `src`. Il primo avvio prepara l’ambiente Python, quelli successivi lo riutilizzano. **Debug** mostra il log nella stessa finestra. Il pallino rosso chiude l’app.

Su Apple Silicon con Python 3.14.10 è stato verificato l’avvio di un download dalla versione 2.3.0.

## 🔧 Uso in breve

1. Scegli **Aggiungi link** per incollare un indirizzo per riga, oppure **Importa da file** per aprire un elenco `.txt`. Su Mac puoi usare **⌘L** e confermare con **⌘Invio**.
2. Controlla l’anteprima e la destinazione. **Impostazioni** (**⌘,** sul Mac) permette di cambiare cartella. Premi **Avvia** quando la coda è pronta.
3. La coda mostra avanzamento, velocità e tempo rimanente. Espandi un file per aprire i dettagli. Per le statistiche, apri **Dettagli sessione** sotto l’elenco.

CLI senza interfaccia:
```powershell
.\venv\Scripts\python.exe -m tools.cli_download "https://mega.nz/file/..."
```

> Si consiglia di lasciare i valori predefiniti (1 download, chunk da 32 MB); per la messa a punto vedi la [guida](Docs/GUIDA_OPERATIVA.md).

## ⚙️ Come funziona

1. **Procura i proxy** — scraping da fonti pubbliche → scrematura in due passaggi (è vivo? raggiunge Mega?) → pool con punteggio.
2. **Scarica** — resolve del link, divisione in chunk, N connessioni parallele su proxy diversi, decifratura in streaming, riassemblaggio e rinomina atomica.
3. **Mantiene il pool in forma** — un refresher in background rimpiazza i proxy esauriti senza fermare i download.

## 📚 Documentazione

- [`CLAUDE.md`](CLAUDE.md) — mappa dei moduli e flusso dati completo.
- [`Docs/GUIDA_OPERATIVA.md`](Docs/GUIDA_OPERATIVA.md) — guida tecnica al funzionamento del tool.

## ⚠️ Limiti noti

- I proxy gratuiti hanno mortalità elevata: è normale che la validazione ne scarti la maggior parte.
- La velocità dipende dai proxy: tipicamente da decine a poche centinaia di KB/s.
- Mega può applicare rate-limit allo stesso file anche da IP diversi (403/509 dal CDN): i proxy temporaneamente bloccati vengono messi a riposo e riusati (dettagli nella [guida](Docs/GUIDA_OPERATIVA.md)).
- Verifica MAC del file scaricato non ancora implementata (pianificata).

## 🛡️ Disclaimer

Strumento pensato **esclusivamente per scaricare file di tua proprietà o che hai il diritto di scaricare**. Aggirare i limiti tecnici di un servizio può toccarne i termini d'uso, e i proxy pubblici sono gestiti da terzi sconosciuti: usalo in modo responsabile e **mai per dati sensibili**. L'autore fornisce uno strumento tecnico neutro e non si assume responsabilità per usi impropri.

## 📄 Licenza

Distribuito con licenza **MIT** — uso, modifica e ridistribuzione liberi, anche commerciali, senza garanzia. Vedi [`LICENSE`](LICENSE).

---

<div align="center">
Creato da <b>SuperPHaze</b> · Alese (SuperPietro) Haze
</div>
