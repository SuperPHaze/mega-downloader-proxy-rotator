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
import re
import threading
import time
from pathlib import Path

import requests

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
_FILE_HANDLE_RE = re.compile(r"/file/([A-Za-z0-9_-]+)#([A-Za-z0-9_,-]+)")
_LEGACY_HANDLE_RE = re.compile(r"#!([A-Za-z0-9_-]+)!([A-Za-z0-9_,-]+)")


class MegaApiError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
        url = f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"
        return {"http": url, "https": url}
    raise ValueError(f"formato proxy non riconosciuto: {sorted(proxy.keys())}")


class MegaPublicClient:
    def __init__(self, proxy: dict | None = None, timeout: float = 30.0) -> None:
        self._session = requests.Session()
        self.timeout = timeout
        proxies = _normalize_proxy(proxy)
        if proxies:
            self._session.proxies.update(proxies)

    def _api_request(self, payload: dict) -> dict:
        body = json.dumps([payload])
        last_err: Exception | None = None
        # Retry esplicito su -3 (EAGAIN) e su errori di rete, bounded a 5 tentativi.
        # Sostituisce il clamp tenacity sul vecchio mega.py.
        for attempt in range(1, 6):
            params = {"id": _next_seq()}
            try:
                resp = self._session.post(
                    API_URL, params=params, data=body, timeout=self.timeout,
                )
                resp.raise_for_status()
                data = json.loads(resp.text)
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_err = exc
                log.warning("[mega_api] tentativo %d errore rete/parse: %s", attempt, exc)
                time.sleep(min(60, 2 ** attempt))
                continue
            item = data[0] if isinstance(data, list) and data else data
            if isinstance(item, int):
                if item == 0:
                    return {}
                if item == -3:
                    log.info("[mega_api] -3 (EAGAIN), retry %d/5", attempt)
                    time.sleep(min(60, 2 ** attempt))
                    continue
                raise MegaApiError(f"API Mega ha risposto codice {item}", code=item)
            if not isinstance(item, dict):
                raise MegaApiError(f"API Mega: risposta inattesa {item!r}")
            return item
        raise MegaApiError(f"API Mega: 5 tentativi esauriti ({last_err})")

    def _parse_url(self, url: str) -> tuple[str, str]:
        m = _FILE_HANDLE_RE.search(url)
        if m:
            return m.group(1), m.group(2)
        m = _LEGACY_HANDLE_RE.search(url)
        if m:
            return m.group(1), m.group(2)
        raise MegaApiError(f"URL Mega non parsabile: {url}")

    def resolve_public_url(self, mega_url: str) -> dict:
        handle, key_b64 = self._parse_url(mega_url)
        raw_key = base64_to_a32(key_b64)
        k, iv = derive_file_key(raw_key)
        resp = self._api_request({"a": "g", "g": 1, "p": handle})
        if "g" not in resp:
            raise MegaApiError(f"File non accessibile (API senza 'g'): {resp!r}")
        cdn_url = resp["g"]
        try:
            file_size = int(resp["s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MegaApiError(f"size mancante o invalida: {exc}") from exc
        attribs = decrypt_attr(base64_url_decode(resp.get("at", "")), k)
        raw_name = attribs.get("n") if attribs else None
        file_name = Path(raw_name).name if raw_name else f"mega_{handle}"
        if not file_name:
            file_name = f"mega_{handle}"
        return {
            "handle": handle,
            "k": k,
            "iv": iv,
            "cdn_url": cdn_url,
            "file_size": file_size,
            "file_name": file_name,
        }

    def get_public_url_info(self, mega_url: str) -> dict | None:
        """Versione lightweight: solo `name` e `size`."""
        try:
            info = self.resolve_public_url(mega_url)
        except MegaApiError as exc:
            log.warning("[mega_api] get_public_url_info fallita: %s", exc)
            return None
        return {"name": info["file_name"], "size": info["file_size"]}
