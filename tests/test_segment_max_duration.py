# Test puri per il budget temporale configurabile per pezzo
# (segment_max_duration_s), mirror di chunk_size/connections_per_file:
# nessuna rete, nessuna GUI.
from src.core.config import PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S
from src.downloader.parallel_client import ParallelMegaDownloader


def test_segment_max_duration_s_uses_given_value():
    dl = ParallelMegaDownloader(proxy_pool=None, n_connections=1, segment_max_duration_s=42)
    assert dl.segment_max_duration_s == 42


def test_segment_max_duration_s_defaults_to_config_when_none():
    dl = ParallelMegaDownloader(proxy_pool=None, n_connections=1)
    assert dl.segment_max_duration_s == PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S
