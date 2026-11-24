"""Regression cases from the audit. All paths and links are synthetic."""
from pathlib import Path

from src.core import maintenance, output_store
from src.core.mega_links import build_folder_job_url, parse_folder_job_url
from src.downloader.mega_folder import reserve_folder_links
from src.downloader.parallel_client import _save_progress


def folder(share, node, name="report.txt"):
    return build_folder_job_url(share, node, "example-key", ("Archive", name), 16)


def path_of(url):
    return Path(*parse_folder_job_url(url).rel_path)


def test_separate_additions_keep_the_first_path_and_survive_restart(tmp_path):
    first, second = folder("SHARE1", "NODE1"), folder("SHARE2", "NODE2")
    a, = reserve_folder_links([first], tmp_path)
    b, = reserve_folder_links([second], tmp_path)
    assert path_of(a) == Path("Archive/report.txt")
    assert path_of(b) == Path("Archive (2)/report.txt")
    assert reserve_folder_links([b, a, first], tmp_path) == [b, a, a]


def test_shared_working_names_and_personal_files_are_reserved(tmp_path):
    archive = tmp_path / "Archive"
    archive.mkdir()
    (archive / "report.txt").write_text("personal")
    first, = reserve_folder_links([folder("SHARE1", "NODE1")], tmp_path)
    assert path_of(first).name == "report (2).txt"
    second, = reserve_folder_links([folder("SHARE1", "NODE2", "report (2).txt.part")], tmp_path)
    assert path_of(second).name != "report (2).txt.part"
    assert (archive / "report.txt").read_text() == "personal"


def test_older_matching_checkpoint_keeps_its_relative_path(tmp_path):
    archive = tmp_path / "Archive"
    archive.mkdir()
    partial = archive / "report.txt.part"
    partial.write_bytes(bytes(16))
    _save_progress(partial, "NODE1", 16, {(0, 15)}, 16)
    job, = reserve_folder_links([folder("SHARE1", "NODE1")], tmp_path)
    assert path_of(job) == Path("Archive/report.txt")
    assert partial.is_file()


def test_older_checkpoint_with_unrelated_sibling_gets_a_fresh_name(tmp_path):
    archive = tmp_path / "Archive"
    archive.mkdir()
    partial = archive / "report.txt.part"
    partial.write_bytes(bytes(16))
    _save_progress(partial, "NODE1", 16, {(0, 15)}, 16)
    personal = archive / "report.txt.part.progress.json.tmp"
    personal.write_text("personal")
    job, = reserve_folder_links([folder("SHARE1", "NODE1")], tmp_path)
    assert path_of(job) == Path("Archive/report (2).txt")
    assert personal.read_text() == "personal"


def test_assigned_path_with_a_replaced_partial_gets_a_fresh_name(tmp_path):
    source = folder("SHARE1", "NODE1")
    job, = reserve_folder_links([source], tmp_path)
    target = tmp_path / path_of(job)
    target.parent.mkdir()
    partial = target.with_name(target.name + ".part")
    partial.write_text("download")
    output_store.record(tmp_path, "job", partial, True)
    assert reserve_folder_links([source], tmp_path) == [job]
    partial.write_text("personal document")
    replacement, = reserve_folder_links([source], tmp_path)
    assert path_of(replacement) == Path("Archive/report (2).txt")
    assert partial.read_text() == "personal document"


def test_cleanup_only_removes_previewed_unchanged_files(tmp_path):
    a, b, c = [tmp_path / f"{n}.bin" for n in "abc"]
    a.write_text("owned")
    b.write_text("old")
    c.write_text("unrelated")
    for path in (a, b):
        output_store.record(tmp_path, "owner", path, False)
    preview = maintenance.survey(maintenance.ITEM_DOWNLOADS, output_root=tmp_path)
    assert set(preview.paths) == {a, b}
    replacement = tmp_path / "replacement"
    replacement.write_text("personal")
    replacement.replace(b)
    later = tmp_path / "later.bin"
    later.write_text("new")
    output_store.record(tmp_path, "owner", later, False)
    result = maintenance.clear(maintenance.ITEM_DOWNLOADS, output_root=tmp_path,
                               selected_downloads=preview.receipts)
    assert result.ok and result.removed == 1
    assert not a.exists()
    assert [p.read_text() for p in (b, c, later)] == ["personal", "unrelated", "new"]


def test_existing_assignment_leaves_a_replaced_file_alone(tmp_path):
    source = folder("SHARE1", "NODE1")
    job, = reserve_folder_links([source], tmp_path)
    target = tmp_path / path_of(job)
    target.parent.mkdir()
    target.write_bytes(b"owned")
    output_store.record(tmp_path, "owner", target, False)
    assert reserve_folder_links([source], tmp_path) == [job]
    target.write_text("personal replacement")
    new, = reserve_folder_links([source], tmp_path)
    assert path_of(new) != path_of(job)
    assert target.read_text() == "personal replacement"


def test_discard_only_owns_its_partial_files(tmp_path):
    task = output_store.JobOutputs(tmp_path, "file1", 0)
    other = output_store.JobOutputs(tmp_path, "file2", 1)
    a, b, c = [tmp_path / n for n in ("finished", "part", "other.part")]
    for path in (a, b, c):
        path.write_bytes(b"x")
    task.written(a)
    task.written(b, partial=True)
    other.written(c, partial=True)
    previous = tmp_path / "previous.part"
    previous.write_bytes(b"old partial")
    output_store.JobOutputs(tmp_path, "file1", 0).written(previous, partial=True)
    task.discard_partial()
    assert a.exists() and not b.exists() and c.exists() and previous.exists()


def test_directory_replaced_after_preview_preserves_external_files(tmp_path):
    import pytest
    root = tmp_path / "downloads"
    inside = root / "collection"
    inside.mkdir(parents=True)
    target = inside / "a.bin"
    target.write_bytes(b"owned")
    output_store.record(root, "job", target, False)
    selected = maintenance.survey(maintenance.ITEM_DOWNLOADS, output_root=root)
    moved = tmp_path / "moved"
    inside.rename(moved)
    try:
        inside.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("directory links unavailable on this volume")
    result = maintenance.clear(maintenance.ITEM_DOWNLOADS, output_root=root,
                               selected_downloads=selected.receipts)
    assert result.removed == 0 and (moved / "a.bin").read_bytes() == b"owned"
