from src.core.file_naming import sanitize_folder_name


def test_removes_colon():
    result = sanitize_folder_name("Mio Film: il ritorno (2026).mp4")
    assert result == "Mio Film il ritorno (2026).mp4"


def test_removes_path_separators_and_wildcards():
    result = sanitize_folder_name("ciao//mondo\\test*?")
    assert result == "ciao mondo test"


def test_strips_trailing_dots():
    result = sanitize_folder_name("...nome con punti finali...")
    assert result == "...nome con punti finali"


def test_empty_string_returns_download():
    result = sanitize_folder_name("")
    assert result == "download"


def test_all_invalid_chars_returns_download():
    result = sanitize_folder_name('<>:"')
    assert result == "download"


def test_truncates_to_max_len():
    long_name = "a" * 200
    result = sanitize_folder_name(long_name, max_len=120)
    assert len(result) == 120


def test_collapses_multiple_spaces():
    result = sanitize_folder_name("ciao   mondo")
    assert result == "ciao mondo"
