# Verifica la disciplina di logging (rules/logging.md): i fallimenti ATTESI
# e transitori con i proxy gratuiti (retry esauriti, chunk falliti) devono
# uscire a WARNING, non ERROR. ERROR resta riservato a bug/condizioni
# davvero inattese.
import logging
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from src.core.config import MAX_ATTEMPTS_PER_FILE
from src.core.state import SessionState
from src.downloader import parallel_client
from src.downloader.worker import DownloadWorker
from src.proxy.pool import ProxyPool


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    # DownloadWorker e' un QThread: serve un'istanza di QApplication nel
    # processo. Il metodo sotto test viene chiamato in modo sincrono.
    QApplication.instance() or QApplication([])


def test_abandoned_after_max_attempts_logs_warning_not_error(tmp_path, caplog):
    worker = DownloadWorker(7, "https://mega.nz/file/AAA#BBB", ProxyPool(), SessionState())
    worker._total_attempts = MAX_ATTEMPTS_PER_FILE  # il prossimo tentativo supera il cap

    with caplog.at_level(logging.DEBUG, logger="src.downloader.worker"):
        result = worker._run_cycle_until_success(1, tmp_path)

    assert result is False
    abbandono = [r for r in caplog.records if "abbandono link" in r.message]
    assert abbandono, "il log di abbandono non e' stato scritto"
    assert abbandono[0].levelno == logging.WARNING
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


class _FakePool:
    """Pool minimale: un solo proxy fittizio, nessuna vera rete."""

    def get_next(self) -> dict:
        return {"host": "127.0.0.1", "port": "8080", "protocol": "http"}

    def refill_blocking(self, force: bool = False) -> int:
        return 0

    def penalize(self, proxy, hard: bool = False) -> None:
        pass

    def record_success(self, proxy) -> None:
        pass

    def record_throughput(self, proxy, bps: float) -> None:
        pass


def test_parallel_chunk_exhausted_retries_logs_warning_not_error(tmp_path, monkeypatch, caplog):
    # Forza un solo tentativo per chunk e nessun backoff: il test deve
    # restare rapido. requests.get solleva sempre un errore di connessione,
    # cosi' il chunk esaurisce subito i retry.
    monkeypatch.setattr(parallel_client, "PARALLEL_SEGMENT_RETRIES", 1)
    monkeypatch.setattr(parallel_client, "PARALLEL_SEGMENT_BACKOFF_MAX", 0)

    def _raise_connection_error(*a, **kw):
        raise parallel_client.requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(parallel_client.requests, "get", _raise_connection_error)

    downloader = parallel_client.ParallelMegaDownloader(_FakePool(), n_connections=1)
    # Bypassa il resolve reale (rete + API Mega): file piccolo -> un solo chunk.
    monkeypatch.setattr(
        downloader,
        "_resolve_cdn",
        lambda *a, **kw: (
            "FILEHANDLE", [0, 0, 0, 0], [0, 0],
            "http://cdn.example/test", 16, "testfile.bin",
        ),
    )

    with caplog.at_level(logging.DEBUG, logger="src.downloader.parallel_client"):
        with pytest.raises(RuntimeError, match="chunk falliti"):
            downloader.download(
                "https://mega.nz/file/AAA#BBB",
                Path(tmp_path),
                resolver_proxy={"host": "1.2.3.4", "port": "8080", "protocol": "http"},
            )

    fallito = [r for r in caplog.records if "chunk fallito" in r.message]
    assert fallito, "il log di chunk fallito non e' stato scritto"
    assert fallito[0].levelno == logging.WARNING
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
