# Test puri per segment_widths(): nessuna rete, nessun Qt.
from src.gui.segment_bar import segment_widths


def test_total_zero_returns_all_zero_widths():
    assert segment_widths([0, 0, 0], 100.0) == [0.0, 0.0, 0.0]


def test_widths_sum_to_total_width():
    widths = segment_widths([3, 1, 0, 2], 123.0)
    assert sum(widths) == 123.0


def test_widths_proportional_to_values():
    widths = segment_widths([1, 1, 2], 80.0)
    # I primi due segmenti (stesso valore) devono avere larghezza uguale;
    # il terzo, doppio, larghezza doppia (a meno del resto di arrotondamento
    # assegnato al segmento piu' grande).
    assert widths[0] == widths[1]
    assert widths[2] >= widths[0] * 2 - 1e-9


def test_zero_value_segment_has_zero_width():
    widths = segment_widths([5, 0, 5], 100.0)
    assert widths[1] == 0.0
    assert widths[0] == 50.0
    assert widths[2] == 50.0


def test_single_nonzero_segment_takes_full_width():
    widths = segment_widths([0, 7, 0], 64.0)
    assert widths == [0.0, 64.0, 0.0]
