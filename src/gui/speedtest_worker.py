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
    PROXY_SPEEDTEST_TIMEOUT,
    PROXY_SPEEDTEST_URL,
    USER_AGENT,
)
from src.core.proxy_url import build_proxies_dict, cache_bust_url

log = logging.getLogger(__name__)


class SpeedTestWorker(QThread):
    # (mbit_per_s, ok) — mbit=0.0 e ok=False se il test fallisce.
    finished_test = pyqtSignal(float, bool)

    def _one_stream(self, _i: int) -> int:
        total = 0
        with requests.get(
            cache_bust_url(LINE_SPEEDTEST_URL), stream=True,
            timeout=LINE_SPEEDTEST_TIMEOUT,
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


class ProxySpeedTestWorker(QThread):
    """Speed test ATTRAVERSO i proxy: misura la banda aggregata che il pool
    erogherebbe. Uno stream per proxy campionato, in parallelo. Diversamente
    dal test di linea, e' resiliente: un proxy lento o caduto contribuisce solo
    i byte effettivamente scaricati prima del timeout, senza far fallire la
    misura complessiva. La banda riportata e' aggregata (byte totali / tempo a
    muro), confrontabile direttamente con quella della linea diretta."""

    # (mbit_per_s, ok) — ok=False solo se NESSUNO stream ha prodotto byte.
    finished_test = pyqtSignal(float, bool)

    def __init__(self, proxies: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._proxies = list(proxies)

    def _one_stream(self, proxy: dict) -> int:
        # Scarica finche' il proxy regge: alla scadenza del timeout (o a fine
        # file) ritorna i byte accumulati. Non solleva: l'eccezione viene
        # assorbita qui per non azzerare il contributo degli altri stream.
        total = 0
        try:
            with requests.get(
                cache_bust_url(PROXY_SPEEDTEST_URL), stream=True,
                timeout=PROXY_SPEEDTEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                proxies=build_proxies_dict(proxy),
            ) as r:
                r.raise_for_status()
                for chunk in r.iter_content(64 * 1024):
                    total += len(chunk)
        except Exception:
            log.debug("Stream speed test proxy interrotto (byte parziali: %d)", total)
        return total

    def run(self) -> None:
        if not self._proxies:
            self.finished_test.emit(0.0, False)
            return
        try:
            t0 = time.monotonic()
            with ThreadPoolExecutor(max_workers=len(self._proxies)) as ex:
                got = list(ex.map(self._one_stream, self._proxies))
            elapsed = time.monotonic() - t0
            total = sum(got)
            if total <= 0:
                self.finished_test.emit(0.0, False)
                return
            bps = total / elapsed if elapsed > 0 else 0.0
            mbit = bps * 8 / 1_000_000
            self.finished_test.emit(round(mbit, 1), True)
        except Exception:
            log.debug("Speed test proxy fallito", exc_info=True)
            self.finished_test.emit(0.0, False)
