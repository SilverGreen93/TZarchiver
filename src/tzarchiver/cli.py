"""Command line entry point.

With no arguments the GUI launches; with one or more paths the app runs in CLI
mode: archives are listed (and optionally extracted), folders are turned into
``<folder>.tzarc`` archives.

Port of the command line handling in frmMain.vb.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .tzarc import (
    V1,
    V2,
    Archive,
    TzarcError,
    create_archive,
    default_extract_dir,
    read_archive,
)

__all__ = ["main", "run_cli", "describe"]


def main(argv: list[str] | None = None) -> int:
    """Entry point: no args -> GUI; paths -> CLI listing/extraction/creation."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="tzarchiver",
        description="Extract or create Trainz .tzarc archives.",
    )
    parser.add_argument("paths", nargs="*", help=".tzarc files and/or folders to archive")
    parser.add_argument("-x", "--extract", action="store_true", help="extract archives instead of only listing them")
    parser.add_argument("-o", "--out", help="extract to this folder instead of <archive name> beside the archive")
    parser.add_argument("--v2", action="store_true", help="create compressed (version 2) archives")
    args = parser.parse_args(argv)

    if not args.paths:
        try:
            from .gui import run_gui
        except ImportError:
            # distro packages ship the CLI as pure Python and expect the
            # system python to provide PyQt6; it may genuinely be missing
            print(
                "Error: the GUI needs PyQt6, which is not installed.\n"
                "Install it (pip install \"tzarchiver[gui]\", or your distro's\n"
                "python3-pyqt6 / python-pyqt6 package), or work from the\n"
                "terminal: tzarchiver \"Some Asset\"",
                file=sys.stderr,
            )
            return 1

        return run_gui(args.paths)

    return 0 if run_cli(args.paths, extract=args.extract, out=args.out, v2=args.v2) else 1


def run_cli(paths: list[str], extract: bool = False, out: str | None = None, v2: bool = False) -> bool:
    """Process every path, printing what happened. Returns False if any failed.

    Folders are archived into ``<folder>.tzarc`` (the app's Create button),
    files are read as archives (its Extract button).
    """
    ok = True
    version = V2 if v2 else V1
    for raw in paths:
        path = Path(raw)
        try:
            if path.is_dir():
                archive = create_archive(path, version=version)
                target = Path(str(path) + ".tzarc")
                archive.write(target, version=version)
                print(f"created {target} ({len(archive)} file{'s' if len(archive) != 1 else ''}, v{version})")
            else:
                archive = read_archive(path)
                print(describe(path, archive))
                if extract:
                    dest = archive.extract(out if out else default_extract_dir(path))
                    print(f"extracted to {dest}")
        except (TzarcError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            ok = False
    return ok


def describe(path: str | Path, archive: Archive | None = None) -> str:
    """Multi-line listing of an archive, as shown in the GUI tree."""
    archive = archive or read_archive(path)
    lines = [f"{Path(path).name} (v{archive.version}, {len(archive)} file{'s' if len(archive) != 1 else ''})"]
    for entry in archive.entries:
        lines.append(f"  {entry.name}  [{entry.size} bytes]")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
