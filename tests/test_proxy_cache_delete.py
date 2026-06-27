import tempfile
from pathlib import Path

from src.proxy.proxy_cache import delete_proxy_cache


def test_delete_existing_cache(tmp_path):
    cache_file = tmp_path / "proxy_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    result = delete_proxy_cache(path=cache_file)
    assert result is True
    assert not cache_file.exists()


def test_delete_nonexistent_cache(tmp_path):
    missing = tmp_path / "proxy_cache_nonexistent.json"
    assert not missing.exists()
    result = delete_proxy_cache(path=missing)
    assert result is False
