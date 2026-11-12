# TZarchiver

Utility application to read and write Trainz `.tzarc` files.

This is the Python port of the original VB.NET application: the archive format
code lives in a plain, Qt-free module (`tzarchiver.tzarc`) and the GUI has been
rebuilt with PyQt6, reproducing the original window.

## Getting Started

From a terminal:

```
pip install -e ".[gui]"
tzarchiver-gui                 # open the GUI
tzarchiver "Some Asset.tzarc"  # list an archive
```

Or run straight from the source tree with `PYTHONPATH=src` set, using
`tzarchiver_cli_entry.py` / `tzarchiver_gui_entry.py`.

## Command line

```
tzarchiver <file or folder>...            list archives / archive folders
tzarchiver -x <file.tzarc> [-o <out>]     extract (default: <archive name> beside the archive)
tzarchiver <folder> [--v2]                create <folder>.tzarc (--v2 = compressed)
```

With no arguments the GUI starts instead; paths given on the command line are
queued in the window, exactly like drag & drop.

## Project layout

```
src/tzarchiver/tzarc.py   archive format logic (v1 + v2), no Qt imports
src/tzarchiver/cli.py     command line entry point
src/tzarchiver/gui.py     PyQt6 window (port of frmMain)
tests/                    pytest suite, fixtures in tests/test_files
```

Run the tests with `python -m pytest` (no installation needed, `tests/conftest.py`
puts `src` on the path).

## Building the Windows executables

The original project was built with Microsoft Visual Studio 2022 and .NET
Framework 4.8 (the sources remain under `TZarchiver/`). The Python build can be
packaged with PyInstaller using the two entry scripts:

```
pyinstaller --windowed --icon assets/175.ico tzarchiver_gui_entry.py   # TZarchiver.exe
pyinstaller --console tzarchiver_cli_entry.py                          # TZarchiverCli.exe
```

## File Format Specifications

The TZarc File Format Specification was determined by reverse-engineering and
is described here: [TZarc File Format Specification](tzarc-format.md)

## Issues and Feature requests

For any bugs, issues or feature requests, use the Issues tab in GitHub.

**Note** that Trainz 2022 changed the TZarc format to v2, with zlib
compression. Both reading and writing v2 archives are supported here: from the
command line with `--v2`, or in the GUI with the "Create compressed v2
archives" checkbox.

## License

This project is licensed under the MIT License - see [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

This project was possible by doing reverse engineering on the TZarc file format and no official information was given in regards to this file format from Auran/N3V.
