"""PyQt6 GUI for TZarchiver.

Port of frmMain (WinForms): a processing queue on the left, the contents of the
queued archives on the right, and Extract / Create / Remove item / Clear list
buttons.  Files and folders can be dragged into the window.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .tzarc import (
    V1,
    V2,
    TzarcError,
    create_archive,
    default_extract_dir,
    read_archive,
)

__all__ = ["TzarcWindow", "run_gui"]

_ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets"

APP_TITLE = f"TZarchiver {__version__}"
GITHUB_URL = "https://github.com/SilverGreen93/TZarchiver"
ICON_FILE = "175.ico"
HINT = "Drag & Drop files to extract and folders to create!"


def _resource_path(name: str) -> str | None:
    """Absolute path to a bundled resource (works from source and PyInstaller)."""
    if getattr(sys, "frozen", False):  # running under PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / name
    else:
        base = _ASSET_DIR / name
    return str(base) if base.is_file() else None


def _window_icon() -> QIcon | None:
    """The app icon, if it can be found next to the code or in the bundle.

    Setting it on the application as well as the window is what puts it in the
    Windows taskbar; --icon alone only stamps the exe file on disk.
    """
    path = _resource_path(ICON_FILE)
    return QIcon(path) if path else None


class TzarcWindow(QWidget):
    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.queue: list[str] = []
        self._build()
        self.setAcceptDrops(True)
        if paths:
            self.load_paths(paths, list_only=True)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(APP_TITLE)
        icon = _window_icon()
        if icon:
            self.setWindowIcon(icon)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 6)
        outer.setSpacing(6)

        columns = QHBoxLayout()
        columns.setSpacing(10)

        # queue column: list plus the two action buttons below it
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel("Processing queue:"))
        self.lst_archives = QListWidget()
        self.lst_archives.setMinimumSize(214, 184)
        left.addWidget(self.lst_archives, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.btn_extract = QPushButton("Extract TZarc")
        self.btn_create = QPushButton("Create TZarc")
        for button in (self.btn_extract, self.btn_create):
            button.setMinimumSize(105, 46)
        buttons.addWidget(self.btn_extract)
        buttons.addWidget(self.btn_create)
        left.addLayout(buttons)

        self.chk_v2 = QCheckBox("Create compressed v2 archives")
        left.addWidget(self.chk_v2)
        columns.addLayout(left)

        # middle column: queue maintenance and the drag hint
        middle = QVBoxLayout()
        middle.setSpacing(4)
        self.btn_remove = QPushButton("Remove item")
        self.btn_clear = QPushButton("Clear list")
        for button in (self.btn_remove, self.btn_clear):
            button.setMinimumSize(72, 47)
        middle.addWidget(self.btn_remove)
        middle.addWidget(self.btn_clear)
        hint = QLabel(HINT)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        hint.setMinimumWidth(72)
        middle.addWidget(hint, 1)
        middle.addStretch(0)
        columns.addLayout(middle)

        # contents column
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(QLabel("Archive contents:"))
        self.tv_contents = QTreeWidget()
        self.tv_contents.setHeaderHidden(True)
        self.tv_contents.setMinimumSize(249, 235)
        right.addWidget(self.tv_contents, 1)
        columns.addLayout(right)

        outer.addLayout(columns, 1)

        footer = QHBoxLayout()
        footer.addWidget(QLabel(f"by SilverGreen93 (c) 2024"), 0, Qt.AlignmentFlag.AlignHCenter)
        link = QLabel(f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>')
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda: webbrowser.open(GITHUB_URL))
        footer.addWidget(link, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(footer)

        self.btn_extract.clicked.connect(self.on_extract)
        self.btn_create.clicked.connect(self.on_create)
        self.btn_remove.clicked.connect(self.on_remove)
        self.btn_clear.clicked.connect(self.on_clear)

        self.setFixedSize(max(self.sizeHint().width(), 567), max(self.sizeHint().height(), 315))

    # -- queue ---------------------------------------------------------------
    def load_paths(self, paths: list[str], list_only: bool = True) -> None:
        """Add paths to the queue and refresh the contents tree (like frmMain_Load)."""
        for path in paths:
            self.queue.append(str(path))
            self.lst_archives.addItem(QListWidgetItem(Path(path).name))
            self.lst_archives.setCurrentRow(self.lst_archives.count() - 1)
        if list_only:
            self.show_contents()

    def add_files_dialog(self) -> None:
        """Pick archives to queue (also reachable by dropping them on the window)."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select tzarc files", "", "Trainz archives (*.tzarc);;All files (*.*)")
        if files:
            self.load_paths(files)

    def add_folder_dialog(self) -> None:
        """Pick a folder to queue for archiving."""
        folder = QFileDialog.getExistingDirectory(self, "Select folder to archive")
        if folder:
            self.load_paths([folder])

    def on_remove(self) -> None:
        row = self.lst_archives.currentRow()
        if row < 0:
            return
        self.lst_archives.takeItem(row)
        del self.queue[row]
        if row < self.tv_contents.topLevelItemCount():
            self.tv_contents.takeTopLevelItem(row)
        self.lst_archives.setCurrentRow(self.lst_archives.count() - 1)

    def on_clear(self) -> None:
        self.lst_archives.clear()
        self.tv_contents.clear()
        self.queue.clear()

    # -- contents tree -------------------------------------------------------
    def show_contents(self) -> None:
        """Fill the tree with the contents of every queued archive (read only)."""
        self.tv_contents.clear()
        for path in self.queue:
            if not Path(path).is_file():
                continue
            try:
                archive = read_archive(path)
            except (TzarcError, OSError) as exc:
                self._error(exc, path)
                continue
            root = QTreeWidgetItem([Path(path).name])
            self.tv_contents.addTopLevelItem(root)
            for entry in archive.entries:
                root.addChild(QTreeWidgetItem([entry.name]))
            root.setExpanded(True)

    # -- actions --------------------------------------------------------------
    def on_extract(self) -> None:
        """Extract every queued archive, as the Extract TZarc button did."""
        for path in self.queue:
            if not Path(path).is_file():
                continue
            try:
                archive = read_archive(path)
                archive.extract(default_extract_dir(path))
            except (TzarcError, OSError) as exc:
                self._error(exc, path)
                continue
        self._info("Finished extracting files")

    def on_create(self) -> None:
        """Archive every queued folder, as the Create TZarc button did.

        The compressed v2 checkbox switches the output to version 2.
        """
        version = V2 if self.chk_v2.isChecked() else V1
        for path in self.queue:
            if Path(path).is_file():
                continue
            try:
                archive = create_archive(path, version=version)
                archive.write(str(path) + ".tzarc", version=version)
            except (TzarcError, OSError) as exc:
                self._error(exc, path)
                continue
        self._info("Finished creating archives")

    # -- drag and drop --------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.load_paths(paths)

    # -- messages -------------------------------------------------------------
    def _error(self, exc: Exception, path: str) -> None:
        QMessageBox.critical(self, "Error", f"{path}\n{exc}")

    def _info(self, text: str) -> None:
        QMessageBox.information(self, "Ready", text)


def run_gui(paths: list[str] | None = None) -> int:
    """Launch the GUI. Returns the process exit code."""
    app = QApplication(sys.argv[:1])
    icon = _window_icon()
    if icon:
        app.setWindowIcon(icon)
    window = TzarcWindow(paths)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``tzarchiver-gui`` script."""
    if argv is None:
        argv = sys.argv[1:]
    return run_gui(argv)


if __name__ == "__main__":
    sys.exit(run_gui())
