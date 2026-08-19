# Infrastruttura comune ai test Qt: UNA sola QApplication per l'intera sessione,
# tenuta viva fino alla fine.
#
# Perche' serve: in PyQt6 la distruzione della QApplication cancella l'oggetto
# C++ di TUTTI i QObject del processo, compresi i singleton di modulo creati
# all'import (`gui.i18n.TR`). I moduli di test che facevano
# `QApplication.instance() or QApplication([])` senza tenerne il riferimento
# lasciavano l'istanza al garbage collector: quando veniva raccolta, un
# QObject usato da un test successivo risultava "wrapped C/C++ object has been
# deleted" e il processo moriva senza nemmeno stampare il resoconto.
# Con questa fixture l'istanza esiste prima di ogni test e nessuno la raccoglie.
#
# La piattaforma offscreen evita di aprire finestre vere: i test restano
# eseguibili in sessione headless e senza rete.
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Riferimento a livello di modulo: sopravvive anche allo smontaggio della
# fixture, cosi' l'istanza non viene mai raccolta a meta' sessione.
_APP = None


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """QApplication condivisa. Restituisce None se PyQt6 non e' installato:
    i test puri devono restare eseguibili comunque (chi ha bisogno di Qt usa
    gia' `pytest.importorskip`)."""
    global _APP
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:         # pragma: no cover - ambiente senza PyQt6
        yield None
        return
    _APP = QApplication.instance() or QApplication([])
    yield _APP
