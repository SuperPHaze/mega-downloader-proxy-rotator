<div align="center">

# Mega Downloader Proxy Rotator · MDPR

[English](README.md) · **Italiano**

**Scarica da Mega.nz più di 5 GB al giorno** — spezzando il download in tanti chunk, ognuno instradato su un **proxy gratuito diverso** e in parallelo, non ci sono limiti.

<!-- DEMO: caricare qui il video (demo.mp4) trascinandolo nell'editor web di GitHub dopo la pubblicazione -->




https://github.com/user-attachments/assets/b4e0839b-6545-4614-9437-22f5ee564264





![version](https://img.shields.io/badge/version-1.8.3-blue)
![python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![gui](https://img.shields.io/badge/GUI-PyQt6-green)
![license](https://img.shields.io/badge/license-MIT-green)

[Sito](https://superphaze.github.io/mega-downloader-proxy-rotator) · [Scarica](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) · [Come funziona](#-come-funziona) · [Segnala un bug](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues)

</div>

---

## 🚀 Panoramica

App **desktop per Windows** (Python + PyQt6) che scarica file da Mega.nz instradando il traffico su proxy HTTP pubblici e gratuiti. Il file viene diviso in una **coda di chunk a dimensione fissa**, scaricati in parallelo ognuno su un proxy diverso, decifrati al volo e riassemblati. Nata come test tecnico di rotazione IP, oggi è un downloader a uso reale, single-user e single-process.

## ✨ Perché è diversa

- **Specifica per Mega** — resolve del link pubblico e decifratura AES integrati (nessuna dipendenza da `mega.py`).
- **Pool di proxy gratuiti validato e con punteggio** — scraping da decine di fonti, validazione a due stadi, reputazione per proxy, cache su disco, rigenerazione in background.
- **Un proxy diverso per ogni chunk** — la rotazione è per-chunk, non per-file: se un proxy cade, perdi al massimo un chunk.
- **Resume granulare** — i chunk completati sopravvivono a crash, cambio proxy e cambio numero di connessioni.

## 🧩 Caratteristiche

- Coda di **chunk a dimensione fissa** (default 8 MB, configurabile) da 4 connessioni HTTP Range parallele, fino a 5 file contemporaneamente (configurabile).
- **Decifratura in streaming** su disco (RAM costante anche su file da molti GB), pattern `.part` + rinomina atomica.
- **Resume** dei download interrotti e **riavvio** di falliti/abbandonati/annullati (riprende solo i chunk mancanti).
- **Limite di tempo per file** configurabile; oltre la soglia il file viene abbandonato.
- **Storico download** con avviso sui link già scaricati (dedup per handle Mega).
- **Watchdog per chunk**: scarta i proxy troppo lenti o che non finiscono in tempo.
- **Funzioni sperimentali** (opt-in, disattivate di default): connessioni parallele per file regolabili e selezione dei proxy per velocità osservata.
- **Diagnostica crash passiva** sempre attiva (heartbeat di memoria, traceback multi-thread), log strutturato universale (`logs/events.jsonl`) e un generatore di report HTML (`tools/report.py`).
- **Interfaccia** a schede con cruscotto (velocità, ETA, stato del pool), tema chiaro/scuro, pausa/ripresa/annullo globali e per singolo job.
- **Modalità CLI** per macchine headless.

## ⚡ Installazione rapida (Windows 10/11)

**Per usarla** — scarica il pacchetto pronto:
1. Vai alla [Release più recente](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) e scarica lo `.zip`.
2. Estrai, doppio clic su **`install.bat`** (crea l'ambiente e installa tutto).
3. Avvia con **`avvia.bat`**.

**Dai sorgenti** — richiede Python 3.11–3.14 nel PATH:
```bash
git clone https://github.com/SuperPHaze/mega-downloader-proxy-rotator
cd mega-downloader-proxy-rotator
install.bat
```

> Il `venv` non è portabile tra macchine: se sposti il progetto, non copiare `venv/` e riesegui `install.bat`.

> **Lingua degli script** — `install.ps1` e `package.ps1` mostrano i messaggi in **inglese per impostazione predefinita**. Per l'italiano, eseguili con `-Lang IT`, es. `powershell -ExecutionPolicy Bypass -File install.ps1 -Lang IT`.

## 🔧 Uso in breve

1. Incolla uno o più link `https://mega.nz/...` (o importali da un file `.txt`).
2. Regola le opzioni dal menù **Impostazioni** e premi **Avvia**.
3. Segui avanzamento, velocità e tentativi per ogni file; metti in pausa, riavvia o annulla quando vuoi.

CLI senza interfaccia:
```powershell
.\venv\Scripts\python.exe -m tools.cli_download "https://mega.nz/file/..."
```

## ⚙️ Come funziona

1. **Procura i proxy** — scraping da fonti pubbliche → scrematura in due passaggi (è vivo? raggiunge Mega?) → pool con punteggio.
2. **Scarica** — resolve del link, divisione in chunk, N connessioni parallele su proxy diversi, decifratura in streaming, riassemblaggio e rinomina atomica.
3. **Mantiene il pool in forma** — un refresher in background rimpiazza i proxy esauriti senza fermare i download.

## 📚 Documentazione

- [`CLAUDE.md`](CLAUDE.md) — mappa dei moduli e flusso dati completo.
- [`Docs/GUIDA_OPERATIVA.md`](Docs/GUIDA_OPERATIVA.md) — guida tecnica al funzionamento del tool.

## ⚠️ Limiti noti

- I proxy gratuiti hanno mortalità elevata (~70%): è normale che la validazione ne scarti la maggior parte.
- La velocità dipende dai proxy: tipicamente da decine a poche centinaia di KB/s.
- Mega può applicare rate-limit allo stesso file anche da IP diversi (403/509 dal CDN).
- Verifica MAC del file scaricato non ancora implementata (pianificata).

## 🛡️ Disclaimer

Strumento pensato **esclusivamente per scaricare file di tua proprietà o che hai il diritto di scaricare**. Aggirare i limiti tecnici di un servizio può toccarne i termini d'uso, e i proxy pubblici sono gestiti da terzi sconosciuti: usalo in modo responsabile e **mai per dati sensibili**. L'autore fornisce uno strumento tecnico neutro e non si assume responsabilità per usi impropri.

## 📄 Licenza

Distribuito con licenza **MIT** — uso, modifica e ridistribuzione liberi, anche commerciali, senza garanzia. Vedi [`LICENSE`](LICENSE).

---

<div align="center">
Creato da <b>SuperPHaze</b> · Alese (SuperPietro) Haze
</div>
