from src.core.file_naming import sanitize_file_name, sanitize_folder_name


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


# --- sanitize_file_name (nome file sicuro per Windows, preserva estensione) ---

def test_file_removes_reserved_chars_keeps_extension():
    assert sanitize_file_name('report: finale?.pdf') == "report finale.pdf"


def test_file_blocks_path_traversal():
    assert sanitize_file_name("../../etc/passwd") == "passwd"


def test_file_reserved_device_name_gets_prefixed():
    # "CON" è un device name riservato anche con estensione.
    assert sanitize_file_name("CON.txt") == "_CON.txt"
    assert sanitize_file_name("nul") == "_nul"


def test_file_empty_returns_fallback():
    assert sanitize_file_name('<>:"', fallback="mega_x") == "mega_x"


def test_file_truncation_preserves_extension():
    name = "a" * 300 + ".mp4"
    result = sanitize_file_name(name, max_len=50)
    assert len(result) == 50
    assert result.endswith(".mp4")


def test_file_normal_name_unchanged():
    assert sanitize_file_name("archivio.tar.gz") == "archivio.tar.gz"


# --- output_root configurabile (2.5) --------------------------------------

def test_final_output_dir_uses_custom_root(tmp_path):
    from src.core.file_naming import final_output_dir
    assert final_output_dir("Film.mp4", 3, tmp_path) == tmp_path / "Film.mp4_3"


def test_final_output_dir_defaults_when_root_none():
    from src.core.config import OUTPUT_DIR
    from src.core.file_naming import final_output_dir
    assert final_output_dir("Film.mp4", 3) == OUTPUT_DIR / "Film.mp4_3"


def test_job_output_dir_uses_custom_root(tmp_path):
    from src.downloader.worker import job_output_dir
    result = job_output_dir("https://mega.nz/file/abc#key", 5, tmp_path)
    assert result.parent == tmp_path
    assert result.name.endswith("_5")
