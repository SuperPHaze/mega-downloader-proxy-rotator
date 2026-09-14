# Test puri per logging_setup: hook installati senza errori, crash.log
# scrivibile. Non testa faulthandler/Qt in se' (richiederebbe un crash nativo
# o una QApplication), solo che l'installazione non fallisca e il file
# di destinazione sia utilizzabile.
import threading

import pytest

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


class _FakeStream:
    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)

    def flush(self):
        pass

    def isatty(self):
        return False


class _FakeFile:
    def __init__(self):
        self.written = []
        self.flushed = False

    def write(self, data):
        self.written.append(data)

    def flush(self):
        self.flushed = True


class _BrokenFile:
    def write(self, data):
        raise OSError("disco pieno")

    def flush(self):
        raise OSError("disco pieno")


def test_tee_stream_writes_to_both_stream_and_file():
    stream = _FakeStream()
    file = _FakeFile()
    tee = logging_setup._TeeStream(stream, file)

    tee.write("riga di log\n")

    assert stream.written == ["riga di log\n"]
    assert file.written == ["riga di log\n"]
    assert file.flushed is True


def test_tee_stream_write_does_not_raise_if_file_is_broken():
    stream = _FakeStream()
    tee = logging_setup._TeeStream(stream, _BrokenFile())

    tee.write("riga di log\n")  # non deve sollevare

    assert stream.written == ["riga di log\n"]


def test_tee_stream_delegates_unknown_attributes_to_original_stream():
    stream = _FakeStream()
    tee = logging_setup._TeeStream(stream, _FakeFile())

    assert tee.isatty() is False


# ---- avvio silenzioso: nessuna console, quindi nessun flusso originale ------
# Con pythonw.exe sys.stdout/sys.stderr valgono None. Il tee resta l'unico
# consumatore e NON deve sollevare: basterebbe la prima riga di log per far
# cadere l'applicazione prima che la finestra compaia. E' il test piu'
# importante dei tre lavori: copre l'unica cosa che puo' impedire l'avvio.

def test_tee_stream_senza_flusso_originale_scrive_solo_su_file():
    file = _FakeFile()
    tee = logging_setup._TeeStream(None, file)

    scritti = tee.write("riga senza console\n")

    assert file.written == ["riga senza console\n"]
    assert file.flushed is True
    assert scritti == len("riga senza console\n")


def test_tee_stream_senza_flusso_originale_flush_innocuo():
    file = _FakeFile()
    tee = logging_setup._TeeStream(None, file)

    tee.flush()     # non deve sollevare

    assert file.flushed is True


def test_tee_stream_senza_flusso_originale_non_e_un_terminale():
    """`isatty()` deve rispondere, non delegare a None: chi la interroga lo fa
    per decidere se colorare l'output."""
    tee = logging_setup._TeeStream(None, _FakeFile())

    assert tee.isatty() is False


def test_tee_stream_senza_flusso_originale_non_inventa_un_descrittore():
    tee = logging_setup._TeeStream(None, _FakeFile())

    with pytest.raises(OSError):
        tee.fileno()


def test_tee_stream_senza_flusso_originale_non_finge_attributi():
    """Un attributo che non esiste deve risultare assente (`hasattr` False),
    non tornare qualcosa di inventato."""
    tee = logging_setup._TeeStream(None, _FakeFile())

    assert not hasattr(tee, "buffer")
    with pytest.raises(AttributeError):
        tee.encoding


def test_tee_stream_senza_flusso_originale_sopravvive_al_file_rotto():
    """Nessuna console E file rotto: non resta niente, ma nemmeno un'eccezione
    (sarebbe un crash all'avvio senza alcuna traccia visibile)."""
    tee = logging_setup._TeeStream(None, _BrokenFile())

    tee.write("nessuno mi leggera'\n")
    tee.flush()


def test_tee_stream_regge_un_flusso_che_si_rompe_a_meta():
    """Console sparita a sessione avviata: il file deve restare."""
    class _StreamRotto:
        def write(self, data):
            raise OSError("console chiusa")

        def flush(self):
            raise OSError("console chiusa")

    file = _FakeFile()
    tee = logging_setup._TeeStream(_StreamRotto(), file)

    tee.write("riga\n")
    tee.flush()

    assert file.written == ["riga\n"]


def test_excepthook_del_thread_principale_scrive_in_crash_log():
    """Senza console il traceback di un'eccezione non gestita del thread
    principale deve restare in crash.log, dove lo legge tools/report.py."""
    logging_setup.setup_logging()
    scritti = []
    original = logging_setup._write_crash_log
    logging_setup._write_crash_log = scritti.append
    try:
        try:
            raise RuntimeError("boom di prova")
        except RuntimeError as exc:
            logging_setup.log_unhandled_main_exception(
                type(exc), exc, exc.__traceback__,
            )
    finally:
        logging_setup._write_crash_log = original

    assert scritti and "[MAIN-EXC]" in scritti[0]
    assert "boom di prova" in scritti[0]
