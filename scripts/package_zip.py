"""Archive the staged release and keep Finder launchers executable on extraction."""
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def write_archive(project: Path, destination: Path) -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(project.rglob("*")):
            if path.is_file():
                name = path.relative_to(project.parent).as_posix()
                archive.write(path, name)
                if path.match("*.app/Contents/MacOS/*"):
                    # Written in the central directory when the ZIP closes, even on Windows.
                    entry = archive.getinfo(name)
                    entry.create_system = 3
                    entry.external_attr = 0o100755 << 16


if __name__ == "__main__":
    write_archive(Path(sys.argv[1]), Path(sys.argv[2]))
