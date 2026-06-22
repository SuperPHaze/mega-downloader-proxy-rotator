# Test puri per l'isteresi armato/disarmato del BackgroundPoolRefresher.
# Pilotano _tick() direttamente (nessun thread/sleep reale) per verificare
# che un pool che oscilla intorno alla soglia non scateni refill a raffica.
import time

from src.core.state import SessionState
from src.proxy.refresher import BackgroundPoolRefresher


class _FakePool:
    def __init__(self, alive: int) -> None:
        self.alive = alive
        self.refill_calls = 0

    def size(self) -> int:
        return self.alive

    def refill_blocking(self, force: bool = False) -> int:
        self.refill_calls += 1
        return 0


def _make_refresher(pool, low=40, high=80, min_interval=45, max_interval=300):
    r = BackgroundPoolRefresher(
        pool,
        SessionState(),
        threshold_low=low,
        threshold_high=high,
        min_interval_s=min_interval,
        max_interval_s=max_interval,
    )
    # Stato come dopo start(initial_force=False): armato, refill "appena fatto".
    r._last_refill_ts = time.monotonic()
    r._armed = True
    return r


def test_below_low_triggers_refill_when_armed():
    pool = _FakePool(alive=30)
    r = _make_refresher(pool)
    r._last_refill_ts = time.monotonic() - 1000  # ben oltre min_interval
    r._tick()
    assert pool.refill_calls == 1
    assert r._armed is False


def test_second_drop_within_min_interval_does_not_refill_again():
    pool = _FakePool(alive=30)
    r = _make_refresher(pool)
    r._last_refill_ts = time.monotonic() - 1000
    r._tick()
    assert pool.refill_calls == 1

    # Pool resta basso (oscilla sotto soglia) ma e' passato pochissimo tempo
    # dall'ultimo refill: niente secondo refill.
    pool.alive = 25
    r._tick()
    assert pool.refill_calls == 1


def test_disarmed_does_not_rearm_until_high_threshold():
    pool = _FakePool(alive=30)
    r = _make_refresher(pool)
    r._last_refill_ts = time.monotonic() - 1000
    r._tick()
    assert pool.refill_calls == 1
    assert r._armed is False

    # Pool risale ma resta sotto HIGH: ancora disarmato, nessun refill anche
    # se e' passato oltre min_interval (ma non oltre max_interval, altrimenti
    # scatterebbe il trigger timed_out indipendente dall'isteresi).
    pool.alive = 60
    r._last_refill_ts = time.monotonic() - (r.min_interval + 5)
    r._tick()
    assert r._armed is False
    assert pool.refill_calls == 1

    # Pool torna sano (>= HIGH): si riarma, ma senza un nuovo calo sotto LOW
    # non scatta un refill.
    pool.alive = 80
    r._tick()
    assert r._armed is True
    assert pool.refill_calls == 1


def test_rearmed_and_below_low_again_triggers_new_refill():
    pool = _FakePool(alive=30)
    r = _make_refresher(pool)
    r._last_refill_ts = time.monotonic() - 1000
    r._tick()
    assert pool.refill_calls == 1

    pool.alive = 80  # riarma
    r._tick()
    assert r._armed is True

    pool.alive = 20  # scende di nuovo sotto LOW
    r._last_refill_ts = time.monotonic() - 1000  # oltre min_interval
    r._tick()
    assert pool.refill_calls == 2


def test_timed_out_triggers_refill_even_when_disarmed():
    pool = _FakePool(alive=60)  # ne' sotto LOW ne' >= HIGH
    r = _make_refresher(pool, max_interval=300)
    r._armed = False
    r._last_refill_ts = time.monotonic() - 301  # oltre max_interval
    r._tick()
    assert pool.refill_calls == 1


def test_min_interval_blocks_a_second_timed_out_refill_too_soon():
    pool = _FakePool(alive=60)  # ne' sotto LOW ne' >= HIGH: solo il timeout puo' scattare
    r = _make_refresher(pool, max_interval=300, min_interval=45)
    r._armed = False
    r._last_refill_ts = time.monotonic() - 301  # oltre max_interval: refill forzato
    r._tick()
    assert pool.refill_calls == 1

    # Il refill ha appena resettato _last_refill_ts: un secondo tick
    # immediato non deve ri-scattare anche se concettualmente "timed_out"
    # potrebbe tornare vero in scenari di clock anomali — qui verifichiamo
    # semplicemente che min_interval protegga dal doppio trigger a ridosso.
    r._tick()
    assert pool.refill_calls == 1
