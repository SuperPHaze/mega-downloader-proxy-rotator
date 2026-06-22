# Test puri per logging_setup: hook installati senza errori, crash.log
# scrivibile. Non testa faulthandler/Qt in se' (richiederebbe un crash nativo
# o una QApplication), solo che l'installazione non fallisca e il file
# di destinazione sia utilizzabile.
import threading

from src.core import logging_setup


def test_setup_logging_is_idempotent_and_returns_log_path():
    path1 = logging_setup.setup_logging()
    path2 = logging_setup.setup_logging()
    assert path1 == path2
    assert path1.name == "app.log"


def test_setup_logging_installs_threading_excepthook():
    logging_setup.setup_logging()
    assert threading.excepthook is logging_setup._threading_excepthook


def test_crash_log_path_is_writable():
    logging_setup.setup_logging()
    crash_path = logging_setup.crash_log_path()
    assert crash_path.name == "crash.log"
    # setup_logging() apre il file in append: se ha avuto successo, il
    # modulo tiene un handle aperto e scrivibile.
    assert logging_setup._crash_file_handle is not None
    assert not logging_setup._crash_file_handle.closed
