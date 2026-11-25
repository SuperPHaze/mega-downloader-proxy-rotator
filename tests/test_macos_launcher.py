"""L'avvio da una cartella Finder con spazi si prova senza scaricare pacchetti."""
import os
import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = "Mega Downloader Proxy Rotator.app"


def copy_launcher(project):
    bundle = project / BUNDLE
    shutil.copytree(PROJECT / BUNDLE, bundle)
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["CFBundlePackageType"] == "APPL"
    assert (bundle / "Contents/Resources" / info["CFBundleIconFile"]).is_file()
    return bundle / "Contents/MacOS" / info["CFBundleExecutable"]


@pytest.mark.skipif(os.name != "posix", reason="The Finder launcher uses /bin/sh")
@pytest.mark.parametrize("windows_env", [False, True])
def test_launcher_creates_and_reuses_isolated_environment(tmp_path, windows_env):
    project = tmp_path / "My Downloads"
    source = project / "src"
    source.mkdir(parents=True)
    if windows_env:
        (project / "venv" / "Scripts").mkdir(parents=True)
    launcher = copy_launcher(project)
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


@pytest.mark.skipif(sys.platform != "darwin", reason="Richiede Launch Services di macOS")
def test_finder_launch_without_a_controlling_terminal(tmp_path):
    project = tmp_path / "Avvio dal Finder"
    source = project / "src"
    source.mkdir(parents=True)
    copy_launcher(project)
    (project / "requirements.txt").write_text("")
    (source / "main.py").write_text(
        "import errno, json, os\nfrom pathlib import Path\n"
        "try:\n    os.close(os.open('/dev/tty', os.O_RDONLY))\n    tty = True\n"
        "except OSError as exc:\n    assert exc.errno in (errno.ENXIO, errno.ENODEV)\n    tty = False\n"
        "Path('launch.json').write_text(json.dumps([tty, *[os.isatty(i) for i in range(3)]]))\n"
    )
    subprocess.run([sys.executable, "-m", "venv", str(project / "venv")], check=True, timeout=90)
    subprocess.run(["/usr/bin/open", "-n", "-g", "-W", str(project / BUNDLE)], check=True, timeout=45)
    assert json.loads((project / "launch.json").read_text()) == [False] * 4


def test_release_zip_preserves_executable_on_extraction(tmp_path):
    import zipfile
    from scripts.package_zip import write_archive

    project = tmp_path / "release"
    executable = copy_launcher(project)
    # Incluso quando il filesystem di staging non conserva il bit Unix.
    executable.chmod(0o644)
    archive = tmp_path / "release.zip"
    write_archive(project, archive)
    name = executable.relative_to(tmp_path).as_posix()
    with zipfile.ZipFile(archive) as zipped:
        entry = zipped.getinfo(name)
        assert entry.create_system == 3 and entry.external_attr >> 16 == 0o100755
        assert zipped.read(name).startswith(b"#!/bin/sh\n")
