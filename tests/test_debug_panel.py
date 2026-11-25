"""Il lettore segue il file di log anche dopo una pausa o una pulizia."""
import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtTest import QTest

from src.gui.debug_panel import DebugPanel


@pytest.fixture
def panel(tmp_path):
    widget = DebugPanel(tmp_path / "session.log")
    yield widget
    widget.close()
    widget.deleteLater()


def test_follows_session_across_hide_and_split_utf8(panel, tmp_path):
    panel.show()
    view = panel.output
    assert view.isReadOnly() and not view.toPlainText()
    path = tmp_path / "session.log"
    path.write_bytes(b"[DEBUG] uno\n[INFO] velocit\xc3")
    panel._refresh()
    assert view.toPlainText() == "[DEBUG] uno\n[INFO] velocit"
    with path.open("ab") as stream:
        stream.write(b"\xa0\n")
    for _ in range(20):
        QTest.qWait(50)
        if view.toPlainText().endswith("velocità\n"):
            break
    assert view.toPlainText().endswith("velocità\n")
    panel.hide()
    assert not panel._timer.isActive()
    with path.open("ab") as stream:
        stream.write(b"ancora in esecuzione\n")
    panel.show()
    assert view.toPlainText() == path.read_text(encoding="utf-8")


def test_reset_when_log_is_cleaned_replaced_or_removed(panel, tmp_path):
    path = tmp_path / "session.log"
    path.write_text("vecchio\n")
    panel.show()
    # Stesso inode, già tornato oltre l'offset precedente dopo il troncamento.
    path.write_text("prima riga dopo la pulizia\n")
    panel._refresh()
    assert panel.output.toPlainText() == path.read_text()
    new_path = tmp_path / "replacement"
    new_path.write_text("file diverso\n")
    new_path.replace(path)
    panel._refresh()
    assert panel.output.toPlainText() == "file diverso\n"
    path.unlink()
    panel._refresh()
    assert not panel.output.toPlainText()
    path.write_text("ripreso\n")
    panel._refresh()
    assert panel.output.toPlainText() == "ripreso\n"


def test_large_history_and_reading_earlier_lines(panel, tmp_path, qt_app):
    path = tmp_path / "session.log"
    path.write_text("".join(f"[DEBUG] prova {i}\n" for i in range(15000)))
    panel.show()
    qt_app.processEvents()
    view = panel.output
    assert view.blockCount() <= view.maximumBlockCount()
    assert view.toPlainText().endswith("[DEBUG] prova 14999\n")
    previous = view.document().find("[DEBUG] prova 14700")
    view.setTextCursor(previous)
    scroll = view.verticalScrollBar()
    scroll.setValue(scroll.maximum() // 2)
    first_visible = view.firstVisibleBlock().text()
    with path.open("a") as stream:
        stream.write("nuovo messaggio\n")
    panel._refresh()
    assert view.textCursor().selectedText() == "[DEBUG] prova 14700"
    assert view.firstVisibleBlock().text() == first_visible
    assert view.toPlainText().endswith("nuovo messaggio\n")
