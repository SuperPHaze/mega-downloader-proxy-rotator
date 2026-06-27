# Speed test della linea in un QThread dedicato: nessuna rete sul thread GUI.
# Diretto, SENZA proxy (proxies={"http": None, "https": None}): misura la banda
# dell'utente, non quella di un proxy. Non tocca pool/downloader.
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import (
    LINE_SPEEDTEST_STREAMS,
    LINE_SPEEDTEST_TIMEOUT,
    LINE_SPEEDTEST_URL,
    USER_AGENT,
)

log = logging.getLogger(__name__)


class SpeedTestWorker(QThread):
    # (mbit_per_s, ok) — mbit=0.0 e ok=False se il test fallisce.
    finished_test = pyqtSignal(float, bool)

    def _one_stream(self, _i: int) -> int:
        total = 0
        with requests.get(
            LINE_SPEEDTEST_URL, stream=True, timeout=LINE_SPEEDTEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            proxies={"http": None, "https": None},   # diretto, niente proxy
        ) as r:
            r.raise_for_status()
            for chunk in r.iter_content(64 * 1024):
                total += len(chunk)
        return total

    def run(self) -> None:
        try:
            t0 = time.monotonic()
            with ThreadPoolExecutor(max_workers=LINE_SPEEDTEST_STREAMS) as ex:
                got = list(ex.map(self._one_stream, range(LINE_SPEEDTEST_STREAMS)))
            elapsed = time.monotonic() - t0
            total = sum(got)
            bps = total / elapsed if elapsed > 0 else 0.0
            mbit = bps * 8 / 1_000_000
            self.finished_test.emit(round(mbit, 1), True)
        except Exception:
            log.debug("Speed test linea fallito", exc_info=True)
            self.finished_test.emit(0.0, False)
