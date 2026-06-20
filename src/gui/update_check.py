# Controllo aggiornamenti su GitHub. Gira in QThread dedicato: nessuna
# chiamata di rete sul thread della GUI.
from __future__ import annotations

import logging

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import APP_VERSION, GITHUB_OWNER, GITHUB_REPO
from src.core.version_compare import is_newer

log = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 6

STATUS_UP_TO_DATE = "up_to_date"
STATUS_AVAILABLE = "available"
STATUS_UNKNOWN = "unknown"


def updates_enabled() -> bool:
    """Costanti GITHUB_OWNER/GITHUB_REPO non valorizzate = controllo disattivato."""
    return bool(GITHUB_OWNER and GITHUB_REPO)


def repo_url() -> str:
    return f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"


def _release_api_url() -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


class UpdateCheckWorker(QThread):
    # (status, latest_version) — latest_version vuota se status != "available".
    finished_check = pyqtSignal(str, str)

    def run(self) -> None:
        if not updates_enabled():
            self.finished_check.emit(STATUS_UNKNOWN, "")
            return
        try:
            resp = requests.get(_release_api_url(), timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            tag = resp.json().get("tag_name", "")
        except Exception:
            log.debug("Controllo aggiornamenti non riuscito (rete o repo non disponibile)", exc_info=True)
            self.finished_check.emit(STATUS_UNKNOWN, "")
            return
        newer = is_newer(tag, APP_VERSION)
        if newer is None:
            self.finished_check.emit(STATUS_UNKNOWN, "")
        elif newer:
            latest = tag[1:] if tag[:1] in ("v", "V") else tag
            self.finished_check.emit(STATUS_AVAILABLE, latest)
        else:
            self.finished_check.emit(STATUS_UP_TO_DATE, "")
