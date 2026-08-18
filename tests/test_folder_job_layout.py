# Layout su disco dei job nati dall'espansione di una cartella Mega.
#
# Copre le due cose che il ramo "albero" cambia rispetto al job normale:
#   1. il path di destinazione (albero, senza `_<file_id>` e senza `ciclo_N`);
#   2. il check di resume, che deve guardare il NOME ESATTO del file e non
#      "un file finale qualsiasi" — la cartella e' condivisa con gli altri
#      file dello stesso albero.
import pytest
from PyQt6.QtWidgets import QApplication

from src.core.file_naming import folder_job_output_dir
from src.core.mega_links import build_folder_job_url
from src.core.state import SessionState
from src.downloader.worker import DownloadWorker, job_output_dir
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

def test_worker_uses_the_tree_path_not_the_hash_path(tmp_path):
    w = _worker(("Cartella", "sub", "f.bin"), tmp_path)
    base = folder_job_output_dir(w._folder_job.rel_path, tmp_path)
    assert base == tmp_path / "Cartella" / "sub"
    # ...e NON la cartella hash-based dei job normali.
    assert base != job_output_dir(w.mega_url, 0, tmp_path)


def test_folder_job_has_no_cycle_subdirectory(tmp_path):
    w = _worker(("Cartella", "f.bin"), tmp_path)
    w._current_base_dir = folder_job_output_dir(w._folder_job.rel_path, tmp_path)
    assert w._cycle_dir(1) == tmp_path / "Cartella"
    assert w._cycle_dir(2) == tmp_path / "Cartella"   # nessun ciclo_N


def test_normal_job_keeps_the_cycle_subdirectory(tmp_path):
    w = DownloadWorker(
        3, "https://mega.nz/file/ABC#KEY", ProxyPool(), SessionState(),
        output_root=tmp_path,
    )
    assert w._folder_job is None
    w._current_base_dir = job_output_dir(w.mega_url, 3, tmp_path)
    assert w._cycle_dir(1).name == "ciclo_1"


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
    w._current_base_dir = base
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
    w, _ = _prepare(
        tmp_path, ("Cartella", "mio.bin"), existing_names=("altro.bin", "mio.bin"),
    )
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


def test_our_file_with_the_expected_size_counts_as_complete(tmp_path):
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=5000)
    (base / "IMG_1.jpg").write_bytes(b"z" * 5000)
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


def test_job_without_size_keeps_the_historical_behaviour(tmp_path):
    # Forma vecchia del job (nessuna dimensione): vale la presenza del file.
    w, base = _prepare(tmp_path, ("Foto", "IMG_1.jpg"), size=None)
    (base / "IMG_1.jpg").write_bytes(b"z" * 7)
    assert w._run_cycle_until_success(1) is True
