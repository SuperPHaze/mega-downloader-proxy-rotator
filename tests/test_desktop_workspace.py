"""Percorsi della GUI con la rete e i dati della sessione isolati."""
import json
import sys

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QLineEdit, QMessageBox, QScrollBar, QStyle, QStyleOptionComboBox,
    QStyleOptionSpinBox, QTabWidget, QToolButton,
)

from src.gui import preferences
from src.gui.format_helpers import link_caption
from src.gui.i18n import TR, t
from src.gui.jobs_panel import FILTER_COMPLETED
from src.gui.main_window import DownloadOrchestrator, MainWindow
from src.gui.paste_links_dialog import PasteLinksDialog


@pytest.fixture
def window(qt_app, tmp_path, monkeypatch, italian_ui):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr("src.gui.main_window.LOGS_DIR", tmp_path)
    for method in ("_run_speedtest", "_maybe_check_updates_on_startup", "_session_persist"):
        monkeypatch.setattr(MainWindow, method, lambda self: None)
    monkeypatch.setattr("src.gui.main_window.session_store.load", lambda: [])
    preferences.save_stats_panel_expanded(True)  # Preferenza scritta dalle versioni precedenti.
    win = MainWindow()
    win.resize(720, 500)
    win.show()
    qt_app.processEvents()
    yield win
    win.close()
    win.deleteLater()


def test_edit_start_and_finish(window, monkeypatch):
    url = "https://mega.nz/file/EXAMPLE1#test-key"
    started = []
    monkeypatch.setattr(DownloadOrchestrator, "start", lambda self, links, **options: started.extend(links))
    monkeypatch.setattr("src.gui.link_panel.confirm_already_downloaded", lambda links, parent: links)
    monkeypatch.setattr("src.gui.main_window.confirm_already_downloaded", lambda links, parent: links)
    assert window.controls.start_btn.isHidden()
    assert not window.controls.start_btn.isEnabled()
    assert window.jobs_panel._filters.isHidden()

    def paste():
        editor = QApplication.activeModalWidget()
        if isinstance(editor, PasteLinksDialog):
            QTimer.singleShot(1000, editor.reject)
            editor.edit.setPlainText(url)
            QTest.keyClick(editor.edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)

    # Chiude il dialogo anche se la scorciatoia dovesse rompersi.
    QTimer.singleShot(0, paste)
    window.jobs_panel._empty._btn.click()
    assert window.link_panel.isVisible()
    assert window.link_panel.preview.item(0).text() == "mega.nz/file/EXAMPLE1"
    assert window.controls.start_btn.isEnabled()
    window.controls.start_btn.click()
    assert started == [url]
    assert window.jobs_panel.isVisible()
    assert window.link_panel.get_links() == []
    assert window.controls.start_btn.isHidden()
    assert window.stats_bar.isVisible()
    assert not window.controls._download_group.isEnabled()
    assert window.controls.settings_btn.isEnabled()
    window._on_file_done(0)
    assert window.jobs_panel._cards[0].isVisible()
    assert window.controls.start_btn.isHidden()
    assert window.controls._download_group.isEnabled()


def test_import_from_empty_and_clear(window, tmp_path, monkeypatch):
    source = tmp_path / "i miei link.txt"
    source.write_text("https://mega.nz/#!EXAMPLE1!testkey\n", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr("src.gui.link_panel.confirm_already_downloaded", lambda links, parent: links)
    window.jobs_panel._empty._import_btn.click()
    assert window.link_panel.isVisible()
    assert window.link_panel.preview.item(0).text() == "mega.nz/file/EXAMPLE1"
    window.link_panel.clear_btn.click()
    assert window.jobs_panel._empty.isVisible()
    assert window.controls.start_btn.isHidden()


def test_settings_action_and_language(window):
    action = window._actions["controls.settings"]
    assert action.menuRole() == QAction.MenuRole.PreferencesRole
    if sys.platform == "darwin":
        assert action in window._file_menu.actions()
    QTimer.singleShot(0, window.controls._settings_dialog.accept)
    action.trigger()
    window.controls.allow_duplicates.setChecked(True)
    assert window.link_panel.allow_dups.isChecked()
    TR.set_preference("en")
    assert window._details_toggle.text() == "Session details"
    assert window.controls._heading.text() == "Download queue"
    assert window.controls._settings_dialog.windowTitle() == "Settings"


@pytest.mark.parametrize("lang, dark, width, height", [
    ("it", False, 640, 440), ("en", True, 640, 440),
    ("en", False, 920, 580), ("it", True, 920, 580),
])
def test_single_page_starts_without_scroll_and_toggles_inline(window, qt_app, lang, dark, width, height):
    TR.set_preference(lang)
    window._on_theme_toggle(dark)
    window.resize(width, height)
    qt_app.processEvents()
    assert window.size().width() == width and window.size().height() == height
    assert window.jobs_panel._empty.isVisible()
    assert window._details_toggle.isVisible() and not window._details_toggle.isChecked()
    assert window._details_scroll.isHidden()
    assert not window.findChildren(QTabWidget)
    assert not any(bar.isVisible() for bar in window.findChildren(QScrollBar))
    for expanded in (True, False):
        window._details_toggle.setFocus()
        QTest.keyClick(window._details_toggle, Qt.Key.Key_Space)
        qt_app.processEvents()
        assert window.jobs_panel._empty.isVisible()
        assert window._stats_panel.isVisible() == expanded
        assert window.proxy_bar.isVisible() == expanded
        assert not any(bar.isVisible() for bar in window.findChildren(QScrollBar))


def test_single_page_session_shows_metrics_and_retains_queue(window, qt_app):
    panel = window.jobs_panel
    window.resize(920, 580)
    window._details_toggle.click()
    panel.reset(["https://mega.nz/file/EXAMPLE1#key"])
    panel.model.set_file_info(0, "Esempio.pdf", "")
    panel.model.set_throughput(0, 2048, 4096, 8192)
    window._show_session()
    qt_app.processEvents()
    assert panel._cards[0].isVisible()
    assert window.stats_bar.isVisible()
    assert window._stats_panel._body.isVisible() and window.proxy_bar._card_validation.isVisible()
    assert window._details_scroll.verticalScrollBar().maximum() == 0
    assert window._details_scroll.horizontalScrollBar().maximum() == 0
    window._stats_panel._copy_btn.click()
    assert "Esempio.pdf" in QApplication.clipboard().text()
    TR.set_preference("en")
    assert window._details_toggle.text() == "Session details"
    assert window._stats_panel._title_lbl.text() == "Statistics"
    window.resize(700, 500)
    qt_app.processEvents()
    assert window.height() == 500
    assert window._details_scroll.horizontalScrollBar().maximum() == 0
    assert panel._cards[0].isVisible()


@pytest.mark.parametrize("discard", [False, True])
def test_cancel_file_requires_explicit_data_removal(window, monkeypatch, discard):
    panel = window.jobs_panel
    panel.reset(["https://mega.nz/file/EXAMPLE1#key"])
    panel.model.set_progress(0, 20)
    panel._filter_buttons[FILTER_COMPLETED].click()
    assert panel._filter_empty.isVisible()
    panel._filter_buttons["all"].click()
    card = panel._cards[0]
    card._expand_btn.setFocus()
    QTest.keyClick(card._expand_btn, Qt.Key.Key_Space)
    assert card._details_btn.isVisible()
    assert card._percent_lbl.text() == "20%"
    removed = []
    monkeypatch.setattr(window, "_delete_folder_for", removed.append)

    def confirm(box):
        assert not box.checkBox().isChecked()
        box.checkBox().setChecked(discard)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", confirm)
    menu = card._action_btn.menu()
    def choose_cancel():
        menu.setActiveAction(card._file_action)
        QTest.keyClick(menu, Qt.Key.Key_Return)

    assert card._file_action.text() == "Annulla download"
    menu.aboutToShow.connect(lambda: QTimer.singleShot(0, choose_cancel))
    card._action_btn.showMenu()
    assert removed == ([0] if discard else [])


@pytest.mark.parametrize("lang, dark, summary", [
    ("it", False, "Ultimo errore: File o cartella non trovati."),
    ("en", True, "Last error: File or folder not found."),
])
def test_single_page_long_file_and_os_error_fit_in_row(window, qt_app, lang, dark, summary):
    TR.set_preference(lang)
    window._on_theme_toggle(dark)
    window.resize(640, 440)
    panel = window.jobs_panel
    panel.reset(["https://mega.nz/file/EXAMPLE1#key"])
    window._show_session()
    title = "Atlante delle coste " * 16 + "volume IV.pdf"
    panel.model.set_file_info(0, title, "")
    panel.model.set_progress(0, 14)
    path = "/archivio/" * 32 + "volume IV.pdf.part"
    panel.on_failed(0, 1, "download_failed_paren", {"error": f"[Errno 2] No such file or directory: '{path}'"})
    card = panel._cards[0]
    card._expand_btn.click()
    qt_app.processEvents()
    assert card._name_lbl.text().endswith(".pdf") and card._name_lbl.text() != title
    assert card._name_lbl.toolTip() == title
    assert card._error_lbl.text() == summary
    assert path in card._error_lbl.toolTip()
    assert path in card._error_lbl.accessibleDescription()
    assert card._progress.height() == 5
    assert panel._scroll.horizontalScrollBar().maximum() == 0
    assert panel._scroll.verticalScrollBar().maximum() == 0

    panel.model.mark_completed(0)
    assert card._file_action.text() == t("jobs_panel.action_open_folder")
    panel.model.mark_failed_fatal(0, "ip_check_failed", {"error": "timeout"})
    assert card._file_action.text() == t("jobs_panel.action_restart")
    opened = []
    card.double_clicked.connect(opened.append)
    card._details_action.trigger()
    assert opened == [0]


def test_restored_draft_keeps_folder_link_and_hides_key(window, monkeypatch):
    url = "https://mega.nz/folder/EXAMPLE1#privatekey/file/EXAMPLE2"
    monkeypatch.setattr("src.gui.main_window.session_store.load", lambda: [url])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window._maybe_restore_session()
    assert window.link_panel.get_links() == [url]
    assert window.link_panel.preview.item(0).text() == link_caption(url) == "mega.nz/folder/EXAMPLE1/EXAMPLE2"
    assert window.controls.start_btn.isVisible()
    assert window.link_panel.preview.accessibleName() == t("workspace.queue_title")


def test_foreign_destination_requires_local_choice(window, monkeypatch, tmp_path):
    foreign = "/Volumes/Drive/Downloads" if sys.platform == "win32" else r"C:\Downloads\Mega"
    window.controls.set_download_dir(foreign)
    url = "https://mega.nz/file/EXAMPLE1#key"
    window.link_panel.set_links([url])
    started = []
    monkeypatch.setattr(window, "_start_with_links", started.extend)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "")
    window.controls.start_btn.click()
    assert not started
    assert window.controls.get_download_dir() == foreign
    assert window.link_panel.isVisible()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    window.controls.start_btn.click()
    assert started == [url]
    assert preferences.load_download_dir() == str(tmp_path)


def test_history_search_selection_and_live_completion(window, qt_app, monkeypatch, tmp_path):
    from src.core import download_history
    from src.gui.history_dialog import QDesktopServices

    monkeypatch.setattr(download_history, "LOGS_DIR", tmp_path)
    path = download_history.download_history_path()
    def record(name):
        return json.dumps({"handle": "same", "file_name": name, "file_size": 3 << 30,
                           "completed_at": "2026-11-25T09:00:00", "path": str(tmp_path / name)}) + "\n"

    path.with_suffix(".log.1").write_text(record("Prima copia.pdf"), encoding="utf-8")
    path.write_text("[]\nparziale\n" + record("Atlante.pdf"), encoding="utf-8")
    button = next(b for b in window.findChildren(QToolButton) if b.defaultAction() is window._actions["history.button"])
    button.click()
    history = window._history_dialog
    assert history.isVisible() and not history.isModal()
    assert [e.name for e in history.model.entries] == ["Atlante.pdf", "Prima copia.pdf"]
    assert history.model.index(0, 2).data() == "3.0 GB"
    history.search.setText("ATLANTE")
    assert history.filtered.rowCount() == 1
    history.table.selectRow(0)
    folders = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: folders.append(url.toLocalFile()) or True)
    history.open_folder.click()
    assert folders == [str(tmp_path)]

    with path.open("a", encoding="utf-8") as stream:
        stream.write(record("Altro.epub"))
    window._on_file_done(0)
    assert history.model.entries[0].name == "Altro.epub"
    assert history._selection().name == "Atlante.pdf"
    history.search.setText("nessuna-corrispondenza")
    assert history.empty.isVisible() and not history.open_folder.isEnabled()
    TR.set_preference("en")
    assert history.empty.text() == t("history.no_match")
    history.close()
    path.unlink()
    path.with_suffix(".log.1").unlink()
    button.click()
    assert history.empty.text() == t("history.empty")
    assert history.filtered.rowCount() == 0


def test_reopen_and_save_link_list(window, monkeypatch):
    links = ["https://mega.nz/file/EXAMPLE1#key", "https://mega.nz/file/EXAMPLE2#key"]
    window.link_panel.set_links(links)
    checked = []
    def confirm(additions, parent):
        checked.append(additions)
        return additions
    monkeypatch.setattr("src.gui.link_panel.confirm_already_downloaded", confirm)
    assert window.link_panel.paste_btn.text() == "Apri elenco link"
    replacement = "https://mega.nz/file/EXAMPLE3#" + "x" * 200
    def edit():
        dialog = QApplication.activeModalWidget()
        assert dialog.edit.toPlainText().splitlines() == links
        assert dialog.edit.textCursor().atEnd() and dialog.edit.textCursor().block().text() == ""
        assert dialog.edit.font().pointSizeF() >= 13
        assert dialog.windowTitle() == "Elenco link" and dialog.add_btn.text() == "Salva elenco"
        dialog.edit.setPlainText("\n".join([links[1], replacement]))
        dialog.add_btn.click()
    QTimer.singleShot(0, edit)
    window.link_panel.paste_btn.click()
    assert window.link_panel.get_links() == [links[1], replacement]
    assert checked == [[replacement]]
    def clear():
        dialog = QApplication.activeModalWidget()
        dialog.edit.clear()
        assert dialog.add_btn.isEnabled()
        dialog.add_btn.click()
    QTimer.singleShot(0, clear)
    window.link_panel.paste_btn.click()
    assert window.jobs_panel._empty.isVisible()


def test_debug_toggles_in_main_window_while_queue_updates(window, tmp_path, monkeypatch, qt_app):
    from src.core.config import TERMINAL_LOG

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: pytest.fail("External process"))
    window.jobs_panel.reset(["https://mega.nz/file/EXAMPLE1#test"])
    window._show_session()
    panel = window._debug_panel
    action = window._actions["debug.button"]
    button = next(b for b in window.findChildren(QToolButton) if b.defaultAction() is action)
    assert panel.isHidden() and not button.isChecked()
    (tmp_path / TERMINAL_LOG).write_text("[DEBUG] prima del clic\n")
    visible_windows = {w for w in QApplication.topLevelWidgets() if w.isVisible()}
    window._details_toggle.click()
    button.click()
    qt_app.processEvents()
    assert panel.isVisible() and panel.window() is window and button.isChecked()
    assert not window._details_toggle.isChecked() and window.jobs_panel.isVisible()
    assert visible_windows == {w for w in QApplication.topLevelWidgets() if w.isVisible()}
    assert "prima del clic" in panel.output.toPlainText()
    window.jobs_panel.model.set_progress(0, 21)
    TR.set_preference("en")
    assert panel.output.accessibleName() == "Debug log"
    panel._hide_button.click()
    window.jobs_panel.model.set_progress(0, 42)
    qt_app.processEvents()
    assert panel.isHidden() and not action.isChecked()
    assert window.isVisible() and window.jobs_panel._cards[0]._percent_lbl.text() == "42%"
    action.trigger()
    assert panel.isVisible()
    window._details_toggle.click()
    assert not action.isChecked() and panel.isHidden()
    button.click()
    button.click()
    assert panel.isHidden() and window.isVisible()


def test_file_details_and_pending_progress(window, qt_app):
    url = "https://mega.nz/file/EXAMPLE1#" + "long-key" * 15
    panel = window.jobs_panel
    panel.reset([url])
    window._show_session()
    card = panel._cards[0]
    assert card._percent_lbl.isHidden() and card._progress.isHidden()
    card._details_action.trigger()
    detail = window._open_dialogs[0]
    assert isinstance(detail.url_edit, QLineEdit)
    assert detail.url_edit.isReadOnly() and detail.url_edit.text() == url
    assert detail.url_edit.cursorPosition() == 0
    assert len(detail.findChildren(QLineEdit)) == 1
    detail.copy_btn.click()
    assert QApplication.clipboard().text() == url
    panel.model.set_progress(0, 12)
    qt_app.processEvents()
    assert card._percent_lbl.isVisible() and card._percent_lbl.text() == "12%"
    assert detail.metric_values["progress"].text() == "12%"
    for key, label in detail.metric_labels.items():
        assert label.x() == detail.metric_values[key].x()
    assert detail.metric_values["status"].text() == "In corso"


@pytest.mark.parametrize("dark", [False, True])
def test_settings_arrow_hit_targets_work_in_both_themes(window, qt_app, dark):
    window._on_theme_toggle(dark)
    controls = window.controls
    controls._settings_dialog.show()
    qt_app.processEvents()
    spin = controls.time_limit_spin
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    initial = spin.value()
    for sub, expected in ((QStyle.SubControl.SC_SpinBoxUp, initial + 1),
                          (QStyle.SubControl.SC_SpinBoxDown, initial)):
        target = spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, sub, spin)
        assert target.isValid() and spin.rect().contains(target.center())
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=target.center())
        assert spin.value() == expected
    combo = controls.concurrency_combo
    combo_option = QStyleOptionComboBox()
    combo.initStyleOption(combo_option)
    arrow = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, combo_option,
                                         QStyle.SubControl.SC_ComboBoxArrow, combo)
    assert arrow.isValid() and combo.rect().contains(arrow.center())
    combo.setFocus()
    previous = combo.currentIndex()
    QTest.keyClick(combo, Qt.Key.Key_Down)
    assert combo.currentIndex() == previous + 1
