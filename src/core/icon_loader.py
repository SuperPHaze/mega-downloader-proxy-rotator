# Costruzione robusta della QIcon dell'app: .ico multi-risoluzione con
# fallback al .png e diagnostica via log se nessuno dei due si carica.
# Condiviso da main.py (icona QApplication) e MainWindow (icona finestra)
# per evitare di duplicare la logica di fallback nei due punti.
from __future__ import annotations

import logging

from PyQt6.QtGui import QIcon

from src.core.config import APP_ICON_ICO_PATH, APP_ICON_PNG_PATH

log = logging.getLogger(__name__)


def build_app_icon() -> QIcon:
    icon = QIcon()
    if APP_ICON_ICO_PATH.exists():
        icon.addFile(str(APP_ICON_ICO_PATH))
    if icon.isNull() and APP_ICON_PNG_PATH.exists():
        icon.addFile(str(APP_ICON_PNG_PATH))
    if icon.isNull():
        log.warning(
            "Icona app non caricata: %s e %s assenti o non validi (QIcon.isNull()).",
            APP_ICON_ICO_PATH, APP_ICON_PNG_PATH,
        )
    return icon
