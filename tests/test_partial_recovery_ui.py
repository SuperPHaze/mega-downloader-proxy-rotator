import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox, QStyle, QStyleOptionButton

from src.core import partial_downloads as partials
from src.downloader.parallel_client import _save_progress
from src.gui import main_window, preferences
from src.gui.i18n import TR


URL = "https://mega.nz/file/Example1#test-key"
NEXT = "https://mega.nz/file/Example2#test-key"


def until(condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert condition()


@pytest.fixture
def window(qt_app, italian_ui, tmp_path, monkeypatch):
    root = tmp_path / "downloads"
    directory = root / "Film_6" / "ciclo_1"
    directory.mkdir(parents=True)
    block = 1024 * 1024
    size = 2 * block
    first = directory / "Film A.mkv.part"
    first.write_bytes(bytes(size))
    _save_progress(first, "Example1", size, {(0, block-1)}, block)
    (directory / "Film B.mkv.part").write_bytes(bytes(128))
    monkeypatch.setattr(partials, "LOGS_DIR", tmp_path / "log")
    monkeypatch.setattr(partials, "completion_records", lambda: [
        {"file_name": "Film A.mkv", "file_size": size, "handle": "Example1", "url": URL},
        {"file_name": "Film B.mkv", "file_size": 128, "handle": "Example2", "url": NEXT},
    ])
    monkeypatch.setattr(partials, "read_failed_links", lambda: [])
    monkeypatch.setattr(main_window.session_store, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(main_window, "OUTPUT_DIR", root)
    monkeypatch.setattr(main_window, "LOGS_DIR", tmp_path)
    for method in ("_run_speedtest", "_maybe_check_updates_on_startup"):
        monkeypatch.setattr(main_window.MainWindow, method, lambda self: None)
    # L'orchestratore e la coda sono reali, il setup di rete resta fermo.
    monkeypatch.setattr("src.downloader.orchestrator._SetupThread.start", lambda self: None)
    monkeypatch.setattr("src.downloader.orchestrator.telemetry.start_session", lambda *a, **k: None)
    win = main_window.MainWindow()
    win.show()
    until(lambda: len(win._partials) == 2)
    yield win
    win.close()
    win.deleteLater()


def open_list(win, button):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    dialog = win._partial_dialog
    until(lambda: dialog.isVisible() and not dialog.busy)
    return dialog


def test_empty_screen_to_queue_and_hot_add(window):
    assert window.orchestrator is None
    assert not window.link_panel.get_links()
    empty = window.jobs_panel._empty
    assert empty.isVisible() and empty._msg.text() == "2 download interrotti"
    option = QStyleOptionButton()
    empty._recover.initStyleOption(option)
    box = empty._recover.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, empty._recover)
    assert box.width() >= empty._recover.fontMetrics().horizontalAdvance(empty._recover.text())
    dialog = open_list(window, empty._recover)
    assert dialog.table.rowCount() == 2
    assert dialog.action.text() == "Riprendi"
    assert "50,0%" in dialog.table.item(0, 1).text()
    assert "copia completata" in dialog.note.text()
    QTest.mouseClick(dialog.action, Qt.MouseButton.LeftButton)
    assert not dialog.isVisible()
    assert window.jobs_panel._filters.isVisible()
    queued = window.jobs_panel.model.get_job(0)
    assert (queued.url, queued.file_name, queued.progress) == (URL, "Film A.mkv", 50)
    assert window.orchestrator.recovery_targets[0].target.parent.parent.name == "Film_6"
    assert window.orchestrator._pending_jobs == [(0, URL)]

    dialog = open_list(window, window._partial_shortcut)
    assert dialog.table.rowCount() == 1 and dialog.action.text() == "Ricomincia da zero…"
    def dismiss():
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        box.defaultButton().click()
    QTimer.singleShot(0, dismiss)
    dialog.action.click()
    assert dialog.isVisible()
    assert window.orchestrator._pending_jobs == [(0, URL)]
    def confirm():
        box = QApplication.activeModalWidget()
        next(button for button in box.buttons() if button.text() == "Ricomincia da zero").click()
    QTimer.singleShot(0, confirm)
    dialog.action.click()
    assert window.orchestrator._pending_jobs == [(0, URL), (1, NEXT)]
    assert window.orchestrator.recovery_targets[1].saved == 0
    assert window.jobs_panel.model.get_job(1).file_name == "Film B.mkv"


def test_preserves_draft_and_refreshes_when_destination_changes(window, tmp_path):
    other = "https://mega.nz/file/More#test-key"
    window.link_panel.set_links([other])
    dialog = open_list(window, window._partial_shortcut)
    dialog.action.click()
    assert window.link_panel.get_links() == [other, URL]
    assert window.orchestrator is None
    window.controls.start_btn.click()
    assert window.orchestrator._pending_jobs == [(0, other), (1, URL)]
    assert window.orchestrator.recovery_targets[1].target.name == "Film A.mkv"
    empty = tmp_path / "new"
    empty.mkdir()
    window.controls.set_download_dir(str(empty))
    window.controls.download_dir_changed.emit(str(empty))
    dialog = open_list(window, window._partial_shortcut)
    assert dialog.table.rowCount() == 0 and not dialog.action.isEnabled()
    assert empty.name in dialog.folder.text() and str(empty) == dialog.folder.toolTip()
    TR.set_preference("en")
    assert dialog.windowTitle() == "Recover downloads"
    assert "No partial downloads" in dialog.empty.text()


def test_unknown_source_prompts_only_when_user_requests_recovery(window, monkeypatch):
    monkeypatch.setattr(partials, "completion_records", lambda: [])
    dialog = open_list(window, window.jobs_panel._empty._recover)
    assert not dialog.selection().url and window.orchestrator is None
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: (NEXT, True))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    dialog.action.click()
    assert warnings and window.orchestrator is None
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: (URL, True))
    dialog.action.click()
    assert window.orchestrator._pending_jobs == [(0, URL)]


def test_saved_session_uses_checkpoint_from_previous_job_id(window, monkeypatch):
    monkeypatch.setattr(main_window.session_store, "load", lambda: [URL])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(main_window, "confirm_already_downloaded", lambda urls, parent: urls)
    window._scan_partials()
    window._maybe_restore_session()
    assert not window.controls.start_btn.isEnabled()
    until(window.controls.start_btn.isEnabled)
    window.controls.start_btn.click()
    entry = window.orchestrator.recovery_targets[0]
    assert entry.target.parent.parent.name == "Film_6"
    assert window.jobs_panel.model.get_job(0).progress == 50
