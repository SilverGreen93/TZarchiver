"""PyInstaller entry point for the GUI exe (TZarchiver.exe).

Built with --windowed (GUI subsystem) so double-clicking the exe opens the
GUI without a terminal flash.  Paths given on the command line are queued in
the window, exactly like passing them to the original VB.NET build.
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    # when run from the source tree without installing, make src/ importable
    _src = Path(__file__).resolve().parent / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

    from tzarchiver.gui import run_gui

    sys.exit(run_gui(sys.argv[1:]))
