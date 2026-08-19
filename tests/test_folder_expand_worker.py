# Test sul worker di espansione: mescolanza cartelle/file singoli, cartella
# vuota, errore su una cartella sola, cap superato. Nessuna rete: la funzione
# di espansione e' sostituita da una fake.
# NOTA i18n: i test che asseriscono le PAROLE del report ("vuota",
# "ATTENZIONE", "annullata", "duplicati") usano la fixture `italian_ui`.
# Da quando il report passa dal dizionario, senza quella fixture l'esito
# dipenderebbe dal locale della macchina che lancia la suite.
import pytest
from PyQt6.QtWidgets import QApplication

from src.downloader.mega_api import MegaApiError
from src.downloader.mega_folder import FolderExpansion, FolderFile
from src.gui import folder_expand_worker as few
from src.gui.folder_expand_worker import FolderExpandWorker

FOLDER_A = "https://mega.nz/folder/AAAAAAAA#chiaveCartellaA"
FOLDER_B = "https://mega.nz/folder/BBBBBBBB#chiaveCartellaB"
FILE_1 = "https://mega.nz/file/FILE0001#chiaveFile1"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    QApplication.instance() or QApplication([])


def _expansion(folder_id, name, n_files, total=None, n_folders=0):
    files = tuple(
        FolderFile(f"N{folder_id}{i}", "S2V5", 100 + i, (name, f"f{i}.bin"))
        for i in range(n_files)
    )
    return FolderExpansion(
        folder_id=folder_id, folder_name=name, files=files,
        total_files=total if total is not None else n_files,
        n_folders=n_folders, n_skipped=0,
    )


def _run(worker):
    """Esegue run() in modo sincrono e raccoglie i segnali emessi."""
    out = {"ok": None, "failed": None}
    worker.finished_ok.connect(lambda a, b, c: out.update(ok=(a, b, c)))
    worker.failed.connect(lambda m: out.update(failed=m))
    worker.run()
    return out


def test_mixed_input_expands_folders_and_keeps_single_files(monkeypatch, italian_ui):
    monkeypatch.setattr(
        few, "expand_folder_link",
        lambda url, **kw: _expansion("A", "CartA", 3),
    )
    out = _run(FolderExpandWorker([FILE_1, FOLDER_A]))
    links, report, truncated = out["ok"]
    assert links[0] == FILE_1          # ordine di input preservato
    assert len(links) == 4             # 1 file + 3 dalla cartella
    assert truncated == 0
    assert any("CartA" in line and "3 file" in line for line in report)


def test_two_folders_are_both_expanded(monkeypatch):
    monkeypatch.setattr(
        few, "expand_folder_link",
        lambda url, **kw: _expansion(
            "A" if "AAAA" in url else "B", "CartA" if "AAAA" in url else "CartB", 2,
        ),
    )
    links, _report, _t = _run(FolderExpandWorker([FOLDER_A, FOLDER_B]))["ok"]
    assert len(links) == 4
    assert len(set(links)) == 4


def test_empty_folder_is_reported_and_produces_no_jobs(monkeypatch, italian_ui):
    monkeypatch.setattr(
        few, "expand_folder_link", lambda url, **kw: _expansion("A", "Vuota", 0),
    )
    out = _run(FolderExpandWorker([FILE_1, FOLDER_A]))
    links, report, _t = out["ok"]
    assert links == [FILE_1]
    assert any("vuota" in line for line in report)


def test_only_an_empty_folder_fails_with_a_message(monkeypatch, italian_ui):
    monkeypatch.setattr(
        few, "expand_folder_link", lambda url, **kw: _expansion("A", "Vuota", 0),
    )
    out = _run(FolderExpandWorker([FOLDER_A]))
    assert out["ok"] is None
    assert "vuota" in out["failed"]


def test_one_failing_folder_does_not_kill_the_others(monkeypatch):
    def fake(url, **kw):
        if "AAAA" in url:
            raise MegaApiError("cartella non accessibile o scaduta")
        return _expansion("B", "CartB", 2)

    monkeypatch.setattr(few, "expand_folder_link", fake)
    links, report, _t = _run(FolderExpandWorker([FOLDER_A, FOLDER_B]))["ok"]
    assert len(links) == 2
    assert any("non accessibile" in line for line in report)


def test_unexpected_exception_is_contained(monkeypatch):
    def boom(url, **kw):
        raise RuntimeError("qualcosa di imprevisto")

    monkeypatch.setattr(few, "expand_folder_link", boom)
    out = _run(FolderExpandWorker([FOLDER_A]))
    assert out["ok"] is None
    assert "imprevisto" in out["failed"]


def test_truncation_is_surfaced_never_silent(monkeypatch, italian_ui):
    monkeypatch.setattr(
        few, "expand_folder_link",
        lambda url, **kw: _expansion("A", "Grande", 4, total=10),
    )
    links, report, truncated = _run(FolderExpandWorker([FOLDER_A], max_files=4))["ok"]
    assert len(links) == 4
    assert truncated == 6
    assert any("ATTENZIONE" in line for line in report)


def test_cancellation_stops_the_expansion(monkeypatch, italian_ui):
    monkeypatch.setattr(
        few, "expand_folder_link", lambda url, **kw: _expansion("A", "CartA", 1),
    )
    worker = FolderExpandWorker([FOLDER_A, FOLDER_B])
    worker.request_cancel()
    out = _run(worker)
    assert out["ok"] is None
    assert "annullata" in out["failed"].lower()


def test_input_without_folders_passes_through_untouched(monkeypatch):
    def never(url, **kw):
        raise AssertionError("non deve essere chiamata senza link cartella")

    monkeypatch.setattr(few, "expand_folder_link", never)
    links, report, _t = _run(FolderExpandWorker([FILE_1, FILE_1]))["ok"]
    assert links == [FILE_1, FILE_1]
    assert report == []


def test_worker_removes_exact_duplicates_across_two_pastes(monkeypatch, italian_ui):
    # La stessa cartella incollata due volte: stessi nodi, stessi path.
    monkeypatch.setattr(
        few, "expand_folder_link", lambda url, **kw: _expansion("A", "CartA", 2),
    )
    links, report, _t = _run(FolderExpandWorker([FOLDER_A, FOLDER_A]))["ok"]
    assert len(links) == 2                      # non 4
    assert any("duplicati" in line for line in report)


def test_worker_decollides_paths_between_different_folders(monkeypatch):
    from src.core.mega_links import parse_folder_job_url

    def fake(url, **kw):
        fid = "A" if "AAAA" in url else "B"
        # Due cartelle DIVERSE che si chiamano allo stesso modo e contengono
        # lo stesso nome file: gli URL differiscono, i path no.
        return FolderExpansion(
            folder_id=fid, folder_name="Backup",
            files=(FolderFile(f"N{fid}", "S2V5", 10, ("Backup", "foto.jpg")),),
            total_files=1, n_folders=0, n_skipped=0,
        )

    monkeypatch.setattr(few, "expand_folder_link", fake)
    links, _report, _t = _run(FolderExpandWorker([FOLDER_A, FOLDER_B]))["ok"]
    paths = ["/".join(parse_folder_job_url(u).rel_path) for u in links]
    assert len(set(paths)) == 2, paths
