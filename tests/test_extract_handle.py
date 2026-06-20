# Test puri per extract_handle: nessuna rete, solo parsing testuale.
from src.core.download_history import extract_handle


def test_new_format_file_link():
    url = "https://mega.nz/file/ABC123#KEY456xyz"
    assert extract_handle(url) == "ABC123"


def test_legacy_format_link():
    url = "https://mega.nz/#!ABC123!KEY456xyz"
    assert extract_handle(url) == "ABC123"


def test_new_format_without_key():
    url = "https://mega.nz/file/ABC123"
    assert extract_handle(url) == "ABC123"


def test_folder_link_returns_none():
    url = "https://mega.nz/folder/XYZ789#KEY"
    assert extract_handle(url) is None


def test_unrecognized_format_returns_none():
    url = "https://example.com/not-a-mega-link"
    assert extract_handle(url) is None


def test_empty_string_returns_none():
    assert extract_handle("") is None
