# Test di regressione per lo spike di velocita' su download ripresi:
# il monitor (_progress_poller) deve inizializzare prev_bytes al valore
# GIA' scaricato (chunk ripresi da run precedenti), non a zero, altrimenti
# il primo delta conta tutti i byte preesistenti in mezzo secondo e produce
# un bps nell'ordine dei GB/s. Pilota _progress_poller() direttamente
# (time.monotonic e Event.wait monkeypatchati) per evitare timing reale.
import threading
import time

import pytest

from src.downloader.parallel_client import ParallelMegaDownloader


def test_progress_poller_first_delta_excludes_resumed_bytes(monkeypatch):
    dl = ParallelMegaDownloader(proxy_pool=None, n_connections=1)
    resumed_bytes = 50_000_000  # chunk gia' completati da run precedente
    dl._bytes_downloaded = resumed_bytes

    instants = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(instants))

    stop = threading.Event()
    samples: list[float] = []
    wait_calls = {"n": 0}

    def fake_wait(timeout):
        wait_calls["n"] += 1
        if wait_calls["n"] == 1:
            # Avanzamento reale fra il primo e il secondo giro: 4096 byte nuovi.
            with dl._bytes_lock:
                dl._bytes_downloaded += 4096
            return False
        stop.set()
        return True

    monkeypatch.setattr(stop, "wait", fake_wait)

    dl._progress_poller(
        total_size=100_000_000,
        cb=lambda pct: None,
        stop=stop,
        speed_cb=lambda bps, done, total: samples.append(bps),
    )

    assert len(samples) == 2
    # Primo campione: prev_bytes parte dal valore ripreso, non da zero, quindi
    # senza avanzamento reale il delta e' 0 (non i 50_000_000 byte ripresi).
    assert samples[0] == 0.0
    # Secondo campione: solo i byte nuovi (4096) in 1s, velocita' plausibile.
    assert samples[1] == pytest.approx(4096.0)


def test_progress_poller_prev_bytes_seeded_from_current_total(monkeypatch):
    """Stesso scenario ma con un valore ripreso diverso/piu' grande: il primo
    campione deve restare 0, mai un multiplo dei byte ripresi."""
    dl = ParallelMegaDownloader(proxy_pool=None, n_connections=1)
    dl._bytes_downloaded = 500_000_000

    instants = iter([0.0, 0.5])
    monkeypatch.setattr(time, "monotonic", lambda: next(instants))

    stop = threading.Event()
    samples: list[float] = []

    def fake_wait(timeout):
        stop.set()
        return True

    monkeypatch.setattr(stop, "wait", fake_wait)

    dl._progress_poller(
        total_size=1_000_000_000,
        cb=lambda pct: None,
        stop=stop,
        speed_cb=lambda bps, done, total: samples.append(bps),
    )

    assert samples == [0.0]
