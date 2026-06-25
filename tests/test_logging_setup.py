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
