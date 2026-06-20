# Identita' del tool (nome, acronimo, autore, nick, link, logo) risolta a tre
# livelli: default cotti -> cache locale dell'ultimo manifest valido ->
# override remoto (scaricato da gui/branding_fetch.py). Logica pura: nessun
# I/O di rete e nessun import Qt qui, solo stdlib (vedi regola core/: solo
# stdlib + PyQt6, e qui non serve nemmeno PyQt6).
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import (
    DEFAULT_APP_ACRONYM,
    DEFAULT_APP_NAME,
    DEFAULT_AUTHOR,
    DEFAULT_LINKS,
    DEFAULT_NICK,
    TOOL_ID,
)

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = _PROJECT_ROOT / "branding_cache.json"

# Estensioni di logo riconosciute dai magic bytes (vedi detect_image_format).
# Il file di cache mantiene l'estensione reale (gif resta animabile, le
# immagini statiche restano png/jpg) invece di forzare sempre .png.
LOGO_CACHE_FORMATS = ("gif", "png", "jpg")


def logo_cache_path(fmt: str) -> Path:
    return _PROJECT_ROOT / f"branding_logo.{fmt}"


def detect_image_format(data: bytes) -> str | None:
    """Rileva il formato dai magic bytes. None se non riconosciuto: il
    chiamante deve scartare il file (fallback al logo di default)."""
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"\x89PNG":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    return None


def clear_stale_logo_cache(keep: Path | None = None) -> None:
    """Rimuove i branding_logo.* con estensione diversa da `keep`, cosi' un
    cambio di formato (es. png -> gif) non lascia file orfani in giro."""
    for fmt in LOGO_CACHE_FORMATS:
        p = logo_cache_path(fmt)
        if p != keep and p.exists():
            try:
                p.unlink()
            except OSError:
                pass


@dataclass(frozen=True)
class Branding:
    name: str
    acronym: str
    author: str
    nick: str
    links: dict = field(default_factory=dict)
    logo_path: str | None = None


def defaults() -> Branding:
    # logo_path None: il fallback offline e' per-tema (LOGO_LIGHT_PATH/LOGO_DARK_PATH
    # in config.py), scelto dalla GUI che conosce il tema corrente. Questo modulo
    # e' puro e non deve decidere il tema.
    return Branding(
        name=DEFAULT_APP_NAME,
        acronym=DEFAULT_APP_ACRONYM,
        author=DEFAULT_AUTHOR,
        nick=DEFAULT_NICK,
        links=dict(DEFAULT_LINKS),
        logo_path=None,
    )


def _coerce_str(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def merge_manifest(raw: dict, logo_cache_file: str | None = None) -> Branding:
    """Fonde common + tools[TOOL_ID] del manifest sui default. Campi
    mancanti o di tipo inatteso ricadono sul default; chiavi sconosciute
    sono ignorate. `logo_cache_file` e' il nome del file scaricato in
    cache (es. "branding_logo.gif") associato a QUESTO manifest; se assente
    o il file non esiste piu' `logo_path` resta None (la GUI sceglie il
    fallback offline per-tema, vedi LOGO_LIGHT_PATH/LOGO_DARK_PATH)."""
    base = defaults()

    common = raw.get("common") if isinstance(raw, dict) else None
    common = common if isinstance(common, dict) else {}
    tools = raw.get("tools") if isinstance(raw, dict) else None
    tools = tools if isinstance(tools, dict) else {}
    tool = tools.get(TOOL_ID)
    tool = tool if isinstance(tool, dict) else {}

    author = _coerce_str(common.get("author"), base.author)
    nick = _coerce_str(common.get("nick"), base.nick)

    links = base.links
    links_raw = common.get("links")
    if isinstance(links_raw, dict):
        coerced = {
            str(k): v.strip()
            for k, v in links_raw.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }
        if coerced:
            links = coerced

    name = _coerce_str(tool.get("name"), base.name)
    acronym = _coerce_str(tool.get("acronym"), base.acronym)

    logo_path = base.logo_path
    if logo_cache_file:
        candidate = _PROJECT_ROOT / logo_cache_file
        if candidate.exists():
            logo_path = str(candidate)

    return Branding(
        name=name, acronym=acronym, author=author, nick=nick,
        links=links, logo_path=logo_path,
    )


def load_cached() -> Branding | None:
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        return None
    logo_cache_file = payload.get("logo_cache_file")
    logo_cache_file = logo_cache_file if isinstance(logo_cache_file, str) else None
    return merge_manifest(manifest, logo_cache_file)


def save_cache(manifest: dict, logo_cache_file: str | None) -> None:
    payload = {"manifest": manifest, "logo_cache_file": logo_cache_file}
    try:
        CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        log.warning("Impossibile salvare la cache branding in %s", CACHE_PATH)


def resolve() -> Branding:
    """Valore da mostrare subito: cache se c'e', altrimenti i default."""
    return load_cached() or defaults()
