import pytest

from tools import cli_download


@pytest.mark.parametrize(("events", "code"), [
    (("fatal_error", "all_done"), 1), (("all_done", "fatal_error"), 1),
    (("abandoned", "all_done"), 1), (("all_done", "job_cancelled"), 1),
    (("all_done", "all_done"), 0),
])
def test_cli_returns_the_outcome_of_the_whole_queue(monkeypatch, events, code):
    from PyQt6.QtCore import QEventLoop
    # Use an isolated event loop without replacing the suite's QApplication.
    loop = QEventLoop()
    monkeypatch.setattr(cli_download, "QCoreApplication", lambda argv: loop)
    cli_download.QCoreApplication.quit = loop.quit
    monkeypatch.setattr(cli_download, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_download.DownloadOrchestrator, "shutdown", lambda self: True)
    def start(orch, links, **options):
        for fid, event in enumerate(events):
            args = {"fatal_error": ("failure",), "abandoned": (links[fid], 1, "failure")}
            getattr(orch, event).emit(fid, *args.get(event, ()))
    monkeypatch.setattr(cli_download.DownloadOrchestrator, "start", start)
    assert cli_download.main(["a", "b"]) == code
