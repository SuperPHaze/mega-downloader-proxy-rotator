"""Avvio dal collegamento di Esplora file, con lo stesso script usato dall'installer."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Richiede la shell di Windows")
def test_explorer_shortcut_launches_without_a_console(tmp_path):
    project = tmp_path / "Folder with spaces"
    script = Path(__file__).resolve().parents[1] / "scripts/create_windows_shortcut.ps1"
    (project / "scripts").mkdir(parents=True)
    (project / "src").mkdir()
    launcher = project / "scripts" / script.name
    shutil.copy2(script, launcher)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(project / "venv")], check=True)
    (project / "src/main.py").write_text(
        "import ctypes, sys\nfrom pathlib import Path\n"
        "assert Path(sys.executable).name.lower() == 'pythonw.exe'\n"
        "assert not ctypes.windll.kernel32.GetConsoleWindow()\n"
        "Path('started.txt').touch()\n"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher)],
                   check=True, timeout=30)
    os.startfile(str(project / "Mega Downloader Proxy Rotator.lnk"))
    marker = project / "started.txt"
    deadline = time.monotonic() + 20
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert marker.exists()
