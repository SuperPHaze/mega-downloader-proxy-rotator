# Test puri per SessionSpeedStats: nessuna rete, nessun Qt.
import math

from src.core.config import SPEED_SAMPLE_CEILING_BPS
from src.gui.session_speed import SessionSpeedStats, is_plausible_bps


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


def test_non_finite_samples_are_ignored():
    stats = SessionSpeedStats()
    stats.sample(math.inf)
    stats.sample(math.nan)
    stats.sample(-math.inf)
    assert stats.average == 0.0
    assert stats.peak is None
    assert stats.minimum is None


def test_sample_above_ceiling_is_ignored_as_spike():
    """Riproduce il bug del picco impossibile: un campione spurio da GB/s
    (es. il primo delta di un resume contaminato dai byte gia' su disco)
    non deve avvelenare picco/media/minima."""
    stats = SessionSpeedStats()
    stats.sample(1000.0)
    stats.sample(SPEED_SAMPLE_CEILING_BPS + 1)
    assert stats.peak == 1000.0
    assert stats.average == 1000.0


def test_sample_at_ceiling_is_accepted():
    stats = SessionSpeedStats()
    stats.sample(SPEED_SAMPLE_CEILING_BPS)
    assert stats.peak == SPEED_SAMPLE_CEILING_BPS


def test_is_plausible_bps_rejects_non_finite_and_negative_and_over_ceiling():
    assert not is_plausible_bps(math.inf)
    assert not is_plausible_bps(math.nan)
    assert not is_plausible_bps(-1.0)
    assert not is_plausible_bps(SPEED_SAMPLE_CEILING_BPS + 1)


def test_is_plausible_bps_accepts_zero_and_normal_values():
    assert is_plausible_bps(0.0)
    assert is_plausible_bps(1000.0)
    assert is_plausible_bps(SPEED_SAMPLE_CEILING_BPS)
