# Stato della sessione condiviso fra GUI e worker di download.
# Unica fonte di verita' per pausa/annullo: i worker leggono qui prima di ogni chunk.
from PyQt6.QtCore import QMutex, QMutexLocker, QWaitCondition


class SessionState:
    def __init__(self) -> None:
        self._mutex = QMutex()
        self._wait = QWaitCondition()
        self._paused = False
        self._cancelled = False
        self._running = False

    def start(self) -> None:
        with QMutexLocker(self._mutex):
            self._paused = False
            self._cancelled = False
            self._running = True

    def pause(self) -> None:
        with QMutexLocker(self._mutex):
            self._paused = True

    def resume(self) -> None:
        with QMutexLocker(self._mutex):
            self._paused = False
            self._wait.wakeAll()

    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancelled = True
            self._paused = False
            self._running = False
            self._wait.wakeAll()

    def is_paused(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._paused

    def is_cancelled(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._cancelled

    def is_running(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._running

    def wait_if_paused(self) -> None:
        # Blocca il worker chiamante finche' non viene resume() o cancel().
        self._mutex.lock()
        try:
            while self._paused and not self._cancelled:
                self._wait.wait(self._mutex)
        finally:
            self._mutex.unlock()
