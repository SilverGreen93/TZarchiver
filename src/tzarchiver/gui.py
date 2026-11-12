"""PyQt6 GUI for TZarchiver.

A resizable portrait window with a tabbed queue: the Extract tab lists the
tzarc files dropped on the window (each expanded with its contents), the
Create tab lists the folders to archive (expanded with their files).  The
Extract all / Create all button for the current tab and Clear list sit below
the tabs.  The compressed v2 checkbox belongs to the Create tab only.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
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
PLACEHOLDER_EXTRACT = "Drag & drop tzarc files here"
PLACEHOLDER_CREATE = "Drag & drop folders here"

EXTRACT_TAB, CREATE_TAB = 0, 1


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
        self.extract_files: list[str] = []
        self.create_dirs: list[str] = []
        self._build()
        self.setAcceptDrops(True)
        if paths:
            self.load_paths(paths)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        self.setWindowTitle(APP_TITLE)
        icon = _window_icon()
        if icon:
            self.setWindowIcon(icon)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 6)
        outer.setSpacing(6)

        # the tabbed queue: one independent tree per tab
        self.tabs = QTabWidget()
        self.tv_extract = self._make_tree(PLACEHOLDER_EXTRACT)
        self.tabs.addTab(self.tv_extract, "Extract")

        self.tv_create = self._make_tree(PLACEHOLDER_CREATE)
        self.chk_v2 = QCheckBox("Create compressed v2 archives")
        create_tab = QWidget()
        create_layout = QVBoxLayout(create_tab)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.addWidget(self.tv_create, 1)
        create_layout.addWidget(self.chk_v2)
        self.tabs.addTab(create_tab, "Create")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

        # action row below the tabs; only the current tab's button is shown
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.btn_extract = QPushButton("Extract all")
        self.btn_create = QPushButton("Create all")
        self.btn_clear = QPushButton("Clear list")
        for button in (self.btn_extract, self.btn_create):
            button.setMinimumSize(105, 46)
        self.btn_clear.setMinimumSize(72, 47)
        actions.addWidget(self.btn_extract)
        actions.addWidget(self.btn_create)
        actions.addStretch(1)
        actions.addWidget(self.btn_clear)
        outer.addLayout(actions)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("\u00a9 2026 SilverGreen93"))
        footer.addStretch(1)
        link = QLabel(f'<a href="{GITHUB_URL}">GitHub</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignRight)
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda: webbrowser.open(GITHUB_URL))
        footer.addWidget(link)
        outer.addLayout(footer)

        self.btn_extract.clicked.connect(self.on_extract)
        self.btn_create.clicked.connect(self.on_create)
        self.btn_clear.clicked.connect(self.on_clear)

        self._on_tab_changed(self.tabs.currentIndex())
        self.setMinimumSize(380, 480)
        self.resize(430, 640)  # portrait on startup

    @staticmethod
    def _make_tree(placeholder: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        TzarcWindow._reset_placeholder(tree, placeholder)
        return tree

    # -- placeholders ---------------------------------------------------------
    @staticmethod
    def _reset_placeholder(tree: QTreeWidget, text: str) -> None:
        """Show the greyed drag hint as the tree's only item."""
        tree.clear()
        item = QTreeWidgetItem([text])
        item.setDisabled(True)
        tree.addTopLevelItem(item)

    @staticmethod
    def _drop_placeholder(tree: QTreeWidget) -> None:
        """Remove the drag hint as soon as a real entry arrives."""
        if tree.topLevelItemCount() == 1 and tree.topLevelItem(0).isDisabled():
            tree.takeTopLevelItem(0)

    def _on_tab_changed(self, index: int) -> None:
        self.btn_extract.setVisible(index == EXTRACT_TAB)
        self.btn_create.setVisible(index == CREATE_TAB)

    # -- queue ------------------------------------------------------------------
    def load_paths(self, paths: list[str]) -> None:
        """Sort dropped paths into their tab and switch to the busiest one."""
        files = [str(path) for path in paths if Path(path).is_file()]
        folders = [str(path) for path in paths if Path(path).is_dir()]
        for path in files:
            self._add_extract_file(path)
        for path in folders:
            self._add_create_folder(path)
        if len(folders) > len(files):
            self.tabs.setCurrentIndex(CREATE_TAB)
        elif files or folders:
            self.tabs.setCurrentIndex(EXTRACT_TAB)

    def _add_extract_file(self, path: str) -> None:
        self._drop_placeholder(self.tv_extract)
        self.extract_files.append(path)
        root = QTreeWidgetItem([Path(path).name])
        self.tv_extract.addTopLevelItem(root)
        try:
            archive = read_archive(path)
        except (TzarcError, OSError) as exc:
            self._error(exc, path)
        else:
            for entry in archive.entries:
                root.addChild(QTreeWidgetItem([entry.name]))
        root.setExpanded(True)

    def _add_create_folder(self, path: str) -> None:
        self._drop_placeholder(self.tv_create)
        self.create_dirs.append(path)
        root = QTreeWidgetItem([Path(path).name])
        self.tv_create.addTopLevelItem(root)
        base = Path(path)
        for child in sorted(base.rglob("*")):
            if child.is_file():
                root.addChild(QTreeWidgetItem([child.relative_to(base).as_posix()]))
        root.setExpanded(True)

    # -- actions --------------------------------------------------------------
    def on_extract(self) -> None:
        """Extract every queued archive, as the Extract all button does."""
        for path in self.extract_files:
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
        """Archive every queued folder, as the Create all button does.

        The compressed v2 checkbox switches the output to version 2.
        """
        version = V2 if self.chk_v2.isChecked() else V1
        for path in self.create_dirs:
            try:
                archive = create_archive(path, version=version)
                archive.write(str(path) + ".tzarc", version=version)
            except (TzarcError, OSError) as exc:
                self._error(exc, path)
                continue
        self._info("Finished creating archives")

    def on_clear(self) -> None:
        """Empty the list of the tab on screen and show its hint again."""
        if self.tabs.currentIndex() == CREATE_TAB:
            self.create_dirs.clear()
            self._reset_placeholder(self.tv_create, PLACEHOLDER_CREATE)
        else:
            self.extract_files.clear()
            self._reset_placeholder(self.tv_extract, PLACEHOLDER_EXTRACT)

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
