import pytest
from src.gui.session_clock import SessionClock


def test_elapsed_grows_before_freeze():
    clock = SessionClock()
    t0 = 1000.0
    clock.start(t0)
    assert clock.is_started()
    assert not clock.is_frozen()
    assert clock.elapsed(t0 + 5.0) == pytest.approx(5.0)
    assert clock.elapsed(t0 + 100.0) == pytest.approx(100.0)


def test_update_all_terminated_freezes_clock():
    clock = SessionClock()
    t0 = 1000.0
    clock.start(t0)
    clock.update(t0 + 10.0, all_terminated=True)
    assert clock.is_frozen()
    assert clock.elapsed(t0 + 10.0) == pytest.approx(10.0)
    assert clock.elapsed(t0 + 999.0) == pytest.approx(10.0)


def test_update_not_terminated_after_freeze_unfreezes():
    clock = SessionClock()
    t0 = 1000.0
    clock.start(t0)
    clock.update(t0 + 10.0, all_terminated=True)
    assert clock.is_frozen()
    # Nuovo job: congelo sciolto, il clock riprende dall'origine
    clock.update(t0 + 20.0, all_terminated=False)
    assert not clock.is_frozen()
    assert clock.elapsed(t0 + 30.0) == pytest.approx(30.0)


def test_reset_clears_state():
    clock = SessionClock()
    clock.start(1000.0)
    clock.update(1010.0, all_terminated=True)
    clock.reset()
    assert not clock.is_started()
    assert not clock.is_frozen()
    assert clock.elapsed(9999.0) == 0.0


def test_elapsed_before_start_returns_zero():
    clock = SessionClock()
    assert clock.elapsed(1000.0) == 0.0


def test_update_before_start_is_noop():
    clock = SessionClock()
    clock.update(1000.0, all_terminated=True)
    assert not clock.is_started()
    assert not clock.is_frozen()


def test_double_freeze_is_idempotent():
    clock = SessionClock()
    clock.start(1000.0)
    clock.update(1010.0, all_terminated=True)
    clock.update(1020.0, all_terminated=True)
    # frozen_at resta a 1010.0: elapsed = 10, non 20
    assert clock.elapsed(9999.0) == pytest.approx(10.0)
