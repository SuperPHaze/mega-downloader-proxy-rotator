"""Il pulsante usa il worker reale; il server di misura è simulato alla presa HTTP."""
import io
import threading

import pytest
import requests

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtTest import QSignalSpy

from src.gui import preferences, speedtest_worker
from src.gui.i18n import TR
from src.gui.main_window import MainWindow


def test_line_measurement_from_startup_through_retry(qt_app, italian_ui, tmp_path, monkeypatch):
    monkeypatch.setattr(preferences, "_PREFS_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(MainWindow, "_maybe_check_updates_on_startup", lambda self: None)
    monkeypatch.setattr(MainWindow, "_maybe_restore_session", lambda self: None)
    monkeypatch.setattr(speedtest_worker, "LINE_SPEEDTEST_STREAMS", 1)
    monkeypatch.setattr(speedtest_worker, "LINE_SPEEDTEST_BYTES", 64_000)
    gate = threading.Event()
    status = 503
    size = 64_000

    def response(url, **options):
        assert url.startswith("https://")
        assert options["proxies"]["all"] is None
        assert gate.wait(3)
        result = requests.Response()
        result.url = url
        result.status_code = status
        result.raw = io.BytesIO(b"x" * size)
        return result

    monkeypatch.setattr(speedtest_worker.requests, "get", response)
    window = MainWindow()
    bar = window.proxy_bar
    try:
        def finish():
            spy = QSignalSpy(window._speedtest_worker.finished)
            assert not bar._speedtest_btn.isEnabled()
            gate.set()
            assert len(spy) or spy.wait(3000)
            qt_app.processEvents()
            assert bar._speedtest_btn.isEnabled()

        finish()
        assert "503" in bar._line_note.text()
        assert bar._speedtest_btn.text() == "Riprova misura"
        status = 200
        gate.clear()
        bar._speedtest_btn.click()
        assert bar._speedtest_btn.text() == "Misurazione…"
        finish()
        value = bar._card_band._value.text()
        assert value.endswith(" Mbit/s") and preferences.load_link_speed_mbps() > 0
        gate.clear()
        size = 0
        bar._speedtest_btn.click()
        finish()
        assert "ultima misura riuscita" in bar._line_note.text()
        assert bar._card_band._value.text() == value
        TR.set_preference("en")
        assert "last successful measurement" in bar._line_note.text()
    finally:
        gate.set()
        window._speedtest_worker.wait(3000)
        window.close()
        window.deleteLater()
