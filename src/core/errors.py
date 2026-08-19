# Eccezioni che l'utente legge: portano un CODICE stabile e i suoi parametri.
#
# Perche': fino a qui il messaggio d'errore era una frase italiana scritta al
# punto di `raise`. Per tradurlo servirebbe riconoscere la stringa a valle —
# fragile e destinato a rompersi al primo ritocco del testo. Con un codice, il
# messaggio ha un'identita' che sopravvive alla riscrittura, e la GUI traduce
# quella.
#
# La proprieta' che rende il cambio a basso rischio: `str(exc)` continua a
# produrre la STESSA frase italiana di prima. Tutti i `f"...({exc})"` gia'
# esistenti — nel worker, nei log, nella telemetria, nella concatenazione degli
# errori di chunk — continuano a funzionare identici. Il codice viaggia
# *sotto* al testo, non al suo posto.
#
# Solo stdlib: nessun import di Qt o della GUI (`core` sta sotto, non sopra).
from __future__ import annotations

import logging

from src.core.error_catalog import ERROR_TEXTS_IT, UNEXPECTED

log = logging.getLogger(__name__)

# Chiavi gia' segnalate: un errore nel catalogo non deve riempire i log di
# righe identiche mentre il download prosegue.
_warned: set[str] = set()


def _warn_once(key: str, msg: str, *args: object) -> None:
    if key in _warned:
        return
    _warned.add(key)
    log.warning(msg, *args)


def format_it(code: str, params: dict[str, object]) -> str:
    """Testo italiano di `code`, con i parametri sostituiti.

    NON solleva mai, per nessun motivo: questo codice gira dentro la gestione
    degli errori: un'eccezione qui maschererebbe l'errore vero e farebbe
    cadere il worker sul percorso in cui deve essere piu' solido.

    Ripiego a due livelli:
      - codice sconosciuto -> si usa il codice stesso come testo. Cosi' un
        `raise MegaApiError("una frase libera")` rimasto in giro continua a
        comportarsi come prima invece di mostrare un vuoto;
      - parametri che non combaciano col template -> si mostra il template
        grezzo, che e' comunque diagnosticabile.
    """
    template = ERROR_TEXTS_IT.get(code)
    if template is None:
        _warn_once(code, "Codice d'errore sconosciuto: %r", code)
        return str(code)
    if not params:
        return template
    try:
        return template.format(**params)
    except Exception as exc:      # noqa: BLE001 - vedi docstring
        _warn_once(
            f"{code}#format",
            "Parametri non applicabili al messaggio %s (%s): %s",
            code, exc, template,
        )
        return template


class UserFacingError(Exception):
    """Errore che l'utente leggera'. Porta `error_code` + `params`; `str(exc)`
    resta la frase italiana, che e' cio' che finisce nei log.

    Le sottoclassi che devono restare anche `ValueError`/`RuntimeError`/`OSError`
    mettono SEMPRE `UserFacingError` come PRIMA base: vedi le tre sotto.
    """

    def __init__(self, code: str, **params: object) -> None:
        self.error_code = code
        self.params = params
        super().__init__(format_it(code, params))


# Le tre basi miste. L'ordine non e' estetico:
#
#   - con `OSError` PRIMA, `OSError.__new__` intercetta la costruzione e
#     `InsufficientDiskSpaceError("disk_full", path=...)` muore con
#     "takes no keyword arguments" (provato, non dedotto);
#   - con `UserFacingError` prima, la ricerca di `__init__` lungo l'MRO trova
#     il nostro e la classe resta comunque sottoclasse di OSError/ValueError/
#     RuntimeError, quindi ogni `except` esistente continua a catturarla.
#
# E' il punto che tiene invariato il comportamento del motore: i rami `except`
# di `worker.py` distinguono fatale / abbandono / ritenta proprio su queste
# classi.
class UserFacingValueError(UserFacingError, ValueError):
    """Resta un `ValueError`: `mega_folder` ci conta per saltare le chiavi di
    nodo non decifrabili (`except (ValueError, TypeError)`)."""


class UserFacingRuntimeError(UserFacingError, RuntimeError):
    """Resta un `RuntimeError`: e' cio' che solleva il client parallelo."""


class UserFacingOSError(UserFacingError, OSError):
    """Resta un `OSError`: lo richiede `InsufficientDiskSpaceError`."""


def error_payload(exc: BaseException) -> dict[str, object]:
    """Codice + parametri di un'eccezione, in forma trasportabile.

    Per tutto cio' che non e' nostro — `requests`, `OSError` grezzi, le
    violazioni di contratto interno — ripiega su `unexpected` con il testo
    originale come parametro: la GUI ha sempre qualcosa da rendere, e non
    torna mai a mostrare una stringa cruda.
    """
    if isinstance(exc, UserFacingError):
        return {"code": exc.error_code, "params": dict(exc.params)}
    return {"code": UNEXPECTED, "params": {"error": str(exc)}}
