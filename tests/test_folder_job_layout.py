"""Destinazioni dei file singoli e delle cartelle condivise."""
import pytest
from PyQt6.QtWidgets import QApplication

from src.core.file_naming import folder_job_output_dir
from src.core.mega_links import build_folder_job_url
from src.core.state import SessionState
from src.downloader.worker import DownloadWorker
from src.proxy.pool import ProxyPool


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    # DownloadWorker e' un QThread: serve una QApplication nel processo, ma qui
    # non si avvia nessun thread (si chiamano solo metodi sincroni).
    QApplication.instance() or QApplication([])


def _worker(rel_path, output_root, file_id=0, size=None):
    url = build_folder_job_url("FID", "NODE1", "S2VZ", rel_path, size)
    w = DownloadWorker(file_id, url, ProxyPool(), SessionState(), output_root=output_root)
    w.run = None  # non deve mai partire davvero
    return w


# ---- folder_job_output_dir -------------------------------------------------

def test_output_dir_is_the_tree_without_the_file_name(tmp_path):
    got = folder_job_output_dir(("Cartella", "sub", "f.bin"), tmp_path)
    assert got == tmp_path / "Cartella" / "sub"


def test_output_dir_of_a_root_level_file(tmp_path):
    assert folder_job_output_dir(("Cartella", "f.bin"), tmp_path) == tmp_path / "Cartella"


def test_output_dir_resanitizes_segments_at_the_filesystem_boundary(tmp_path):
    # Difesa in profondita': un job puo' arrivare da un file di sessione
    # scritto da una versione precedente o modificato a mano.
    got = folder_job_output_dir(("..", "a:b", "f.bin"), tmp_path)
    assert got == tmp_path / "download" / "a b"
    assert tmp_path in got.parents or got.parent == tmp_path


def test_output_dir_rejects_empty_rel_path():
    with pytest.raises(ValueError):
        folder_job_output_dir(())


# ---- destinazione scelta dal worker ----------------------------------------

@pytest.mark.parametrize("rel_path", [("Cartella", "sub", "f.bin"), ("Cartella", "f.bin")])
def test_worker_uses_original_tree(tmp_path, rel_path):
    w = _worker(rel_path, tmp_path)
    assert w._output_dir == tmp_path.joinpath(*rel_path[:-1])
    assert list(tmp_path.iterdir()) == []


def test_single_file_goes_in_the_selected_directory(tmp_path):
    w = DownloadWorker(3, "https://mega.nz/file/ABC#KEY", ProxyPool(), SessionState(),
                       output_root=tmp_path)
    assert w._output_dir == tmp_path
    assert list(tmp_path.iterdir()) == []


def test_file_name_is_sanitized_for_the_filesystem(tmp_path):
    w = _worker(("Cartella", "CON.txt"), tmp_path)
    assert w._folder_file_name == "_CON.txt"


# ---- resume: nome esatto, non "un file qualsiasi" --------------------------

def _prepare(tmp_path, rel_path, existing_names=(), size=None):
    w = _worker(rel_path, tmp_path, size=size)
    base = folder_job_output_dir(rel_path, tmp_path)
    base.mkdir(parents=True, exist_ok=True)
    for name in existing_names:
        (base / name).write_bytes(b"x")
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    return w, base


def test_resume_does_not_fire_because_a_sibling_file_is_complete(tmp_path):
    # Regressione centrale: con la scansione "un file finale qualsiasi" questo
    # job risulterebbe gia' completato per colpa del file di un ALTRO job.
    w, _ = _prepare(tmp_path, ("Cartella", "mio.bin"), existing_names=("altro.bin",))
    emitted = []
    w.cycle_completed.connect(lambda fid, c: emitted.append((fid, c)))
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True      # esce subito dopo il primo giro
    assert w._run_cycle_until_success(1) is False
    assert emitted == []


def test_resume_fires_when_our_exact_file_is_there(tmp_path):
    w, base = _prepare(
        tmp_path, ("Cartella", "mio.bin"), existing_names=("altro.bin", "mio.bin"),
    )
    w.files.finished(base / "mio.bin")
    emitted = []
    w.cycle_completed.connect(lambda fid, c: emitted.append((fid, c)))
    assert w._run_cycle_until_success(1) is True
    assert emitted == [(0, 1)]


def test_resume_ignores_our_part_file(tmp_path):
    # Un `.part` e' un download interrotto, non un file completo.
    w, _ = _prepare(tmp_path, ("Cartella", "mio.bin"), existing_names=("mio.bin.part",))
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    assert w._run_cycle_until_success(1) is False


def test_resume_ignores_a_final_file_that_still_has_a_sidecar(tmp_path):
    w, base = _prepare(tmp_path, ("Cartella", "mio.bin"), existing_names=("mio.bin",))
    (base / "mio.bin.progress.json").write_text("{}", encoding="utf-8")
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    assert w._run_cycle_until_success(1) is False


def test_sibling_temp_files_are_not_deleted_from_the_shared_folder(tmp_path):
    # La pulizia dei `megapy_*` e' pensata per una cartella "di proprieta'" del
    # job: in un albero condiviso cancellerebbe i temporanei di altri file.
    w, base = _prepare(
        tmp_path, ("Cartella", "mio.bin"), existing_names=("megapy_altro.tmp",),
    )
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    w._run_cycle_until_success(1)
    assert (base / "megapy_altro.tmp").exists()


# ---- il file su disco deve essere DAVVERO il nostro ------------------------

def test_a_same_named_file_of_another_share_does_not_count_as_complete(tmp_path):
    # Nell'albero il path e' stabile fra le sessioni: due cartelle Mega diverse
    # con lo stesso nome di radice e lo stesso nome file puntano allo stesso
    # posto. Senza il controllo sulla dimensione il download risulterebbe
    # "completato" restituendo all'utente il file di un'ALTRA cartella.
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=5000)
    (base / "IMG_1.jpg").write_bytes(b"z" * 123)   # file di un'altra origine
    emitted = []
    w.cycle_completed.connect(lambda fid, c: emitted.append(c))
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    assert w._run_cycle_until_success(1) is False
    assert emitted == []


def test_our_file_with_the_expected_size_counts_as_complete(tmp_path, monkeypatch):
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=5000)
    target = base / "IMG_1.jpg"
    target.write_bytes(b"z" * 5000)
    monkeypatch.setattr("src.downloader.worker.completion_records",
                        lambda: [dict(url=w.mega_url, path=str(target), disk_signature=list(w.files.signature(target)))])
    emitted = []
    w.cycle_completed.connect(lambda fid, c: emitted.append(c))
    assert w._run_cycle_until_success(1) is True
    assert emitted == [1]


def test_truncated_file_is_redownloaded(tmp_path):
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=5000)
    (base / "IMG_1.jpg").write_bytes(b"z" * 4999)
    w._get_proxy_blocking = lambda: None
    w._sleep_interruptible = lambda _s: True
    assert w._run_cycle_until_success(1) is False


def test_job_without_size_recognizes_its_own_file(tmp_path):
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=None)
    (base / "IMG_1.jpg").write_bytes(b"z" * 7)
    w.files.finished(base / "IMG_1.jpg")
    assert w._run_cycle_until_success(1) is True


def test_same_size_and_name_without_provenance_are_insufficient(tmp_path, monkeypatch):
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=7)
    target = base / "IMG_1.jpg"
    target.write_bytes(b"another")
    monkeypatch.setattr("src.downloader.worker.completion_records",
                        lambda: [dict(url="another folder", file_size=7, path=str(target))])
    assert not w._run_cycle_until_success(1)
    assert target.read_bytes() == b"another"
