# Resa a video degli errori: da CODICE + parametri al testo nella lingua scelta.
#
# E1 ha messo un codice sotto a ogni errore che l'utente legge; il testo
# italiano vive nel catalogo di `core/` (dove serve ai LOG) e viene innestato
# in `strings_it.py` come chiavi `err.*`. Qui c'e' il pezzo mancante: la
# funzione che, dato il payload, produce la frase nella lingua corrente.
#
# Tre cose non ovvie, tutte volute:
#
#  1. **Annidamento** (opzione C del progetto). Il testo che l'utente legge non
#     e' una frase ma una composizione su tre livelli: cornice del worker ->
#     aggregato dei chunk -> errore del singolo chunk. Il payload di E1 porta i
#     livelli sotto come DATO (`cause`, `children`), non come stringa gia'
#     composta: `_resolve_nested` li rende per primi e li innesta al posto del
#     parametro testuale corrispondente. In italiano il risultato coincide
#     carattere per carattere con la concatenazione di prima, perche' ogni
#     figlio reso in italiano e' esattamente il suo `str(exc)`.
#
#  2. **Codici con il punto**. Un codice senza punto e' uno slug del catalogo
#     del motore e si rende come `err.<codice>`. Un codice che contiene un
#     punto e' gia' una chiave i18n intera (`main_window.restart_refused`): e'
#     la forma usata dagli errori che nascono nella GUI e non hanno un
#     corrispettivo nel motore. Cosi' restano traducibili e si ritraducono a
#     caldo come tutto il resto, senza sporcare il catalogo di `core/` con
#     testi che i log non vedranno mai.
#
#  3. **Alias dell'abbandono**. Il worker usa DUE formulazioni per la stessa
#     causa: fra parentesi per il tentativo fallito («IP check fallito (…)»),
#     con i due punti per l'abbandono («IP check fallito: …»). Il canale
#     `abandoned_detail` porta pero' il codice del canale `failed`, cioe' la
#     forma con le parentesi. `ABANDON_ALIASES` rimette la formulazione giusta
#     al confine, cosi' la frase dell'abbandono resta identica a quella di
#     prima della traduzione. Vale SOLO per l'abbandono: il tentativo fallito
#     continua a usare la forma con le parentesi.
from __future__ import annotations

from src.gui.i18n import t, tn

# Payload singolo -> parametro testuale che sostituisce nel template.
_NESTED_ONE = {
    "cause": "error",       # `download_failed_paren`: la causa vera del fallimento
    "reason": "reason",     # `attempt_frame`: il motivo dentro la cornice
}
# Lista di payload -> parametro testuale, uniti come li univa il motore.
_NESTED_MANY = {
    "children": "detail",   # `chunks_failed`: i primi tre errori di chunk
}
_JOIN = "; "

# Profondita' massima della ricorsione. I livelli veri sono tre (cornice,
# aggregato, chunk): il limite e' una cintura di sicurezza, non un vincolo di
# progetto — un payload malformato non deve poter mandare la GUI in ricorsione
# infinita mentre sta gia' mostrando un errore.
_MAX_DEPTH = 6

# Codici il cui testo INGLESE cambia col conteggio, e parametro che sceglie la
# forma. L'italiano NON cambia (resta la frase del catalogo nelle due forme:
# e' il testo di prima della traduzione e non si tocca), ma senza la coppia
# l'inglese direbbe «1 minutes» e «1 words». Non sono casi di scuola: il limite
# di tempo per file si imposta a partire da 1 minuto, e una chiave malformata
# puo' avere una sola word.
#
# L'elenco vive qui ed e' l'unica fonte: un test verifica che i dizionari
# abbiano le forme plurali esattamente per questi codici e per nessun altro.
_COUNT_PARAM = {
    "time_limit_exceeded": "minutes",
    "node_key_too_short": "words",
    "crypto_bad_key_length": "words",
    "crypto_file_key_short": "words",
    "folder_key_invalid": "words",
    "folder_key_too_short": "words",
    "chunk_retries_exhausted": "attempts",
}

# Codice del canale `failed` -> codice da usare per l'ABBANDONO. Vedi il
# punto 3 in testa al modulo.
ABANDON_ALIASES = {
    "ip_check_failed_paren": "ip_check_failed",
    "download_failed_paren": "download_failed",
    "pool_empty_short": "pool_empty",
}


def _is_payload(value: object) -> bool:
    """Un payload e' `{"code": ..., "params": <mappa>}`.

    Il controllo su `params` non e' pedanteria: senza, un `params` che non e'
    un dizionario farebbe sollevare `dict()` piu' in basso — dentro la
    gestione degli errori, dove questo modulo non deve sollevare mai."""
    return (
        isinstance(value, dict)
        and "code" in value
        and isinstance(value.get("params"), dict)
    )


def _key_for(code: str) -> str:
    """Chiave i18n di un codice d'errore (vedi punto 2 in testa al modulo)."""
    return code if "." in code else f"err.{code}"


def _count_of(code: str, params: dict) -> int | None:
    """Conteggio che sceglie singolare o plurale, se il codice lo prevede."""
    name = _COUNT_PARAM.get(code)
    if name is None:
        return None
    try:
        return int(params[name])
    except (KeyError, TypeError, ValueError):
        return None      # parametro assente o non numerico: si usa `t()`


def render_error(code: str, params: dict | None = None, _depth: int = 0) -> str:
    """Testo dell'errore nella lingua corrente.

    Non solleva mai: gira dentro la gestione degli errori, dove un'eccezione
    maschererebbe il guasto vero. `t()` ha gia' i suoi ripieghi (chiave
    assente -> italiano -> slug; parametri che non combaciano -> testo grezzo).
    """
    p = dict(params) if isinstance(params, dict) else {}
    # Nota: si tocca SOLO cio' che e' davvero un payload. `reason` e `detail`
    # arrivano gia' come testo quando non c'e' niente da annidare (e `reason`
    # e' anche un parametro vero di `attempt_frame`): toglierli comunque
    # lascerebbe il segnaposto a video.
    for src, dst in _NESTED_ONE.items():
        if not _is_payload(p.get(src)):
            continue
        p[dst] = _render_child(p.pop(src), _depth)
    for src, dst in _NESTED_MANY.items():
        children = p.get(src)
        if not isinstance(children, (list, tuple)):
            continue
        rendered = [_render_child(c, _depth) for c in children if _is_payload(c)]
        if not rendered:
            # Nessun figlio leggibile: si tiene `detail`, cioe' il testo che il
            # motore aveva gia' composto. Resta italiano anche in inglese, ma
            # e' l'unica informazione rimasta: perderla sarebbe peggio.
            continue
        p.pop(src)
        p[dst] = _JOIN.join(rendered)
    key = _key_for(code)
    count = _count_of(code, p)
    testo = t(key, **p) if count is None else tn(key, count, **p)
    # `t()`/`tn()` ricascano sulla CHIAVE quando non la conoscono. In quel caso
    # si mostra il codice nudo, com'e' scritto nel contratto di `format_it`:
    # `err.<codice>` aggiungerebbe rumore nostro a un messaggio gia' degradato.
    # Il WARNING l'ha gia' loggato `t()`, una volta sola.
    return str(code) if testo == key else testo


def _render_child(payload: dict, depth: int) -> str:
    """Un livello piu' in basso. Oltre il tetto ci si ferma al codice: e' una
    cintura di sicurezza contro un payload malformato, non un caso reale."""
    if depth >= _MAX_DEPTH:
        return str(payload.get("code", ""))
    return render_error(payload["code"], payload["params"], depth + 1)


def resolve_payloads(params: dict) -> dict:
    """Copia di `params` con i payload d'errore sostituiti dal testo reso.

    Serve alla riga di stato della finestra: memorizzando gia' il testo, al
    cambio lingua la cornice si tradurrebbe e la parte d'errore no. Ricordando
    il payload e rendendolo al disegno, cambiano insieme.
    """
    return {
        name: render_error(value["code"], value["params"]) if _is_payload(value)
        else value
        for name, value in params.items()
    }
