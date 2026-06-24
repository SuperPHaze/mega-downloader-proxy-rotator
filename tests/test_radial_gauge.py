# Test puri per gauge_fraction(): nessuna rete, nessun Qt.
import math

from src.gui.radial_gauge import gauge_fraction


def test_normal_fraction():
    assert gauge_fraction(50.0, 200.0) == 0.25


def test_peak_zero_returns_zero():
    assert gauge_fraction(50.0, 0.0) == 0.0


def test_peak_negative_returns_zero():
    assert gauge_fraction(50.0, -10.0) == 0.0


def test_current_above_peak_clamped_to_one():
    assert gauge_fraction(300.0, 200.0) == 1.0


def test_current_zero_returns_zero():
    assert gauge_fraction(0.0, 200.0) == 0.0


def test_non_finite_current_returns_zero():
    assert gauge_fraction(math.inf, 200.0) == 0.0
    assert gauge_fraction(math.nan, 200.0) == 0.0


def test_non_finite_peak_returns_zero():
    assert gauge_fraction(50.0, math.inf) == 0.0
    assert gauge_fraction(50.0, math.nan) == 0.0
