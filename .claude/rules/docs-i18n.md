---
paths: ["README*.md", "CHANGELOG*.md", "Docs/**/*.md", "index*.html", "install.ps1", "package.ps1"]
---

# Regole di internazionalizzazione (i18n) di documentazione e script

## Principio
- Tutti i materiali rivolti al pubblico sono bilingui: **inglese come default** (è ciò che vede
  il pubblico) + **italiano affiancato**.
- **L'italiano è la fonte di verità.** Si modifica SEMPRE e SOLO la versione italiana di un
  documento; la versione inglese è una **copia generata**, mai scritta o corretta a mano.
- Dopo ogni modifica a un documento italiano, **rigenerare la controparte inglese** lanciando
  `sync-docs.bat`, che esegue il prompt riusabile interno `MyDocs/prompts/sync-translations.md`
  con Claude Code; poi rivedere il diff prima del commit. Questo evita discordanze fra le due
  lingue. **Entrambi i file sono gitignorati**: sono strumenti locali (`MyDocs/` è privata), e su
  una macchina nuova vanno ricreati — il `.bat` se ne accorge e lo dice invece di fallire a metà.
  Il prompt mostra i diff e applica **solo dopo conferma**; non committa e non pusha mai.
- **Stessa disciplina di parità per TUTTA la doc pubblica** (README, guida, CHANGELOG, sito,
  script — le coppie sotto): **se una modifica IT non ha fatto il suo giro di sync EN nello stesso
  ciclo, la modifica non è finita**. Non si scrive mai l'inglese a mano fuori da `sync-docs.bat`.
- Coppie fonte→generato: `README.it.md`→`README.md`; `Docs/GUIDA_OPERATIVA.md`→
  `Docs/OPERATING_GUIDE.md`; `CHANGELOG.it.md`→`CHANGELOG.md`; `index.it.html`→`index.html`.
  Per gli script `install.ps1`/`package.ps1` la fonte è il 2° argomento di `L` (italiano), l'inglese
  (1° arg) è generato.
- **Etichette della GUI**: in ogni lingua si scrive l'etichetta che l'utente vede a schermo. I
  documenti inglesi usano quindi quella inglese (`**Settings → "Download folder:"**`), senza
  glossa. Fino alla 2.0.0 tenevano l'etichetta italiana con la traduzione fra parentesi, perché
  la GUI era solo italiana: con la GUI bilingue quella ragione è venuta meno. Le voci **già
  rilasciate** del CHANGELOG non si riscrivono — sono un archivio storico.
- CLAUDE.md, i file in `.claude/rules/` e la documentazione interna di sviluppo restano in
  **italiano** e NON si traducono.

## README
- `README.md` = inglese (è la home di GitHub). `README.it.md` = italiano.
- Selettore di lingua in cima a entrambi: `**English** · [Italiano](README.it.md)` e il reciproco.
- Entrambe le versioni DEVONO documentare le opzioni di lingua degli script: se aggiungi o cambi un'opzione, aggiorna ENTRAMBI i README.

## Guida operativa
- `Docs/OPERATING_GUIDE.md` (EN) + `Docs/GUIDA_OPERATIVA.md` (IT), con selettore di lingua reciproco.

## Script PowerShell (install.ps1 / package.ps1)
- Messaggi a schermo in **inglese di default**; italiano con `-Lang IT`.
- Meccanismo: `param([ValidateSet("EN","IT")][string]$Lang="EN")` + helper `L "en" "it"`. Non duplicare le righe a video.
- Cambiare SOLO le stringhe utente: mai la logica o il control flow.

## Sito
- `index.html` (EN default) + `index.it.html` (IT), con toggle di lingua reciproco nella barra di
  navigazione (`<a class="navlang">`). Si traducono testo visibile, `<meta name="description">` e
  `<html lang>`; non si toccano CSS, JavaScript, id/class e percorsi degli asset.

## Navigazione per ancora (DOC_MAP)
- Prima di modificare la documentazione, consulta `MyDocs/DOC_MAP.md` (se presente) e
  targetizza la sezione per ancora invece di leggere i file interi.
- Dopo aver modificato o aggiunto sezioni a un documento sorgente IT, aggiorna subito la mappa e
  lancia `python MyDocs/check_doc_map.py` per verificare che tutte le ancore siano ancora valide.
- Se `MyDocs/` non è presente (macchina di deploy, CI) questa regola degrada silenziosamente:
  è un aiuto di lavoro locale, non una dipendenza di build.
