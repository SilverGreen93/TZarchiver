"""PyInstaller entry point for the CLI exe (TZarchiverCli.exe).

Built with --console so stdout/stderr are attached to the terminal by
default.  With no arguments it prints usage and exits; use TZarchiver.exe
(GUI subsystem) for the GUI.
"""

import sys

if __name__ == "__main__":
    from tzarchiver.cli import main

    if not sys.argv[1:]:
        print("Usage: TZarchiverCli.exe \"config.bin\"")
        print("       TZarchiverCli.exe --extract <file.tzarc> [-o <out folder>]")
        print("       TZarchiverCli.exe <folder> [--v2]")
        print("       Use TZarchiver.exe for the GUI.")
        sys.exit(1)

    sys.exit(main())
