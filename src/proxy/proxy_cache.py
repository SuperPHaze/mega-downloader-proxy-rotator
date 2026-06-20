# Cache dei proxy validati: persistita su disco tra sessioni per evitare
# lo scrape iniziale "da zero" all'avvio dell'applicazione.
#
# Vincoli:
# - Solo stdlib (json/datetime/pathlib). Nessun import da `src.gui` o
#   `src.downloader` (regola proxy.md).
# - load/save/clear non sollevano MAI: una cache rotta = log warning +
#   ritorno coerente (`[]` o False).
# - Atomic write via tmp + os.replace: un crash a meta' save non corrompe
#   il file esistente.
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src.core.config import (
    PROXY_CACHE_PATH,
    PROXY_CACHE_SCHEMA_VERSION,
    PROXY_CACHE_TTL_S,
)

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def cache_path() -> Path:
    return _PROJECT_ROOT / PROXY_CACHE_PATH


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def save(
    proxies: list[dict],
    *,
    path: Path | None = None,
    schema_version: int = PROXY_CACHE_SCHEMA_VERSION,
) -> bool:
    """Scrive su disco la cache. Mai solleva: ritorna False su errore."""
    target = path or cache_path()
    payload = {
        "schema": schema_version,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "proxies": proxies,
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        log.info("[proxy_cache] salvati %d proxy in %s", len(proxies), target.name)
        return True
    except OSError as exc:
        log.warning("[proxy_cache] save fallita su %s: %s", target, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def load(
    *,
    path: Path | None = None,
    max_age_s: int = PROXY_CACHE_TTL_S,
    schema_version: int = PROXY_CACHE_SCHEMA_VERSION,
) -> list[dict]:
    """Carica e filtra le entry valide. Mai solleva: ritorna [] su qualunque errore."""
    target = path or cache_path()
    if not target.exists():
        log.info("[proxy_cache] file non presente (%s), prima sessione", target.name)
        return []
    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        log.warning("[proxy_cache] %s non leggibile, ignoro: %s", target.name, exc)
        return []
    if not isinstance(data, dict):
        log.warning("[proxy_cache] %s: payload non e' un oggetto, ignoro", target.name)
        return []
    schema = data.get("schema")
    if schema != schema_version:
        log.warning(
            "[proxy_cache] schema %r sconosciuto (atteso %d), ignoro",
            schema, schema_version,
        )
        return []
    proxies = data.get("proxies")
    if not isinstance(proxies, list):
        log.warning("[proxy_cache] campo 'proxies' assente o non-lista, ignoro")
        return []
    now = datetime.now()
    out: list[dict] = []
    skipped_ttl = 0
    skipped_bad = 0
    for entry in proxies:
        if not isinstance(entry, dict):
            skipped_bad += 1
            continue
        host = entry.get("host")
        port = entry.get("port")
        if not host or not port:
            skipped_bad += 1
            continue
        last_seen = _parse_iso(entry.get("last_seen"))
        if last_seen is None:
            skipped_bad += 1
            continue
        age = (now - last_seen).total_seconds()
        if age < 0 or age > max_age_s:
            skipped_ttl += 1
            continue
        # Normalizza protocol/latency/score per il pool.
        out.append({
            "host": str(host),
            "port": str(port),
            "protocol": str(entry.get("protocol") or "http"),
            "score": int(entry.get("score") or 0),
            "latency_ms": entry.get("latency_ms"),
            "last_seen": entry.get("last_seen"),
        })
    log.info(
        "[proxy_cache] caricati %d proxy validi (%d oltre TTL, %d malformati)",
        len(out), skipped_ttl, skipped_bad,
    )
    return out


def clear(*, path: Path | None = None) -> None:
    """Rimuove il file di cache. Mai solleva."""
    target = path or cache_path()
    try:
        target.unlink(missing_ok=True)
        log.info("[proxy_cache] cache rimossa: %s", target.name)
    except OSError as exc:
        log.warning("[proxy_cache] clear fallita: %s", exc)
