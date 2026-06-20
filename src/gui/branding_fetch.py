# Scarica il manifest di branding (nome/autore/link/logo) da remoto e,
# se presente, il logo del tool. Gira in QThread dedicato: nessuna chiamata
# di rete sul thread della GUI. Fallimento sempre silenzioso (offline,
# manifest malformato, repo assente): l'app continua a mostrare cache/default.
from __future__ import annotations

import json
import logging

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

from src.core.branding import (
    clear_stale_logo_cache,
    detect_image_format,
    logo_cache_path,
    merge_manifest,
    save_cache,
)
from src.core.config import BRANDING_MANIFEST_URL, TOOL_ID

log = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 6
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_LOGO_BYTES = 5 * 1024 * 1024


def branding_enabled() -> bool:
    return bool(BRANDING_MANIFEST_URL)


def _get_limited(url: str, max_bytes: int) -> bytes | None:
    """GET con limite di dimensione rispettato anche se il server non manda
    Content-Length: l'eccesso interrompe lo streaming senza bufferizzare."""
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
        content_length = resp.headers.get("Content-Length")
        if content_length is not None and int(content_length) > max_bytes:
            return None
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    except Exception:
        log.debug("GET %s non riuscito (rete o risorsa non disponibile)", url, exc_info=True)
        return None


class BrandingFetchWorker(QThread):
    branding_updated = pyqtSignal(object)  # Branding

    def run(self) -> None:
        if not branding_enabled():
            return
        raw = _get_limited(BRANDING_MANIFEST_URL, _MAX_MANIFEST_BYTES)
        if raw is None:
            return
        try:
            manifest = json.loads(raw)
        except Exception:
            log.debug("Manifest branding non e' JSON valido", exc_info=True)
            return
        if not isinstance(manifest, dict):
            return

        logo_cache_file = self._maybe_fetch_logo(manifest)
        save_cache(manifest, logo_cache_file)
        self.branding_updated.emit(merge_manifest(manifest, logo_cache_file))

    def _maybe_fetch_logo(self, manifest: dict) -> str | None:
        """Scarica il logo del tool se referenziato e valido. Ritorna il nome
        del file salvato in cache (es. "branding_logo.gif") o None in ogni
        caso dubbio (nessun logo_url, errore di rete, formato non valido)."""
        tools = manifest.get("tools")
        tool = tools.get(TOOL_ID) if isinstance(tools, dict) else None
        logo_url = tool.get("logo_url") if isinstance(tool, dict) else None
        if not isinstance(logo_url, str) or not logo_url.lower().startswith(("http://", "https://")):
            return None

        data = _get_limited(logo_url, _MAX_LOGO_BYTES)
        if data is None:
            return None

        pix = QPixmap()
        if not pix.loadFromData(data) or pix.isNull():
            log.debug("Logo branding scaricato non valido (QPixmap.isNull())")
            return None

        fmt = detect_image_format(data)
        if fmt is None:
            log.debug("Formato logo branding non riconosciuto, scartato")
            return None

        target = logo_cache_path(fmt)
        try:
            target.write_bytes(data)
        except Exception:
            log.warning("Impossibile salvare il logo branding in cache: %s", target)
            return None

        clear_stale_logo_cache(keep=target)
        return target.name
