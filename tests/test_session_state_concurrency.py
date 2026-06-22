# Stress di concorrenza per SessionState (src/core/state.py).
# Riproduce il pattern che causava un access violation nativo con le
# primitive Qt (QMutex/QWaitCondition) martellate da decine di thread Python
# puri in un ThreadPoolExecutor (parallel_client._download_chunk): tanti
# thread in busy loop su is_cancelled()/wait_if_paused() mentre un altro
# thread chiama pause/resume/cancel. Con threading.Lock/Condition (stdlib)
# non deve mai crashare, deadlockare, o violare la semantica pausa/annullo.
import threading
import time

from src.core.state import SessionState

N_READERS = 50


def test_concurrent_is_cancelled_and_wait_if_paused_no_crash_no_deadlock():
    state = SessionState()
    state.start()

    errors: list[BaseException] = []
    paused_seen = threading.Event()
    resumed_after_pause: list[bool] = []

    def reader() -> None:
        try:
            local_resumed = False
            # Gira finche' non viene cancellato: il main thread guida la
            # durata dello stress tramite il ciclo pause/resume + cancel.
            while not state.is_cancelled():
                if state.is_paused():
                    paused_seen.set()
                state.wait_if_paused()
                # Se siamo qui dopo aver visto pausa, e non siamo cancellati,
                # vuol dire che resume() ci ha sbloccati correttamente.
                if paused_seen.is_set() and not state.is_cancelled():
                    local_resumed = True
            if local_resumed:
                resumed_after_pause.append(True)
        except BaseException as exc:  # noqa: BLE001 - vogliamo vedere QUALSIASI crash
            errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(N_READERS)]
    for t in readers:
        t.start()

    # Cicla pause/resume per un po' per esercitare il path del Condition.wait().
    for _ in range(20):
        state.pause()
        time.sleep(0.01)
        state.resume()
        time.sleep(0.01)

    # Ora cancella: tutti i reader devono uscire entro un timeout breve.
    state.cancel()

    for t in readers:
        t.join(timeout=10)

    assert not errors, f"thread reader hanno sollevato eccezioni: {errors}"
    for t in readers:
        assert not t.is_alive(), "un reader e' rimasto bloccato dopo cancel() (deadlock)"

    assert state.is_cancelled() is True
    assert state.is_running() is False
    assert resumed_after_pause, "nessun reader ha osservato lo sblocco dopo resume()"


def test_pause_then_resume_unblocks_waiters():
    state = SessionState()
    state.start()
    state.pause()

    unblocked = threading.Event()

    def waiter() -> None:
        state.wait_if_paused()
        unblocked.set()

    t = threading.Thread(target=waiter)
    t.start()

    time.sleep(0.1)
    assert not unblocked.is_set(), "il waiter non doveva sbloccarsi prima di resume()"

    state.resume()
    t.join(timeout=5)

    assert unblocked.is_set()
    assert not t.is_alive()


def test_cancel_unblocks_paused_waiters_without_resume():
    state = SessionState()
    state.start()
    state.pause()

    unblocked = threading.Event()

    def waiter() -> None:
        state.wait_if_paused()
        unblocked.set()

    t = threading.Thread(target=waiter)
    t.start()

    time.sleep(0.1)
    assert not unblocked.is_set()

    state.cancel()
    t.join(timeout=5)

    assert unblocked.is_set()
    assert not t.is_alive()
    assert state.is_cancelled() is True
    assert state.is_paused() is False
