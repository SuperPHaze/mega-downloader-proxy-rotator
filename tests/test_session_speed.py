# Test puri per SessionSpeedStats: nessuna rete, nessun Qt.
from src.gui.session_speed import SessionSpeedStats


def test_no_samples_has_neutral_values():
    stats = SessionSpeedStats()
    assert stats.average == 0.0
    assert stats.peak is None
    assert stats.minimum is None


def test_zero_samples_are_ignored():
    stats = SessionSpeedStats()
    stats.sample(0.0)
    stats.sample(-5.0)
    assert stats.average == 0.0
    assert stats.peak is None
    assert stats.minimum is None


def test_average_peak_minimum_over_positive_samples():
    stats = SessionSpeedStats()
    stats.sample(1000.0)
    stats.sample(3000.0)
    stats.sample(2000.0)
    assert stats.average == 2000.0
    assert stats.peak == 3000.0
    assert stats.minimum == 1000.0


def test_mixed_zero_and_positive_samples():
    stats = SessionSpeedStats()
    stats.sample(0.0)
    stats.sample(500.0)
    stats.sample(0.0)
    stats.sample(1500.0)
    assert stats.average == 1000.0
    assert stats.peak == 1500.0
    assert stats.minimum == 500.0


def test_reset_clears_all_statistics():
    stats = SessionSpeedStats()
    stats.sample(1000.0)
    stats.sample(2000.0)
    stats.reset()
    assert stats.average == 0.0
    assert stats.peak is None
    assert stats.minimum is None
