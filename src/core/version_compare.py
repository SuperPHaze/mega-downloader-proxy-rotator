# Confronto versioni semver (MAJOR.MINOR.PATCH). Solo stdlib, nessun I/O.
from __future__ import annotations


def parse_semver(version: str) -> tuple[int, int, int] | None:
    v = version.strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    parts = v.split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def is_newer(latest: str, current: str) -> bool | None:
    """True se `latest` > `current`. None se uno dei due non e' un semver valido."""
    lv = parse_semver(latest)
    cv = parse_semver(current)
    if lv is None or cv is None:
        return None
    return lv > cv
