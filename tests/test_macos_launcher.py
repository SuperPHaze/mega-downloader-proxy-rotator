"""L'avvio da una cartella Finder con spazi si prova senza scaricare pacchetti."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "posix", reason="The Finder launcher uses /bin/sh")
@pytest.mark.parametrize("windows_env", [False, True])
def test_launcher_creates_and_reuses_isolated_environment(tmp_path, windows_env):
    project = tmp_path / "My Downloads"
    source = project / "src"
    source.mkdir(parents=True)
    if windows_env:
        (project / "venv" / "Scripts").mkdir(parents=True)
    launcher = project / "avvia.command"
    shutil.copy2(Path(__file__).resolve().parents[1] / launcher.name, launcher)
    (project / "requirements.txt").write_text("", encoding="utf-8")
    (source / "main.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "Path('started.txt').write_text(sys.prefix, encoding='utf-8')\n",
        encoding="utf-8",
    )
    environment = dict(os.environ, PIP_NO_INDEX="1", PYTHONPATH="")
    expected = project / (".venv-macos" if windows_env else "venv")
    marker = project / "started.txt"
    for _ in range(2):
        subprocess.run([str(launcher)], cwd=tmp_path, env=environment, check=True, timeout=90)
        assert Path(marker.read_text(encoding="utf-8")).resolve() == expected.resolve()
        marker.unlink()
    if windows_env:
        assert list((project / "venv").iterdir()) == [project / "venv" / "Scripts"]
