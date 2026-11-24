"""The unfinished queue. File IDs also identify the partial downloads on disk."""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path

from src.core.config import SESSION_STATE_PATH
from src.core.file_naming import job_url_hash

log = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = 1  # file_ids and next_id extend the original URL-only format.


def _path() -> Path:
    return _PROJECT_ROOT / SESSION_STATE_PATH


def save(urls: list[str] | dict[int, str], *, next_id: int = 0) -> bool:
    """Write atomically. Older versions can still read the URL list."""
    target = _path()
    payload = {"schema": _SCHEMA, "saved_at": datetime.now().isoformat(timespec="seconds")}
    if isinstance(urls, dict):
        payload.update(urls=list(urls.values()), file_ids=list(urls),
                       next_id=max(next_id, max(urls, default=-1) + 1))
    else:
        payload["urls"] = list(urls)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError as exc:
        log.warning("[session_store] save fallita: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _read() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("[session_store] load fallita, ignoro: %s", exc)
        return {}
    if isinstance(data, dict) and data.get("schema") == _SCHEMA and isinstance(data.get("urls"), list):
        return data
    return {}


def load() -> list[str]:
    return [u for u in _read().get("urls", []) if isinstance(u, str) and u]


def _valid_id(value: object) -> bool:
    # IDs cross Qt signals as signed 32-bit integers.
    return type(value) is int and 0 <= value < 2**31 - 1


def _legacy_ids(urls: list[str], root: Path) -> tuple[dict[int, str], int]:
    """Recover only unambiguous old hash directories in the selected destination."""
    occurrences = Counter(urls)
    if not occurrences:
        return {}, 0
    hashes = {job_url_hash(url): url for url in occurrences}
    candidates = defaultdict(list)
    reserved = Counter()
    try:
        for entry in root.iterdir():
            prefix, _, suffix = entry.name.rpartition("_")
            url = hashes.get(prefix)
            if url is None or not suffix.isascii() or not suffix.isdecimal() or len(suffix) > 10:
                continue
            file_id = int(suffix)
            if _valid_id(file_id) and suffix == str(file_id):
                reserved[file_id] += 1
                if not entry.is_symlink() and entry.is_dir():
                    candidates[url].append(file_id)
    except OSError as exc:
        log.debug("[session_store] cartella precedente non leggibile: %s", exc)
    jobs = {ids[0]: url for url, ids in candidates.items()
            if len(ids) == 1 and occurrences[url] == 1 and reserved[ids[0]] == 1}
    # Reserve even ambiguous directories: a fresh job must not write to them.
    return jobs, max(reserved, default=-1) + 1


def restore_jobs(links: list[str], root: Path) -> tuple[dict[int, str], int]:
    """Match the edited draft by exact URL and occurrence, in its current order."""
    data = _read()
    urls = data.get("urls", [])
    ids = data.get("file_ids")
    if (isinstance(ids, list) and len(ids) == len(urls)
            and all(_valid_id(fid) for fid in ids) and len(set(ids)) == len(ids)):
        saved = {fid: url for fid, url in zip(ids, urls) if isinstance(url, str) and url}
        next_id = max(ids, default=-1) + 1
        if _valid_id(data.get("next_id")):
            next_id = max(next_id, data["next_id"])
    else:
        saved, next_id = _legacy_ids([u for u in urls if isinstance(u, str) and u], root)

    available = defaultdict(deque)
    for fid, url in saved.items():
        available[url].append(fid)
    jobs = {}
    for url in links:
        if available[url]:
            fid = available[url].popleft()
        else:
            fid = next_id
            next_id += 1
        jobs[fid] = url
    return jobs, next_id


def clear() -> None:
    """Rimuove il file di stato. Mai solleva."""
    try:
        _path().unlink(missing_ok=True)
    except OSError as exc:
        log.warning("[session_store] clear fallita: %s", exc)
