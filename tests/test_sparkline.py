# Test puri per sparkline_points(): nessuna rete, nessun Qt.
from src.gui.sparkline import sparkline_points


def test_fewer_than_two_points_returns_empty():
    assert sparkline_points([], 100.0, 20.0) == []
    assert sparkline_points([5.0], 100.0, 20.0) == []


def test_two_points_span_full_width():
    pts = sparkline_points([1.0, 2.0], 100.0, 20.0)
    assert len(pts) == 2
    assert pts[0][0] == 0.0
    assert pts[1][0] == 100.0


def test_max_value_sits_at_top_margin():
    pts = sparkline_points([10.0, 20.0, 5.0], 90.0, 24.0)
    margin = 2.0
    # Il punto col valore massimo (indice 1) e' al margine superiore.
    assert pts[1][1] == margin


def test_zero_value_sits_at_bottom_margin():
    pts = sparkline_points([0.0, 10.0], 90.0, 24.0)
    margin = 2.0
    usable_h = 24.0 - 2 * margin
    assert pts[0][1] == margin + usable_h


def test_all_zero_values_are_flat_at_bottom():
    pts = sparkline_points([0.0, 0.0, 0.0], 90.0, 24.0)
    margin = 2.0
    usable_h = 24.0 - 2 * margin
    expected_y = margin + usable_h
    assert all(y == expected_y for _x, y in pts)


def test_constant_nonzero_values_are_flat_at_top():
    pts = sparkline_points([7.0, 7.0, 7.0], 90.0, 24.0)
    margin = 2.0
    assert all(y == margin for _x, y in pts)


def test_x_coordinates_evenly_spaced():
    pts = sparkline_points([1.0, 2.0, 3.0, 4.0], 90.0, 24.0)
    xs = [x for x, _y in pts]
    assert xs == [0.0, 30.0, 60.0, 90.0]
