---
paths: ["**"]
---

# Regole di workflow globali

## Version bump obbligatorio (ultimo step)
- Al termine di ogni task, PRIMA di dichiarare il lavoro concluso, chiedere all'utente se vuole aggiornare la versione dell'app (`APP_VERSION` in `src/core/config.py`).
- Se l'utente conferma, proporre il nuovo valore seguendo semver: PATCH per bugfix/piccole modifiche, MINOR per nuove funzionalita', MAJOR per breaking change.
- Se l'utente rifiuta, procedere senza modificare la versione.
- Non aggiornare mai `APP_VERSION` autonomamente: serve sempre conferma esplicita.
