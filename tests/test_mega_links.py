# Test puri sul riconoscimento delle forme di URL Mega: nessuna rete, nessuna
# crypto. Copre file singolo, cartella, cartella con nodo selezionato, formati
# legacy e la forma INTERNA dei job generati espandendo una cartella.
import pytest

from src.core.mega_links import (
    SUB_AUTO,
    SUB_FILE,
    SUB_FOLDER,
    build_folder_job_url,
    extract_handle,
    is_folder_link,
    parse_file_link,
    parse_folder_job_url,
    parse_folder_link,
)

FOLDER_URL = "https://mega.nz/folder/lDsUgAAL#uRGkMHzu6xzzseMsIljrBg"


# ---- link a file singolo ---------------------------------------------------

def test_file_link_new_format():
    link = parse_file_link("https://mega.nz/file/ABC123#KEY456xyz")
    assert link is not None
    assert (link.handle, link.key_b64) == ("ABC123", "KEY456xyz")


def test_file_link_legacy_format():
    link = parse_file_link("https://mega.nz/#!ABC123!KEY456xyz")
    assert link is not None
    assert (link.handle, link.key_b64) == ("ABC123", "KEY456xyz")


def test_file_link_rejects_folder_url():
    # Un link cartella NON deve essere scambiato per un file risolvibile.
    assert parse_file_link(FOLDER_URL) is None


def test_file_link_rejects_combined_folder_file_url():
    url = "https://mega.nz/folder/AAAA#KEYKEY/file/NODE1"
    assert parse_file_link(url) is None


def test_file_link_rejects_garbage():
    assert parse_file_link("https://example.com/nope") is None
    assert parse_file_link("") is None


# ---- link a cartella -------------------------------------------------------

def test_folder_link_plain():
    link = parse_folder_link(FOLDER_URL)
    assert link is not None
    assert link.folder_id == "lDsUgAAL"
    assert link.key_b64 == "uRGkMHzu6xzzseMsIljrBg"
    assert link.sub_kind is None and link.sub_handle is None


def test_folder_link_with_selected_file():
    link = parse_folder_link("https://mega.nz/folder/AAAA#KEYKEY/file/NODE1")
    assert link is not None
    assert (link.folder_id, link.sub_kind, link.sub_handle) == ("AAAA", SUB_FILE, "NODE1")


def test_folder_link_with_selected_subfolder():
    link = parse_folder_link("https://mega.nz/folder/AAAA#KEYKEY/folder/SUB1")
    assert link is not None
    assert (link.folder_id, link.sub_kind, link.sub_handle) == ("AAAA", SUB_FOLDER, "SUB1")


def test_folder_link_legacy():
    link = parse_folder_link("https://mega.nz/#F!lDsUgAAL!uRGkMHzu6xzzseMsIljrBg")
    assert link is not None
    assert link.folder_id == "lDsUgAAL"
    assert link.key_b64 == "uRGkMHzu6xzzseMsIljrBg"
    assert link.sub_kind is None


def test_folder_link_legacy_with_sub_is_auto():
    # Il formato legacy non dice se il terzo campo e' un file o una cartella:
    # il tipo va risolto dal nodo, quindi il parser marca SUB_AUTO.
    link = parse_folder_link("https://mega.nz/#F!AAAA!KEYKEY!NODE1")
    assert link is not None
    assert (link.sub_kind, link.sub_handle) == (SUB_AUTO, "NODE1")


def test_legacy_folder_is_not_read_as_legacy_file():
    # "#F!" non deve essere catturato dalla regex del file legacy "#!".
    assert parse_file_link("https://mega.nz/#F!AAAA!KEYKEY") is None


def test_is_folder_link():
    assert is_folder_link(FOLDER_URL)
    assert not is_folder_link("https://mega.nz/file/ABC#KEY")
    assert not is_folder_link("")


# ---- forma interna dei job -------------------------------------------------

REL = ("Mia Cartella", "sotto", "file.bin")
JOB_URL = build_folder_job_url("FID1", "NODE1", "K8WORDS", REL)


def test_job_url_round_trip():
    job = parse_folder_job_url(JOB_URL)
    assert job is not None
    assert job.folder_id == "FID1"
    assert job.node_handle == "NODE1"
    assert job.node_key_b64 == "K8WORDS"
    assert job.rel_path == REL
    assert job.file_name == "file.bin"


def test_job_url_survives_prefix_check_of_the_gui():
    assert JOB_URL.startswith("https://mega.nz/")


def test_job_url_round_trip_with_unicode_and_spaces():
    rel = ("Cartella àèì", "sub dir", "file (1).tar.gz")
    job = parse_folder_job_url(build_folder_job_url("F", "N", "K", rel))
    assert job is not None and job.rel_path == rel


def test_job_url_is_not_mistaken_for_a_plain_file_link():
    # Regressione: /file/<h>#<k> dentro la forma interna non deve far scattare
    # il ramo "file pubblico singolo" (che risolverebbe senza n=<folder_id>).
    assert parse_file_link(JOB_URL) is None
    assert parse_folder_link(JOB_URL) is None
    assert not is_folder_link(JOB_URL)


def test_build_job_url_rejects_empty_parts():
    with pytest.raises(ValueError):
        build_folder_job_url("", "N", "K", REL)
    with pytest.raises(ValueError):
        build_folder_job_url("F", "N", "K", ())


def test_parse_job_url_on_non_job_returns_none():
    assert parse_folder_job_url(FOLDER_URL) is None
    assert parse_folder_job_url("https://mega.nz/file/ABC#KEY") is None
    assert parse_folder_job_url("") is None


# ---- extract_handle --------------------------------------------------------

def test_extract_handle_job_url_returns_node_handle():
    # Il dedup dello storico resta per-FILE anche dentro le cartelle.
    assert extract_handle(JOB_URL) == "NODE1"


def test_extract_handle_combined_url_returns_node_handle():
    assert extract_handle("https://mega.nz/folder/AAAA#KEYKEY/file/NODE9") == "NODE9"


def test_extract_handle_subfolder_selection_returns_none():
    assert extract_handle("https://mega.nz/folder/AAAA#KEYKEY/folder/SUB9") is None


def test_extract_handle_plain_folder_returns_none():
    assert extract_handle(FOLDER_URL) is None


# ---- dimensione attesa nel job (proprieta' del file su disco) --------------

def test_job_url_carries_the_expected_size():
    url = build_folder_job_url("F", "N", "K", ("C", "f.bin"), 12345)
    job = parse_folder_job_url(url)
    assert job is not None and job.size == 12345
    assert job.rel_path == ("C", "f.bin")


def test_job_url_without_size_parses_with_size_none():
    job = parse_folder_job_url(build_folder_job_url("F", "N", "K", ("C", "f.bin")))
    assert job is not None and job.size is None


def test_zero_size_is_preserved_not_dropped():
    job = parse_folder_job_url(build_folder_job_url("F", "N", "K", ("C", "f.bin"), 0))
    assert job is not None and job.size == 0


def test_size_does_not_break_the_other_parsers():
    url = build_folder_job_url("F", "N", "K", ("C", "f.bin"), 99)
    assert parse_file_link(url) is None
    assert parse_folder_link(url) is None
    assert extract_handle(url) == "N"
