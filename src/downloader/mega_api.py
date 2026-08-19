# Mini-client per l'API pubblica Mega: parse URL + chiamata `g=1` -> URL CDN
# + decifratura attributi cifrati. Niente upload/login con account/folder.
#
# Sostituisce mega.py per il nostro use-case (download di link pubblici via
# proxy HTTP). Usa una requests.Session per-istanza con proxies espliciti:
# niente monkey-patch globali, niente threading.local.
from __future__ import annotations

import json
import logging
import random
import threading
import time
from typing import Callable

import requests

from src.core.errors import UserFacingError
from src.core.file_naming import sanitize_file_name
from src.core.mega_links import (
    MegaFolderJobLink,
    parse_file_link,
    parse_folder_job_url,
    parse_folder_link,
)
from src.core.proxy_url import build_proxies_dict
from src.downloader.mega_crypto import (
    base64_to_a32,
    base64_url_decode,
    decrypt_attr,
    derive_file_key,
)

log = logging.getLogger(__name__)

API_URL = "https://g.api.mega.co.nz/cs"
_SEQ_LOCK = threading.Lock()
_SEQUENCE_NUMBER = random.randint(0, 0xFFFFFFFF)


class MegaApiError(UserFacingError):
    """Errore dell'API pubblica Mega.

    Il codice numerico dell'API (-3, -9...) non e' piu' un attributo a
    parte: vive in `params["api_code"]` del messaggio `api_error_code`,
    insieme a tutti gli altri parametri. Un solo posto invece di due.
    """

    @property
    def message(self) -> str:
        """Testo italiano. Compatibilita' con chi leggeva `.message`."""
        return str(self)


def _next_seq() -> int:
    global _SEQUENCE_NUMBER
    with _SEQ_LOCK:
        seq = _SEQUENCE_NUMBER
        _SEQUENCE_NUMBER += 1
    return seq


def _normalize_proxy(proxy: dict | None) -> dict[str, str] | None:
    if not proxy:
        return None
    if "http" in proxy and "https" in proxy:
        return {"http": proxy["http"], "https": proxy["https"]}
    if "protocol" in proxy and "host" in proxy and "port" in proxy:
        return build_proxies_dict(proxy)
    raise ValueError(f"formato proxy non riconosciuto: {sorted(proxy.keys())}")


class MegaPublicClient:
    def __init__(
        self,
        proxy: dict | None = None,
        timeout: float = 30.0,
        should_abort: Callable[[], bool] | None = None,
    ) -> None:
        self._session = requests.Session()
        self.timeout = timeout
        # Callback opzionale per la cancellazione cooperativa: se ritorna True
        # durante un backoff, il resolve si interrompe subito invece di dormire
        # fino a decine di secondi (un Annulla arrivato durante il retry non
        # deve restare appeso). None = nessuna cancellazione (comportamento
        # storico), usato dai path che non hanno un SessionState a portata.
        self._should_abort = should_abort
        proxies = _normalize_proxy(proxy)
        if proxies:
            self._session.proxies.update(proxies)

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Dorme `seconds` a passi da 0.5s, ma esce subito (ritornando True) se
        `should_abort()` diventa vero. Ritorna False se ha dormito tutto."""
        step = 0.5
        elapsed = 0.0
        while elapsed < seconds:
            if self._should_abort is not None and self._should_abort():
                return True
            time.sleep(step)
            elapsed += step
        return False

    def _api_request(
        self, payload: dict, extra_params: dict[str, str] | None = None
    ) -> dict:
        """`extra_params` finisce nella QUERY della POST (oltre a `id`).

        Serve alle cartelle condivise, che richiedono `n=<folder_id>` come
        parametro di query per dare contesto alla chiamata.
        """
        body = json.dumps([payload])
        last_err: Exception | None = None
        # Retry esplicito su -3 (EAGAIN) e su errori di rete, bounded a 5 tentativi.
        # Sostituisce il clamp tenacity sul vecchio mega.py. Backoff cappato a 30s
        # (era 60) e INTERROMPIBILE via should_abort per non ignorare un Annulla.
        for attempt in range(1, 6):
            params: dict[str, object] = {"id": _next_seq()}
            if extra_params:
                params.update(extra_params)
            try:
                resp = self._session.post(
                    API_URL, params=params, data=body, timeout=self.timeout,
                )
                resp.raise_for_status()
                data = json.loads(resp.text)
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_err = exc
                log.warning("[mega_api] tentativo %d errore rete/parse: %s", attempt, exc)
                if self._sleep_interruptible(min(30, 2 ** attempt)):
                    raise MegaApiError("resolve_cancelled") from exc
                continue
            item = data[0] if isinstance(data, list) and data else data
            if isinstance(item, int):
                if item == 0:
                    return {}
                if item == -3:
                    log.info("[mega_api] -3 (EAGAIN), retry %d/5", attempt)
                    if self._sleep_interruptible(min(30, 2 ** attempt)):
                        raise MegaApiError("resolve_cancelled")
                    continue
                raise MegaApiError("api_error_code", api_code=item)
            if not isinstance(item, dict):
                raise MegaApiError("api_unexpected_response", response=repr(item))
            return item
        raise MegaApiError("api_retries_exhausted", error=str(last_err))

    def _parse_url(self, url: str) -> tuple[str, str]:
        """(handle, chiave b64) di un link a FILE singolo.

        I link a cartella non sono risolvibili qui: vanno prima espansi in job
        per-file (vedi downloader/mega_folder.py).
        """
        link = parse_file_link(url)
        if link is not None:
            return link.handle, link.key_b64
        if parse_folder_link(url) is not None:
            raise MegaApiError("folder_link_not_downloadable", url=url)
        raise MegaApiError("url_not_parsable", url=url)

    def resolve_public_url(self, mega_url: str) -> dict:
        job = parse_folder_job_url(mega_url)
        if job is not None:
            return self._resolve_folder_node(job)
        handle, key_b64 = self._parse_url(mega_url)
        raw_key = base64_to_a32(key_b64)
        k, iv = derive_file_key(raw_key)
        resp = self._api_request({"a": "g", "g": 1, "p": handle})
        if "g" not in resp:
            raise MegaApiError("file_not_accessible", response=repr(resp))
        cdn_url = resp["g"]
        try:
            file_size = int(resp["s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MegaApiError("size_missing", error=str(exc)) from exc
        attribs = decrypt_attr(base64_url_decode(resp.get("at", "")), k)
        raw_name = attribs.get("n") if attribs else None
        # Sanitizza alla SORGENTE: il nome così risolto è quello usato da tutti
        # i client (seriale/parallelo), dallo storico e dalla GUI. Blocca path
        # traversal, caratteri riservati Windows e device name (CON/NUL/…).
        file_name = (
            sanitize_file_name(raw_name, fallback=f"mega_{handle}")
            if raw_name else f"mega_{handle}"
        )
        return {
            "handle": handle,
            "k": k,
            "iv": iv,
            "cdn_url": cdn_url,
            "file_size": file_size,
            "file_name": file_name,
        }

    def _resolve_folder_node(self, job: MegaFolderJobLink) -> dict:
        """Risolve un NODO dentro una cartella condivisa (job auto-contenuto).

        Differenze rispetto al file pubblico singolo:
          - la chiave a 8 word e' gia' decifrata e viaggia dentro il job, non
            va ricavata dal fragment di un link pubblico;
          - la richiesta `g` usa `n` DUE VOLTE con due significati diversi:
            nel PAYLOAD `n` e' l'handle del nodo, nella QUERY `n` e' l'id della
            cartella condivisa che da' contesto alla chiamata. Non e' un refuso.
          - il nome file NON si prende dagli attributi della risposta: e' gia'
            stato deciso (sanificato e de-collisionato) in fase di espansione e
            viaggia nel job, cosi' il path su disco resta stabile fra i retry.
        """
        raw_key = base64_to_a32(job.node_key_b64)
        if len(raw_key) < 8:
            raise MegaApiError(
                "node_key_too_short",
                words=len(raw_key),
                node=job.node_handle,
            )
        k, iv = derive_file_key(raw_key)
        resp = self._api_request(
            {"a": "g", "g": 1, "n": job.node_handle},
            extra_params={"n": job.folder_id},
        )
        if "g" not in resp:
            raise MegaApiError(
                "folder_file_not_accessible", response=repr(resp)
            )
        cdn_url = resp["g"]
        try:
            file_size = int(resp["s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MegaApiError("size_missing", error=str(exc)) from exc
        file_name = sanitize_file_name(
            job.file_name, fallback=f"mega_{job.node_handle}"
        )
        return {
            "handle": job.node_handle,
            "k": k,
            "iv": iv,
            "cdn_url": cdn_url,
            "file_size": file_size,
            "file_name": file_name,
        }

    def list_folder(self, folder_id: str) -> list[dict]:
        """Elenca RICORSIVAMENTE i nodi di una cartella pubblica Mega.

        Una sola chiamata per cartella: `r:1` restituisce l'intero albero, che
        viene poi decifrato in locale con la master key del link. Ritorna la
        lista grezza dei nodi (`f` della risposta): la decifratura e la
        ricostruzione dell'albero stanno in downloader/mega_folder.py.
        """
        resp = self._api_request(
            {"a": "f", "c": 1, "r": 1, "ca": 1}, extra_params={"n": folder_id},
        )
        nodes = resp.get("f")
        if not isinstance(nodes, list):
            raise MegaApiError(
                "folder_listing_unavailable", response=repr(resp)
            )
        return [n for n in nodes if isinstance(n, dict)]

    def get_public_url_info(self, mega_url: str) -> dict | None:
        """Versione lightweight: solo `name` e `size`."""
        try:
            info = self.resolve_public_url(mega_url)
        except MegaApiError as exc:
            log.warning("[mega_api] get_public_url_info fallita: %s", exc)
            return None
        return {"name": info["file_name"], "size": info["file_size"]}
