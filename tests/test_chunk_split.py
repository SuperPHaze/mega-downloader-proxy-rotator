# Test puri per la suddivisione in chunk a dimensione fissa.
# Nessuna rete, nessuna GUI: _split_chunks e' logica pura (offset arithmetic).
from src.core.config import PARALLEL_MIN_SEGMENT_BYTES
from src.downloader.parallel_client import _split_chunks

MB = 1024 * 1024


def _assert_no_gaps_no_overlaps(chunks, file_size):
    assert chunks[0][0] == 0
    assert chunks[-1][1] == file_size - 1
    for (start, end) in chunks:
        assert start <= end
    for (_, end), (next_start, _) in zip(chunks, chunks[1:]):
        assert next_start == end + 1
    total_covered = sum(end - start + 1 for start, end in chunks)
    assert total_covered == file_size


def test_exact_multiple_of_chunk_size():
    file_size = 4 * MB
    chunk_size = 1 * MB
    chunks = _split_chunks(file_size, chunk_size)
    assert len(chunks) == 4
    _assert_no_gaps_no_overlaps(chunks, file_size)
    assert all(end - start + 1 == chunk_size for start, end in chunks)


def test_file_slightly_larger_than_one_chunk():
    chunk_size = 1 * MB
    file_size = chunk_size + 10
    chunks = _split_chunks(file_size, chunk_size)
    assert len(chunks) == 2
    _assert_no_gaps_no_overlaps(chunks, file_size)
    assert chunks[1][1] - chunks[1][0] + 1 == 10


def test_file_smaller_than_min_segment_returns_single_chunk():
    file_size = PARALLEL_MIN_SEGMENT_BYTES // 2
    chunks = _split_chunks(file_size, 1 * MB)
    assert chunks == [(0, file_size - 1)]


def test_file_equal_to_min_segment_returns_single_chunk():
    # Anche se chunk_size e' piu' piccolo del file: la soglia e' su file_size,
    # non sul rapporto file_size/chunk_size.
    file_size = PARALLEL_MIN_SEGMENT_BYTES
    chunks = _split_chunks(file_size, 16)
    assert chunks == [(0, file_size - 1)]


def test_large_file_with_small_chunk_many_pieces():
    file_size = PARALLEL_MIN_SEGMENT_BYTES * 2 + 10
    chunk_size = PARALLEL_MIN_SEGMENT_BYTES
    chunks = _split_chunks(file_size, chunk_size)
    assert len(chunks) == 3
    _assert_no_gaps_no_overlaps(chunks, file_size)


def test_boundaries_aligned_to_16_bytes_except_last():
    file_size = PARALLEL_MIN_SEGMENT_BYTES * 3 + 7  # non multiplo di 16
    chunk_size = 1 * MB
    chunks = _split_chunks(file_size, chunk_size)
    _assert_no_gaps_no_overlaps(chunks, file_size)
    for start, _ in chunks:
        assert start % 16 == 0
    # Tutti i confini (end+1) sono multipli di 16 tranne l'ultimo, che e'
    # vincolato solo da file_size (puo' non essere multiplo di 16).
    for _, end in chunks[:-1]:
        assert (end + 1) % 16 == 0


def test_chunk_size_not_multiple_of_16_gets_aligned_down():
    file_size = PARALLEL_MIN_SEGMENT_BYTES * 3
    chunk_size = 1000  # non multiplo di 16 -> allineato a 992
    chunks = _split_chunks(file_size, chunk_size)
    _assert_no_gaps_no_overlaps(chunks, file_size)
    assert chunks[0][1] - chunks[0][0] + 1 == 992
