---
paths: ["src/gui/**", "src/core/state.py", "src/core/config.py",
        "src/core/download_history.py", "tools/demo/**"]
---

# Regola: il demo runner e' cittadino di prima classe

## Perche'
`tools/demo/demo_runner.py` produce i video demo e la galleria di ogni release
(vedi la sezione "Contratto con MDPR" in cima al file). Dipende da API precise
della GUI del tool — molte private (nomi di classi, slot con underscore,
attributi interni), non solo pubbliche. Se cambiano senza aggiornare il
runner, il video della prossima release e' rotto e ce ne accorgiamo tardi
(a ridosso del rilascio, non quando la modifica e' stata fatta).

## Regola
Quando in un ciclo di lavoro tocchi UNA di queste cose:
- una classe/slot/attributo della GUI che appare nel "Contratto" del runner;
- l'API di `TR` in `src/gui/i18n.py`;
- la struttura di `preferences.json` o `session_state.json`;
- i campi di `Job`/`JobsModel` in `src/gui/jobs_model.py`;
allora, **nello stesso ciclo**:
1. Aggiorna `tools/demo/demo_runner.py` (codice + Sezione "Contratto con MDPR" in cima).
2. Lancia `pytest tests/test_demo_runner_smoke.py -v` (esegue `--dry-run`, <5s) e verifica che passi.
3. Se il cambio e' non-triviale (rinomina di uno slot usato dal runner, cambio
   di comportamento non catturabile da un `hasattr`), considera anche un giro
   reale del runner (`python tools/demo/demo_runner.py --lang both`, ~20-90 min)
   prima di considerare "finito" il ciclo.

## Come sapere se qualcosa e' impattato
Se non sei sicuro, apri la sezione "Contratto con MDPR" in cima a
`tools/demo/demo_runner.py` e cerca il nome della classe/metodo/attributo che
stai toccando. Se compare li', il runner e' impattato. Il Contratto elenca
anche cosa il `--dry-run` NON puo' verificare (comportamento, non firma) —
per quei punti serve un giro reale o un controllo a mano.

## Non e' una regola cosmetica
Un runner rotto significa che alla prossima release non hai video/screenshot.
Rifarlo di corsa il giorno del rilascio e' l'errore che questa regola previene.
