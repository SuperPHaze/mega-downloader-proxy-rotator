---
paths: ["README*.md", "CHANGELOG*.md", "Docs/**/*.md", "index*.html", "install.ps1", "package.ps1"]
---

# Regole di internazionalizzazione (i18n) di documentazione e script

## Principio
- Tutti i materiali rivolti al pubblico sono bilingui: **inglese come default** (è ciò che vede
  il pubblico) + **italiano affiancato**.
- **L'italiano è la fonte di verità.** Si modifica SEMPRE e SOLO la versione italiana di un
  documento; la versione inglese è una **copia generata**, mai scritta o corretta a mano.
- Dopo ogni modifica a un documento italiano, **rigenerare la controparte inglese** eseguendo il
  prompt riusabile interno `Docs/prompts/sync-translations.md` (non pubblicato, gitignorato) con Claude Code, e rivedere il diff prima
  del commit. Questo evita discordanze tra le due lingue.
- Coppie fonte→generato: `README.it.md`→`README.md`; `Docs/GUIDA_OPERATIVA.md`→
  `Docs/OPERATING_GUIDE.md`; `CHANGELOG.it.md`→`CHANGELOG.md`; (futuro) `index.it.html`→`index.html`.
  Per gli script `install.ps1`/`package.ps1` la fonte è il 2° argomento di `L` (italiano), l'inglese
  (1° arg) è generato.
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
- `index.html` (EN default) + versione IT con toggle di lingua. [Da fare]
