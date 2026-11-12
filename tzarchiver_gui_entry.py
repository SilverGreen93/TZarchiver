"""PyInstaller entry point for the GUI exe (TZarchiver.exe).

Built with --windowed (GUI subsystem) so double-clicking the exe opens the
GUI without a terminal flash.  Paths given on the command line are queued in
the window, exactly like passing them to the original VB.NET build.
"""

import sys

if __name__ == "__main__":
    from tzarchiver.gui import run_gui

    sys.exit(run_gui(sys.argv[1:]))
