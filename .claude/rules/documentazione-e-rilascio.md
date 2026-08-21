---
paths: ["**"]
---

# Regola: documentazione allineata e checklist di rilascio

## Principio (Definition of Done) — NON NEGOZIABILE
**Perché**: fra un anno vogliamo poter modificare o riprendere in mano questo tool — noi stessi o un LLM
a cui lo passiamo — leggendo **solo** la sua documentazione. Se la doc è desincronizzata dal codice,
questa possibilità è persa e il tool diventa incomprensibile a distanza di tempo. La doc **è** la memoria
del progetto.

La documentazione si aggiorna **insieme** al codice, **nello stesso ciclo di lavoro**. Una modifica NON è
"finita" finché OGNI documento impattato non è allineato al comportamento reale del tool. **Avere la
documentazione non aggiornata rispetto al codice NON è accettabile.**

Quando cambia qualcosa di rilevante — una feature, un fix che cambia comportamento/parametri/UI, nuovi
moduli, una nuova struttura — vanno aggiornati **nello stesso ciclo, TUTTI** i documenti impattati (fonti
IT; l'inglese si rigenera col sync, mai a mano):
- **README** (`README.it.md` → `README.md`): funzioni, uso, requisiti, numeri-vetrina.
- **Guida operativa** (`Docs/GUIDA_OPERATIVA.md` → `Docs/OPERATING_GUIDE.md`): comportamento, parametri,
  sezioni nuove, tabella numeri §12, limiti noti §14.
- **Sito** (`index.it.html` → `index.html`): claim, numeri e passi rivolti all'utente; badge di versione.
- **CHANGELOG** (`CHANGELOG.it.md` → `CHANGELOG.md`): voce sotto `[Non rilasciato]`.
- **CLAUDE.md**: mappa moduli (inclusi i **file nuovi**), flusso dati, convenzioni, gotcha.
- **`.claude/rules/`**: la regola d'area, se cambia o si aggiunge una convenzione.
- **`MyDocs/DOC_MAP.md`**: ancore delle sezioni nuove o rinominate, poi `python MyDocs/check_doc_map.py`
  per confermare che tutte le ancore reggano.

`src/core/config.py` resta la **fonte di verità per i numeri** (mai citarli a memoria). Nessuna eccezione e
nessun "lo aggiorno dopo": se non sai se un documento è impattato, **aprilo e verifica**. La checklist di
rilascio (sotto) è il controllo FINALE, non un sostituto di questo aggiornamento continuo.

## Regola sui numeri nei documenti
I numeri vivono in `config.py` e, in prosa, nella tabella §12 della guida (`Docs/GUIDA_OPERATIVA.md`).
README e sito **non** ripetono valori specifici di `config.py`, salvo i due numeri-vetrina concordati
(**chunk 32 MB** e **10 connessioni per file**): per tutti gli altri rimandano alla guida.
Le altre sezioni della guida possono citare numeri in prosa (è il documento tecnico), ma devono
coincidere con `config.py` e con la tabella §12.

## A ogni modifica funzionale (feature o fix che cambia comportamento, parametri o UI)
1. **CHANGELOG**: aggiungere la voce sotto `[Non rilasciato]` (Aggiunto/Modificato/Corretto) in `CHANGELOG.it.md`.
2. **Valutare l'impatto** e aggiornare SOLO le fonti italiane toccate:
   - `Docs/GUIDA_OPERATIVA.md` — se cambia comportamento, parametri, sezioni;
   - `README.it.md` — se cambiano funzioni, uso, numeri, requisiti;
   - `index.it.html` — se cambiano claim/numeri rivolti all'utente;
   - `CLAUDE.md` — se cambia architettura/moduli/convenzioni (interno).
3. **Verificare i numeri** citati contro `config.py`.
4. **Rigenerare l'inglese** col sync (`sync-docs.bat`) e rivedere il diff.
5. **Test del "fra un anno"**: chiediti se una persona nuova (o un LLM) che legge SOLO la doc IT
   aggiornata capisce cosa fa questa modifica e come integrarla. Se no, la doc non è ancora abbastanza.
Nessun documento deve restare indietro rispetto al codice.

## A ogni rilascio (bump versione)
1. Timbrare in `CHANGELOG.it.md`: `[Non rilasciato]` → `[X.Y.Z] — AAAA-MM-GG`; rigenerare EN.
2. Pass di coerenza: numeri vs `config.py`, nome ufficiale, versione/badge uniformi (config + README + sito).
3. Sync EN completo; verificare parità IT↔EN e link.
4. Pubblicazione: pre-flight + zip + push come da guida interna.

## Sintesi operativa
CHANGELOG aggiornato → doc impattate allineate (fonti IT) → numeri verificati su `config.py` →
sync EN → (al rilascio) timbro versione + coerenza globale.
