---
paths: ["**"]
---

# Regola: documentazione allineata e checklist di rilascio

## Principio (Definition of Done)
Una modifica NON è "finita" finché codice e documentazione non sono allineati.
- `src/core/config.py` è la **fonte di verità per i numeri** (mai citare valori a memoria).
- L'**italiano è la fonte** dei documenti; l'inglese si **rigenera col sync** (vedi `docs-i18n.md`),
  mai scritto a mano.

## A ogni modifica funzionale (feature o fix che cambia comportamento, parametri o UI)
1. **CHANGELOG**: aggiungere la voce sotto `[Non rilasciato]` (Aggiunto/Modificato/Corretto) in `CHANGELOG.it.md`.
2. **Valutare l'impatto** e aggiornare SOLO le fonti italiane toccate:
   - `Docs/GUIDA_OPERATIVA.md` — se cambia comportamento, parametri, sezioni;
   - `README.it.md` — se cambiano funzioni, uso, numeri, requisiti;
   - `index.it.html` — se cambiano claim/numeri rivolti all'utente;
   - `CLAUDE.md` — se cambia architettura/moduli/convenzioni (interno).
3. **Verificare i numeri** citati contro `config.py`.
4. **Rigenerare l'inglese** col sync (`sync-docs.bat`) e rivedere il diff.
Nessun documento deve restare indietro rispetto al codice.

## A ogni rilascio (bump versione)
1. Timbrare in `CHANGELOG.it.md`: `[Non rilasciato]` → `[X.Y.Z] — AAAA-MM-GG`; rigenerare EN.
2. Pass di coerenza: numeri vs `config.py`, nome ufficiale, versione/badge uniformi (config + README + sito).
3. Sync EN completo; verificare parità IT↔EN e link.
4. Pubblicazione: pre-flight + zip + push come da guida interna.

## Sintesi operativa
CHANGELOG aggiornato → doc impattate allineate (fonti IT) → numeri verificati su `config.py` →
sync EN → (al rilascio) timbro versione + coerenza globale.
