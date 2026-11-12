"""PyInstaller entry point for the CLI exe (TZarchiverCli.exe).

Built with --console so stdout/stderr are attached to the terminal by
default.  With no arguments it prints usage and exits; use TZarchiver.exe
(GUI subsystem) for the GUI.
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    # when run from the source tree without installing, make src/ importable
    _src = Path(__file__).resolve().parent / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    from tzarchiver.cli import main

    if not sys.argv[1:]:
        print("Usage: TZarchiverCli.exe \"config.bin\"")
        print("       TZarchiverCli.exe --extract <file.tzarc> [-o <out folder>]")
        print("       TZarchiverCli.exe <folder> [--v2]")
        print("       Use TZarchiver.exe for the GUI.")
        sys.exit(1)

    sys.exit(main())
