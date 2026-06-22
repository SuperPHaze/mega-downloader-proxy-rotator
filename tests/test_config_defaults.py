# Guardia anti-regressione sui default 1.9.0 (chunk 32 MB, 10 connessioni/file).
from src.core.config import PARALLEL_CHUNK_SIZE_MB, PARALLEL_CONNECTIONS_PER_FILE


def test_default_connections_per_file():
    assert PARALLEL_CONNECTIONS_PER_FILE == 10


def test_default_chunk_size_mb():
    assert PARALLEL_CHUNK_SIZE_MB == 32
