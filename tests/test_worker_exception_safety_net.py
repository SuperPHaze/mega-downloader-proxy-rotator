# Verifica che un'eccezione imprevista dentro DownloadWorker.run() venga
# loggata con il file_id PRIMA che il thread termini (e non sparisca in
# silenzio), poi rilanciata senza cambiare il comportamento esistente.
import logging

import pytest
from PyQt6.QtWidgets import QApplication

from src.core.state import SessionState
from src.downloader.worker import DownloadWorker
from src.proxy.pool import ProxyPool


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    # DownloadWorker e' un QThread: serve un'istanza di QApplication nel
    # processo, ma run() qui viene chiamato in modo sincrono (non .start()),
    # quindi non serve un event loop attivo.
    QApplication.instance() or QApplication([])


def test_unhandled_exception_is_logged_with_file_id_then_reraised(caplog):
    worker = DownloadWorker(7, "https://mega.nz/file/AAA#BBB", ProxyPool(), SessionState())
    worker._run_cycle_until_success = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))

    with caplog.at_level(logging.ERROR, logger="src.downloader.worker"):
        with pytest.raises(RuntimeError, match="boom"):
            worker.run()

    matching = [r for r in caplog.records if "eccezione non gestita nel worker" in r.message]
    assert matching, "il log della rete di sicurezza non e' stato scritto"
    assert "[file 7]" in matching[0].message
