# Costruzione robusta della QIcon dell'app: .ico multi-risoluzione con
# fallback al .png e diagnostica via log se nessuno dei due si carica.
# Condiviso da main.py (icona QApplication + finestra + area di notifica) e
# MainWindow per evitare di duplicare la logica di fallback nei due punti.
#
# Perche' i fotogrammi si caricano UNO PER UNO invece di lasciare fare a
# `QIcon.addFile(<file.ico>)`: con quella sola chiamata l'insieme delle
# dimensioni disponibili lo decide il lettore ICO di Qt, e non e' scritto da
# nessuna parte che debba esporle tutte. Con Qt 6.11 le espone (misurato:
# 16/24/32/48/64/128/256), ma Windows chiede l'icona a misure diverse per la
# barra, la finestra e il commutatore di finestre: se un giorno ne arrivasse
# una sola, le altre sarebbero un ingrandimento sfocato della stessa immagine
# e nessuno se ne accorgerebbe da qui. Leggendo i fotogrammi con QImageReader
# la cosa non dipende piu' dal lettore.
#
# Il controllo di riuscita e' `availableSizes()`, non `isNull()`: e' la
# domanda giusta ("quante misure sono entrate?") e non dipende da quando Qt
# decide di leggere il file.
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtGui import QIcon, QImageReader, QPixmap

from src.core.config import APP_ICON_ICO_PATH, APP_ICON_PNG_PATH

log = logging.getLogger(__name__)


def _add_all_frames(icon: QIcon, path: Path) -> int:
    """Aggiunge a `icon` OGNI immagine contenuta in `path` (un .ico ne ha
    molte, un .png una sola). Ritorna quante ne ha aggiunte davvero.

    Non solleva: un file assente, illeggibile o corrotto vale zero
    fotogrammi, che e' esattamente cio' che il chiamante deve sapere per
    passare al ripiego.
    """
    added = 0
    try:
        reader = QImageReader(str(path))
        if not reader.canRead():
            return 0
        count = max(1, reader.imageCount())
        for index in range(count):
            if index > 0 and not reader.jumpToImage(index):
                break
            image = reader.read()
            if image.isNull():
                continue
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                continue
            icon.addPixmap(pixmap)
            added += 1
    except Exception:       # pragma: no cover - difensivo: Qt senza plugin immagini
        log.warning("Lettura icona fallita: %s", path, exc_info=True)
    return added


def build_app_icon() -> QIcon:
    """QIcon dell'applicazione: .ico multi-risoluzione, ripiego al .png.

    Ritorna una QIcon vuota (mai None) se non si carica nulla, dopo averlo
    scritto nel log: senza icona l'app parte comunque, ma la diagnosi deve
    restare leggibile a distanza di mesi.
    """
    icon = QIcon()
    frames = _add_all_frames(icon, APP_ICON_ICO_PATH)
    if frames == 0:
        # Il ripiego scatta davvero: `_add_all_frames` torna 0 sia se il file
        # manca sia se c'e' ma non si legge (il secondo caso, con la vecchia
        # catena basata su `isNull()`, dipendeva da un dettaglio interno di Qt).
        frames = _add_all_frames(icon, APP_ICON_PNG_PATH)
        if frames > 0:
            log.warning(
                "Icona .ico non caricata (%s): uso il ripiego .png (%s)",
                APP_ICON_ICO_PATH, APP_ICON_PNG_PATH,
            )
    if frames == 0 or not icon.availableSizes():
        log.warning(
            "Icona app non caricata: %s e %s assenti o non validi "
            "(nessuna dimensione disponibile).",
            APP_ICON_ICO_PATH, APP_ICON_PNG_PATH,
        )
    return icon
