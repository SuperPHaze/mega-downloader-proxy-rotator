# Stato della sessione condiviso fra GUI e worker di download.
# Unica fonte di verita' per pausa/annullo: i worker leggono qui prima di ogni chunk.
#
# Implementato con threading.Condition (stdlib) invece di QMutex/QWaitCondition:
# sotto alta concorrenza (decine di thread Python puri in un ThreadPoolExecutor,
# non QThread) le primitive Qt hanno causato un access violation nativo
# intermittente in is_cancelled(). threading.Lock/Condition sono pensate per
# essere martellate da thread Python qualsiasi e non hanno questo problema.
import threading


class SessionState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wait = threading.Condition(self._lock)
        self._paused = False
        self._cancelled = False
        self._running = False

    def start(self) -> None:
        with self._lock:
            self._paused = False
            self._cancelled = False
            self._running = True

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._wait.notify_all()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._paused = False
            self._running = False
            self._wait.notify_all()

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def wait_if_paused(self) -> None:
        # Blocca il worker chiamante finche' non viene resume() o cancel().
        with self._lock:
            while self._paused and not self._cancelled:
                self._wait.wait()
