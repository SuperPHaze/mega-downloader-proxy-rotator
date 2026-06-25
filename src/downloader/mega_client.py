# Client Mega seriale: download single-stream via proxy HTTP.
#
# Niente piu' mega.py: usa MegaPublicClient (resolve URL + decifratura
# attributi) + requests con `proxies=` nativo per il transfer dal CDN.
# Decifratura AES-CTR a blocchi durante lo streaming, scrittura diretta
# sul file finale (niente temp file, niente WinError 32).
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable

import requests

from src.core.config import IP_CHECK_URL, PROXY_TIMEOUT, USER_AGENT
from src.core.proxy_url import build_proxies_dict, build_proxy_url
from src.downloader.mega_api import MegaApiError, MegaPublicClient
from src.downloader.mega_crypto import a32_to_str

log = logging.getLogger(__name__)


class MegaCryptoDependencyError(RuntimeError):
    """Dipendenza pycryptodome mancante o non importabile.

    Why: distinguere errori d'ambiente (permanenti) da fallimenti del proxy
    (transitori), così il worker non marca morto un proxy innocente.
    """


_CHUNK = 64 * 1024


class MegaClient:
    def __init__(self, proxy: dict) -> None:
        self.proxy = proxy
        self._proxy_url = build_proxy_url(proxy)
        self._proxies = build_proxies_dict(proxy)

    def get_egress_ip(self) -> str:
        log.debug("IP check via %s", self._proxy_url)
        resp = requests.get(
            IP_CHECK_URL,
            headers={"User-Agent": USER_AGENT},
            proxies=self._proxies,
            timeout=PROXY_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text.strip()

    def get_public_url_info(self, mega_url: str) -> dict | None:
        client = MegaPublicClient(self.proxy, timeout=max(PROXY_TIMEOUT * 4, 30))
        return client.get_public_url_info(mega_url)

    def download(
        self,
        mega_url: str,
        output_dir: Path,
        progress_callback: Callable[[int], None] | None = None,
        speed_callback: Callable[[float, int, int], None] | None = None,
        resolved_callback: Callable[[str, object, "Path"], None] | None = None,
    ) -> Path:
        try:
            from Crypto.Cipher import AES
            from Crypto.Util import Counter
        except ImportError as exc:
            raise MegaCryptoDependencyError(
                f"pycryptodome non importabile ({exc}). "
                "Verifica le dipendenze (pip install -r requirements.txt)."
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        api = MegaPublicClient(self.proxy, timeout=max(PROXY_TIMEOUT * 4, 30))
        info = api.resolve_public_url(mega_url)
        file_name = info["file_name"]
        file_size = info["file_size"]
        cdn_url = info["cdn_url"]
        k = info["k"]
        iv = info["iv"]
        final_path = output_dir / file_name
        # Pattern .part + rename atomico: il client seriale non ha resume,
        # ma un download interrotto non deve mai lasciare un file con il nome
        # finale che il check del worker scambierebbe per completo.
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        log.info(
            "[serial] resolve ok: name=%s size=%d cdn_host=%s",
            file_name, file_size,
            cdn_url.split("/")[2] if "://" in cdn_url else "?",
        )
        # Notifica immediata al worker: nome file noto appena risolto.
        if resolved_callback is not None:
            try:
                resolved_callback(file_name, file_size, final_path)
            except Exception:
                pass

        k_str = a32_to_str(k)
        initial_counter = ((iv[0] << 32) + iv[1]) << 64
        counter = Counter.new(128, initial_value=initial_counter)
        aes = AES.new(k_str, AES.MODE_CTR, counter=counter)

        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        timeout = (PROXY_TIMEOUT, max(PROXY_TIMEOUT * 4, 60))
        resp = requests.get(
            cdn_url, headers=headers, proxies=self._proxies,
            timeout=timeout, stream=True,
        )
        resp.raise_for_status()

        downloaded = 0
        last_pct = -1
        _speed_t = time.monotonic()
        _speed_bytes = 0
        with open(part_path, "wb") as fp:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                fp.write(aes.decrypt(chunk))
                downloaded += len(chunk)
                if file_size > 0:
                    pct = min(99, int(downloaded * 100 / file_size))
                    if progress_callback and pct != last_pct:
                        try:
                            progress_callback(pct)
                        except Exception:
                            pass
                        last_pct = pct
                    if speed_callback:
                        _speed_bytes += len(chunk)
                        now = time.monotonic()
                        dt = now - _speed_t
                        if dt >= 0.5:
                            bps = _speed_bytes / dt
                            _speed_t = now
                            _speed_bytes = 0
                            try:
                                speed_callback(bps, downloaded, file_size)
                            except Exception:
                                pass

        if file_size and downloaded != file_size:
            raise MegaApiError(
                f"download incompleto: {downloaded}/{file_size} byte"
            )
        # Download verificato: promuovi il .part al nome finale.
        os.replace(part_path, final_path)
        if progress_callback:
            try:
                progress_callback(100)
            except Exception:
                pass
        log.info("[serial] download completato: %s (%d B)", final_path, downloaded)
        return final_path
