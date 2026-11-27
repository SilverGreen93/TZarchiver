"""PyQt6 GUI for TZarchiver.

A resizable portrait window with a tabbed queue: the Extract tab lists the
tzarc and ja files dropped on the window and the Create tab the folders to
archive, each expanded into a real folder/file tree.  The Extract all /
Extract all to... and Create all / Create all in... buttons for the current
tab and Clear list sit below the tabs.  Right-clicking any entry in the
Extract tree offers "Extract to...", which unpacks that one file, folder or
whole archive into a chosen destination;
right-clicking a queued folder in the Create tree offers "Create in...", which
writes its archive into a chosen destination.  Both menus can also "Remove" a
queued archive or folder from its list.  A Filter box under the tabs hides,
letter by letter, every list row whose name misses the typed text, keeping
matching entries and their parents.
The compressed v2 checkbox belongs to the Create tab only and keeps
its state from one run to the next.
Extracting and creating happen on a background thread, so a built-in archive
of a gigabyte never leaves the window unresponsive: while a job runs, a strip
under the buttons names the file being written, shows a progress bar for it and
offers Cancel, and the queue itself is out of reach until the job ends.
"""

from __future__ import annotations

import json
import os
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .archive import ArchiveError, ArchiveTask, Cancelled, default_extract_dir, open_archive
from .tzarc import V1, V2, create_archive

__all__ = ["TzarcWindow", "run_gui"]

_ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets"

APP_TITLE = f"TZarchiver {__version__}"
GITHUB_URL = "https://github.com/SilverGreen93/TZarchiver"
ICON_FILE = "175.ico"
PLACEHOLDER_EXTRACT = "Drag & drop tzarc or ja files here"
PLACEHOLDER_CREATE = "Drag & drop folders here"

EXTRACT_TAB, CREATE_TAB = 0, 1

# what a tree row stands for, kept in the row's UserRole data
ARCHIVE_ENTRY, FOLDER_ENTRY, FILE_ENTRY = "archive", "folder", "file"
# the create tree's top-level rows are queued folders on disk
QUEUED_FOLDER_ENTRY = "queued folder"

# the two kinds of work the background job does
EXTRACT_OP, CREATE_OP = "extract", "create"

# what the GUI carries over from one run to the next, and where it keeps it
SETTINGS_APP = "TZarchiver"
SETTINGS_FILE = "settings.json"
KEY_V2 = "create/compressed_v2"


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


def _lookup_key(path: str) -> str:
    """One comparable spelling for one path, for duplicate drop detection.

    normpath folds ".\\a\\..\\b" style segments and normcase makes the result
    case- and separator-insensitive on Windows, so the same folder dropped via
    Explorer and typed by hand counts once.
    """
    return os.path.normcase(os.path.normpath(path))


def _settings_dir() -> Path:
    """The per-user folder the settings file lives in.

    %APPDATA%\\TZarchiver on Windows, ~/.config/TZarchiver on Linux
    (XDG_CONFIG_HOME when set) - next to the user's other app settings, so the
    file can be read or deleted by hand and travels with the user profile.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base or os.path.expanduser("~")) / SETTINGS_APP


def _settings_path() -> Path:
    """The settings file itself: <settings dir>/settings.json."""
    return _settings_dir() / SETTINGS_FILE


def _load_settings() -> dict:
    """The stored settings, or an empty dict when there is nothing usable yet.

    A missing, unreadable or malformed file is not worth a dialog over: the GUI
    starts from its defaults and the next write replaces the broken file.
    """
    try:
        with _settings_path().open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_settings(values: dict) -> None:
    """Write the settings back out, creating the folder when it is missing."""
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2)
            handle.write("\n")
    except OSError:
        pass  # a read-only or full profile must not stop the app


@dataclass(frozen=True)
class _Operation:
    """One queued item, settled into what the background job has to do.

    Everything here was decided on the GUI thread - destination picked,
    overwrite question answered - so the job never needs the window.  ``path``
    is the archive to unpack or the folder to archive and ``target`` the file
    or folder that gets written; ``dest`` and ``value`` only matter when one
    folder or file inside an archive was asked for.
    """

    mode: str  # EXTRACT_OP or CREATE_OP
    path: str
    kind: str  # ARCHIVE_ENTRY, FOLDER_ENTRY, FILE_ENTRY or QUEUED_FOLDER_ENTRY
    value: str
    dest: str
    target: str
    version: int = V1


class _ArchiveJob(QThread, ArchiveTask):
    """The extract/create work of one button press, off the GUI thread.

    Everything slow happens in this thread - opening an archive, expanding its
    compressed members, writing files, packing a folder - which is what keeps
    the window answering the desktop while a gigabyte of built-in content is
    being unpacked.  Only plain values travel back, as signals: the size of
    the stretch being worked on, how many bytes of it are done, and what went
    wrong.  Questions (which folder, overwrite?) were settled before the
    thread started, so it never touches a widget.

    Being the ArchiveTask its own work reports through keeps both halves of
    the reporting together.  The counts are taken in the worker thread, so
    they can only be handed over as a signal, and only when the bar would
    visibly move; the cancel request is Qt's own interruption flag, asked
    before every file and every block handed to the disk.
    """

    #: what is being worked on and how many bytes that stretch is worth
    phase = pyqtSignal(str, int)
    #: bytes done so far, and the file being worked on right now
    step = pyqtSignal(int, str)
    #: the source that could not be handled, and why
    trouble = pyqtSignal(str, str)
    #: the work is over, whether it finished, failed or was cancelled
    ended = pyqtSignal()

    #: shortest gap between two progress signals: often enough to watch a bar
    #: fill, rare enough that a block loop cannot bury the event queue
    TICK_MS = 100

    def __init__(self, operations: list, summary: str) -> None:
        super().__init__()
        self.operations = operations
        #: what the window says when everything went through
        self.summary = summary
        self.total = 0
        self.done = 0
        self.current = ""
        self.label = ""
        self.cancelled = False
        self._stamp = 0.0
        self._reported = True

    # -- the work ---------------------------------------------------------
    def run(self) -> None:
        """Go through the queue, then tell the window it may have its buttons back."""
        try:
            for op in self.operations:
                if self.isInterruptionRequested():
                    self.cancelled = True
                    break
                try:
                    self._run(op)
                except Cancelled:
                    self.cancelled = True
                    break
                except (ArchiveError, OSError) as exc:
                    self.trouble.emit(op.path, str(exc))
        finally:
            self.ended.emit()

    def _run(self, op: _Operation) -> None:
        """One queued item: the archive call that does it passes itself as the task."""
        self.current = ""
        if op.mode == CREATE_OP:
            self.label = f"Creating {Path(op.target).name}"
            archive = create_archive(op.path, version=op.version, task=self)
            archive.write(op.target, version=op.version, task=self)
            return
        archive = open_archive(op.path)
        name = Path(op.path).name
        if op.kind == FOLDER_ENTRY:
            self.label = f"Extracting folder {op.value} from {name}"
            archive.extract_folder(op.value, op.dest, self)
        elif op.kind == FILE_ENTRY:
            self.label = f"Extracting {op.value} from {name}"
            archive.extract_entry(op.value, op.dest, self)
        else:
            self.label = f"Extracting {name}"
            archive.extract(op.target, self)

    # -- reporting (this is the ArchiveTask the work above reports through) --
    def plan(self, total: int) -> None:
        self.total = total
        self.done = 0
        self._stamp = time.monotonic()
        self._reported = False
        self.phase.emit(self.label, total)

    def starting(self, name: str) -> None:
        self.current = name

    def work(self, count: int) -> None:
        """Count the bytes, and move the bar often enough to watch, not constantly."""
        self.done += count
        now = time.monotonic()
        first = not self._reported  # the first bytes of a stretch always show
        if first or self.done >= self.total or (now - self._stamp) * 1000 >= self.TICK_MS:
            self._reported = True
            self._stamp = now
            self.step.emit(self.done, self.current)

    def should_continue(self) -> bool:
        return not self.isInterruptionRequested()


class TzarcWindow(QWidget):
    def __init__(self, paths: list[str] | None = None) -> None:
        super().__init__()
        self.extract_files: list[str] = []
        self.create_dirs: list[str] = []
        self._seen_files: set[str] = set()
        self._seen_dirs: set[str] = set()
        #: the job currently running in its own thread, None when idle
        self._job: _ArchiveJob | None = None
        #: what went wrong during the running job, told about once it is over
        self._job_trouble: list[str] = []
        #: the strip's left-hand text, kept so each update can add the file name
        self._job_label = ""
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
        self.tv_extract.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tv_extract.customContextMenuRequested.connect(self._show_extract_menu)
        self.tabs.addTab(self.tv_extract, "Extract")

        self.tv_create = self._make_tree(PLACEHOLDER_CREATE)
        self.tv_create.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tv_create.customContextMenuRequested.connect(self._show_create_menu)
        self.chk_v2 = QCheckBox("Create compressed v2 archives (TRS22+)")
        self.chk_v2.setChecked(self._remembered_v2())
        self.chk_v2.toggled.connect(self._remember_v2)
        create_tab = QWidget()
        create_layout = QVBoxLayout(create_tab)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.addWidget(self.tv_create, 1)
        create_layout.addWidget(self.chk_v2)
        self.tabs.addTab(create_tab, "Create")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

        # one filter box serves both trees and applies on every keystroke
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setClearButtonEnabled(True)
        self.edit_filter.setPlaceholderText("filter by partial name")
        self.edit_filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.edit_filter, 1)
        outer.addLayout(filter_row)

        # action row below the tabs; only the current tab's buttons are shown
        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.btn_extract = QPushButton("Extract all")
        self.btn_extract_to = QPushButton("Extract all to...")
        self.btn_create = QPushButton("Create all")
        self.btn_create_in = QPushButton("Create all in...")
        self.btn_clear = QPushButton("Clear list")
        buttons = (self.btn_extract, self.btn_extract_to, self.btn_create, self.btn_create_in, self.btn_clear)
        width = max(button.sizeHint().width() for button in buttons)
        for button in buttons:
            button.setMinimumSize(width, 23)
        actions.addWidget(self.btn_extract)
        actions.addWidget(self.btn_extract_to)
        actions.addWidget(self.btn_create)
        actions.addWidget(self.btn_create_in)
        actions.addStretch(1)
        actions.addWidget(self.btn_clear)
        outer.addLayout(actions)

        # while a job runs: the file being worked on, a bar for it and a way out
        self.job_panel = QWidget()
        panel = QVBoxLayout(self.job_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(3)
        self.progress_name = QLabel("")
        panel.addWidget(self.progress_name)
        bar_row = QHBoxLayout()
        bar_row.setSpacing(4)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        bar_row.addWidget(self.progress, 1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumSize(width, 23)
        self.btn_cancel.clicked.connect(self.on_cancel)
        bar_row.addWidget(self.btn_cancel)
        panel.addLayout(bar_row)
        self.job_panel.setVisible(False)
        outer.addWidget(self.job_panel)

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
        self.btn_extract_to.clicked.connect(self.on_extract_all_to)
        self.btn_create.clicked.connect(self.on_create)
        self.btn_create_in.clicked.connect(self.on_create_all_in)
        self.btn_clear.clicked.connect(self.on_clear)

        self._on_tab_changed(self.tabs.currentIndex())
        self._update_buttons()
        self.setMinimumSize(380, 480)
        self.resize(self.minimumSize())  # portrait, at the minimum, on startup

    @staticmethod
    def _make_tree(placeholder: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        # Qt asks its style how much room a level needs and that answer is wide
        # for this window: measured 20 px under the windowsvista and fusion
        # styles, 30 px under windows11.  Halving it (before anything else
        # measures the tree, since a style cannot change the room afterwards)
        # keeps deep archive paths on screen and still leaves room for the
        # branch mark, the smallest halved answer measured being 10 px.
        tree.setIndentation(tree.indentation() // 2)
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

    # -- filter -----------------------------------------------------------------
    def _apply_filter(self, text: str = "") -> None:
        """Hide list rows whose name misses ``text``, letter-per-keystroke.

        A row stays when its own name contains the text (whole subtree kept)
        or when any descendant does; parents kept only for their matching
        children expand so those stay reachable.  An empty filter shows all;
        the drag hint is never filtered.
        """
        needle = text.casefold()
        for tree in (self.tv_extract, self.tv_create):
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                if item.isDisabled():
                    item.setHidden(False)  # the hint is not part of the list
                elif not needle:
                    self._set_visible(item, True)
                else:
                    self._filter_node(item, needle)

    def _filter_node(self, node: QTreeWidgetItem, needle: str) -> bool:
        """Show ``node`` if it or any descendant matches ``needle``; report it."""
        if needle in node.text(0).casefold():
            if node.childCount():
                node.setExpanded(True)
            self._set_visible(node, True)
            return True
        # every child is filtered first: any() must not short-circuit the rest
        child_visible = [self._filter_node(node.child(i), needle) for i in range(node.childCount())]
        visible = any(child_visible)
        node.setHidden(not visible)
        if visible and node.childCount():
            node.setExpanded(True)  # keep the path to the match open
        return visible

    def _set_visible(self, node: QTreeWidgetItem, visible: bool) -> None:
        """Set ``visible`` on ``node`` and everything below it."""
        node.setHidden(not visible)
        for i in range(node.childCount()):
            self._set_visible(node.child(i), visible)

    def _on_tab_changed(self, index: int) -> None:
        self.btn_extract.setVisible(index == EXTRACT_TAB)
        self.btn_extract_to.setVisible(index == EXTRACT_TAB)
        self.btn_create.setVisible(index == CREATE_TAB)
        self.btn_create_in.setVisible(index == CREATE_TAB)

    def _update_buttons(self) -> None:
        """Keep the action buttons in step with the two queues.

        While a job runs the queues cannot be worked on twice, so every action
        button is off regardless of what is queued.
        """
        busy = self._job is not None
        self.btn_extract.setEnabled(bool(self.extract_files) and not busy)
        self.btn_extract_to.setEnabled(bool(self.extract_files) and not busy)
        self.btn_create.setEnabled(bool(self.create_dirs) and not busy)
        self.btn_create_in.setEnabled(bool(self.create_dirs) and not busy)

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
        key = _lookup_key(path)
        if key in self._seen_files:
            return  # the exact same file is already queued
        self._seen_files.add(key)
        self._drop_placeholder(self.tv_extract)
        self.extract_files.append(path)
        self._update_buttons()
        root = QTreeWidgetItem([Path(path).name])
        root.setData(0, Qt.ItemDataRole.UserRole, (ARCHIVE_ENTRY, path))
        self.tv_extract.addTopLevelItem(root)
        try:
            archive = open_archive(path)
        except (ArchiveError, OSError) as exc:
            self._error(exc, path)
        else:
            root.setText(0, f"{Path(path).name} ({archive.format_label})")  # v1/v2 or ja 1.2
            self._add_path_nodes(root, (entry.name for entry in archive.entries))
        root.setExpanded(True)
        self._apply_filter(self.edit_filter.text())  # a running filter covers it too

    @staticmethod
    def _add_path_nodes(root: QTreeWidgetItem, names) -> None:
        """Show slash-separated ``names`` under ``root`` as a real tree.

        Every folder part gets one node that all entries below it share, so a
        nested name like "summer/winter/x.txt" reads as three levels instead of
        one long row.
        """
        folders: dict[str, QTreeWidgetItem] = {}
        for name in names:
            parts = name.split("/")
            parent = root
            prefix = ""
            for part in parts[:-1]:
                prefix = f"{prefix}/{part}" if prefix else part
                node = folders.get(prefix)
                if node is None:
                    node = QTreeWidgetItem([part])
                    node.setData(0, Qt.ItemDataRole.UserRole, (FOLDER_ENTRY, prefix))
                    parent.addChild(node)
                    folders[prefix] = node
                parent = node
            leaf = QTreeWidgetItem([parts[-1]])
            leaf.setData(0, Qt.ItemDataRole.UserRole, (FILE_ENTRY, name))
            parent.addChild(leaf)

    def _add_create_folder(self, path: str) -> None:
        key = _lookup_key(path)
        if key in self._seen_dirs:
            return  # the exact same folder is already queued
        self._seen_dirs.add(key)
        self._drop_placeholder(self.tv_create)
        self.create_dirs.append(path)
        self._update_buttons()
        root = QTreeWidgetItem([Path(path).name])
        root.setData(0, Qt.ItemDataRole.UserRole, (QUEUED_FOLDER_ENTRY, path))
        self.tv_create.addTopLevelItem(root)
        base = Path(path)
        # folders on disk hold the same tree as an archive: nested paths become
        # nested rows; empty folders are not archived, so they are not listed
        names = [
            child.relative_to(base).as_posix() for child in sorted(base.rglob("*")) if child.is_file()
        ]
        self._add_path_nodes(root, names)
        root.setExpanded(True)
        self._apply_filter(self.edit_filter.text())  # a running filter covers it too

    # -- actions --------------------------------------------------------------
    def on_extract(self) -> None:
        """Extract every queued archive beside itself, as the Extract all button does."""
        self._extract_queue(None)

    def on_extract_all_to(self) -> None:
        """Extract every queued archive into a destination folder the user picks.

        Each archive lands in a folder named after it, like the context menu.
        """
        dest = QFileDialog.getExistingDirectory(self, "Extract all to...")
        if not dest:
            return  # dialog cancelled: leave everything alone
        self._extract_queue(Path(dest))

    def _extract_queue(self, dest: Path | None) -> None:
        """Unpack every queued archive into ``dest``, or beside itself when None.

        Extraction folders that already exist get an overwrite question first;
        Cancel stops the whole run.  Whatever survives the questions is handed
        to the background job.
        """
        if self._job is not None:
            return  # a job is already writing: the buttons are off, but be safe
        multiple = len(self.extract_files) > 1
        mode = "ask"
        operations = []
        for path in self.extract_files:
            if not Path(path).is_file():
                continue
            target = default_extract_dir(path) if dest is None else dest / Path(path).stem
            if target.exists():
                choice = self._overwrite_choice(target, multiple, mode)
                if choice == "cancel":
                    return
                if choice in ("all", "none"):
                    mode = choice
                if choice in ("no", "none"):
                    continue
            operations.append(_Operation(EXTRACT_OP, path, ARCHIVE_ENTRY, "", "", str(target)))
        self._start_job(operations, "Finished extracting files")

    # -- the job in progress ----------------------------------------------------
    def _start_job(self, operations: list, summary: str) -> None:
        """Hand the settled work to its own thread and start following it.

        ``summary`` is what the window says once everything went through.
        """
        self._job_trouble = []
        self._job_label = ""
        job = _ArchiveJob(operations, summary)
        job.phase.connect(self._on_phase)
        job.step.connect(self._on_step)
        job.trouble.connect(self._on_trouble)
        job.ended.connect(self._on_job_ended)
        self._job = job
        self.job_panel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_clear.setEnabled(False)
        self._update_buttons()
        job.start()

    def on_cancel(self) -> None:
        """Ask the running job to stop: at the next file or block written.

        The files it already wrote are left where they are, as they are when an
        archive turns out to be damaged part way through.
        """
        if self._job is not None:
            self._job.requestInterruption()
            self.btn_cancel.setEnabled(False)  # one press is enough

    def _on_phase(self, label: str, total: int) -> None:
        """A new stretch of work: the bar learns its size, the strip its words."""
        self._job_label = label
        self.progress_name.setText(label)
        self.progress_name.setToolTip(label)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)

    def _on_step(self, done: int, name: str) -> None:
        """More bytes are down: move the bar and name the file they came from."""
        self.progress.setValue(min(done, self.progress.maximum()))
        line = f"{self._job_label}  -  {name}" if name else self._job_label
        self.progress_name.setToolTip(line)
        self.progress_name.setText(self._elided(line))

    def _elided(self, text: str) -> str:
        """Shorten ``text`` to what fits the strip, keeping both ends of it."""
        width = self.progress_name.width()
        if width <= 0:
            return text
        return self.progress_name.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, width)

    def _on_trouble(self, path: str, message: str) -> None:
        """Remember one failure.

        Showing it here would put a modal box in front of a job that is still
        running, so everything waits for the end of the run.
        """
        self._job_trouble.append(f"{path}\n{message}")

    def _on_job_ended(self) -> None:
        """The thread is done: put the window back and say what happened."""
        job, trouble = self._job, self._job_trouble
        self._job = None
        self.job_panel.setVisible(False)
        self.progress_name.setText("")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.btn_clear.setEnabled(True)
        self._update_buttons()
        if trouble:
            self._report_trouble(trouble)
        if job is not None and job.cancelled:
            self._info("Cancelled - what was already written is kept")
        elif job is not None:
            self._info(job.summary)

    def _report_trouble(self, trouble: list) -> None:
        """One box for everything that went wrong during the job."""
        shown = trouble[:5]
        rest = len(trouble) - len(shown)
        text = "\n\n".join(shown) + (f"\n\nand {rest} more" if rest else "")
        QMessageBox.critical(self, "Error", text)

    def _show_extract_menu(self, pos) -> None:
        """Right-click menu for the extract tree: Extract to... on any entry,
        Remove on the queued archive rows."""
        if self._job is not None:
            return  # the queue waits for the running job
        item = self.tv_extract.itemAt(pos)
        if item is None or not item.data(0, Qt.ItemDataRole.UserRole):
            return  # empty space or the drag hint: nothing to do here
        menu = QMenu(self)
        extract_action = menu.addAction("Extract to...")
        remove_action = menu.addAction("Remove") if item.parent() is None else None
        chosen = menu.exec(self.tv_extract.viewport().mapToGlobal(pos))
        if chosen is extract_action:
            self.on_extract_to(item)
        elif chosen is remove_action:
            self.on_remove_extract(item)

    def on_extract_to(self, item: QTreeWidgetItem) -> None:
        """Extract one right-clicked entry to a destination folder the user picks.

        An archive row unpacks the whole archive into a new folder named after
        it, a folder row recreates that folder (with everything below it) in the
        destination, and a file row just writes the file itself there.  When
        that file or folder is already there, the user is asked before it is
        overwritten; saying no leaves it untouched.
        """
        kind, value = item.data(0, Qt.ItemDataRole.UserRole)
        top = item
        while top.parent() is not None:
            top = top.parent()
        archive_path = top.data(0, Qt.ItemDataRole.UserRole)[1]
        dest = QFileDialog.getExistingDirectory(self, "Extract to...", str(Path(archive_path).parent))
        if not dest:
            return  # dialog cancelled: leave everything alone
        if kind == ARCHIVE_ENTRY:
            target = Path(dest) / Path(archive_path).stem
        elif kind == FOLDER_ENTRY:
            target = Path(dest) / Path(value.replace("\\", "/")).name
        else:
            target = Path(dest) / value.replace("\\", "/").split("/")[-1]
        if target.exists() and self._ask_overwrite(target) != QMessageBox.StandardButton.Yes:
            return
        self._start_job(
            [_Operation(EXTRACT_OP, archive_path, kind, value, str(dest), str(target))],
            f"Finished extracting from {Path(archive_path).name}",
        )

    def _ask_overwrite(self, target: Path, multiple: bool = False):
        """Ask whether ``target``, which already exists, may be overwritten.

        A plain Yes/No box by default; when the action covers a longer queue
        it also offers Yes to All, No to All and Cancel so one click can
        settle the rest of the run.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Already exists")
        box.setText(f"{target.name} already exists.\nOverwrite it?")
        box.setIcon(QMessageBox.Icon.Question)
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        if multiple:
            buttons |= (
                QMessageBox.StandardButton.YesAll
                | QMessageBox.StandardButton.NoAll
                | QMessageBox.StandardButton.Cancel
            )
        box.setStandardButtons(buttons)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec()

    _OVERWRITE_ANSWERS = {
        QMessageBox.StandardButton.Yes: "yes",
        QMessageBox.StandardButton.No: "no",
        QMessageBox.StandardButton.YesAll: "all",
        QMessageBox.StandardButton.NoAll: "none",
        QMessageBox.StandardButton.Cancel: "cancel",
    }

    def _overwrite_choice(self, target: Path, multiple: bool, mode: str) -> str:
        """Decide about ``target`` for the queue loop.

        ``mode`` carries a previous Yes/No to All ("all"/"none") or asks now.
        Returns yes (overwrite this one), no (skip it), all/none (the new
        standing answer) or cancel (stop the run).
        """
        if mode == "all":
            return "yes"
        if mode == "none":
            return "no"
        return self._OVERWRITE_ANSWERS[self._ask_overwrite(target, multiple)]

    def on_create(self) -> None:
        """Archive every queued folder beside itself, as the Create all button does."""
        self._create_queue(None)

    def on_create_all_in(self) -> None:
        """Archive every queued folder into a destination folder the user picks."""
        dest = QFileDialog.getExistingDirectory(self, "Create all in...")
        if not dest:
            return  # dialog cancelled: leave everything alone
        self._create_queue(Path(dest))

    def _create_queue(self, dest: Path | None) -> None:
        """Write every queued folder's archive into ``dest``, or beside itself.

        The compressed v2 checkbox switches the output to version 2; archives
        that already exist get an overwrite question first, and Cancel stops
        the whole run.  What survives goes to the background job.
        """
        if self._job is not None:
            return  # a job is already writing: the buttons are off, but be safe
        version = V2 if self.chk_v2.isChecked() else V1
        multiple = len(self.create_dirs) > 1
        mode = "ask"
        operations = []
        for path in self.create_dirs:
            target = (
                Path(str(path) + ".tzarc")
                if dest is None
                else dest / (Path(path).name + ".tzarc")
            )
            if target.exists():
                choice = self._overwrite_choice(target, multiple, mode)
                if choice == "cancel":
                    return
                if choice in ("all", "none"):
                    mode = choice
                if choice in ("no", "none"):
                    continue
            operations.append(
                _Operation(CREATE_OP, path, QUEUED_FOLDER_ENTRY, "", "", str(target), version)
            )
        self._start_job(operations, "Finished creating archives")

    def _show_create_menu(self, pos) -> None:
        """Right-click menu for the create tree: Create in... and Remove, on
        the queued folder rows only.

        Only the top-level folder rows get the menu; the folder and file rows
        below them are not archives waiting to be created on their own.
        """
        if self._job is not None:
            return  # the queue waits for the running job
        item = self.tv_create.itemAt(pos)
        if item is None or item.parent() is not None or not item.data(0, Qt.ItemDataRole.UserRole):
            return  # empty space, the drag hint or a contents row: no menu
        menu = QMenu(self)
        create_action = menu.addAction("Create in...")
        remove_action = menu.addAction("Remove")
        chosen = menu.exec(self.tv_create.viewport().mapToGlobal(pos))
        if chosen is create_action:
            self.on_create_in(item)
        elif chosen is remove_action:
            self.on_remove_create(item)

    def on_create_in(self, item: QTreeWidgetItem) -> None:
        """Write <folder>.tzarc for the right-clicked queued folder into a
        destination folder the user picks, honoring the compressed v2 checkbox.

        An archive that already sits there gets an overwrite question first.
        """
        _, folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        dest = QFileDialog.getExistingDirectory(self, "Create in...", str(Path(folder_path).parent))
        if not dest:
            return  # dialog cancelled: leave everything alone
        target = Path(dest) / (Path(folder_path).name + ".tzarc")
        if target.exists() and self._ask_overwrite(target) != QMessageBox.StandardButton.Yes:
            return
        version = V2 if self.chk_v2.isChecked() else V1
        self._start_job(
            [_Operation(CREATE_OP, folder_path, QUEUED_FOLDER_ENTRY, "", "", str(target), version)],
            f"Finished creating archive for {Path(folder_path).name}",
        )

    def on_remove_extract(self, item: QTreeWidgetItem) -> None:
        """Take the right-clicked tzarc out of the extract queue."""
        _, path = item.data(0, Qt.ItemDataRole.UserRole)
        self._remove_row(self.tv_extract, item, self.extract_files, self._seen_files, path, PLACEHOLDER_EXTRACT)

    def on_remove_create(self, item: QTreeWidgetItem) -> None:
        """Take the right-clicked folder out of the create queue."""
        _, path = item.data(0, Qt.ItemDataRole.UserRole)
        self._remove_row(self.tv_create, item, self.create_dirs, self._seen_dirs, path, PLACEHOLDER_CREATE)

    def _remove_row(self, tree, item, paths: list[str], seen: set[str], path: str, placeholder: str) -> None:
        """Common Remove: forget the path, drop its row, show the hint if empty.

        The duplicate-detection key goes too, so the same path can be dropped
        or queued again afterwards.
        """
        if path in paths:
            paths.remove(path)
        seen.discard(_lookup_key(path))
        tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
        if tree.topLevelItemCount() == 0:
            self._reset_placeholder(tree, placeholder)
        self._update_buttons()

    def on_clear(self) -> None:
        """Empty the list of the tab on screen and show its hint again."""
        if self._job is not None:
            return  # the queue waits for the running job
        if self.tabs.currentIndex() == CREATE_TAB:
            self.create_dirs.clear()
            self._seen_dirs.clear()
            self._reset_placeholder(self.tv_create, PLACEHOLDER_CREATE)
        else:
            self.extract_files.clear()
            self._seen_files.clear()
            self._reset_placeholder(self.tv_extract, PLACEHOLDER_EXTRACT)
        self._update_buttons()

    # -- remembered state -----------------------------------------------------
    @staticmethod
    def _remembered_v2() -> bool:
        """The compressed-v2 choice left by the previous run, off on first use."""
        return bool(_load_settings().get(KEY_V2, False))

    @staticmethod
    def _remember_v2(checked: bool) -> None:
        """Store the compressed-v2 choice the moment it changes.

        Saving on every toggle instead of only at close keeps the last choice
        even if the window is killed rather than closed.  Whatever else the
        file already holds is read back first, so it survives this write.
        """
        values = _load_settings()
        values[KEY_V2] = checked
        _save_settings(values)

    # -- drag and drop --------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._job is not None:
            return  # a running job has the queues to itself
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.load_paths(paths)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Closing while a job runs asks first: no thread is left writing files.

        Waiting for the job is safe because it notices the request before its
        next file or block, which is at most one member of the archive away.
        """
        job = self._job
        if job is None:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Still working",
            "An operation is still running.\nStop it and quit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        job.requestInterruption()
        job.wait(30000)
        event.accept()

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
