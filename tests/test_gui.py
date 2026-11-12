"""Tests for the PyQt6 GUI.

These run offscreen (no window appears); message boxes are replaced so no
dialog can block the test run.  Everything is skipped when PyQt6 is missing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from tzarchiver.gui import APP_TITLE, HINT, TzarcWindow  # noqa: E402
from tzarchiver.tzarc import V1, V2, read_archive  # noqa: E402

FIXTURES = Path(__file__).parent / "test_files"
FOLDER = FIXTURES / "folder"
FOLDER_ARCHIVE = FIXTURES / "folder v1.tzarc"
V2_ARCHIVE = FIXTURES / "kuid 173000 100413 v2.tzarc"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dialogs(monkeypatch):
    """Collect the messages the window would have shown instead of showing them."""
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("info", text))),
    )
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(("error", text))),
    )
    return shown


@pytest.fixture
def window(qapp):
    win = TzarcWindow()
    yield win


# ---------------------------------------------------------------------------
# window chrome
# ---------------------------------------------------------------------------

def test_window_title_carries_the_version(window):
    assert window.windowTitle() == APP_TITLE


def test_window_is_fixed_sized_at_least_the_original(window):
    size = window.size()
    assert size.width() >= 567 and size.height() >= 315
    assert window.minimumSize() == window.maximumSize()


def test_hint_labels_the_two_kinds_of_drop(window):
    labels = [w.text() for w in window.findChildren(QLabel)]
    assert HINT in labels


# ---------------------------------------------------------------------------
# queue
# ---------------------------------------------------------------------------

def test_paths_are_queued_and_listed(window):
    window.load_paths([str(FOLDER_ARCHIVE), str(V2_ARCHIVE)])
    assert window.queue == [str(FOLDER_ARCHIVE), str(V2_ARCHIVE)]
    assert window.lst_archives.count() == 2
    assert window.lst_archives.item(0).text() == FOLDER_ARCHIVE.name


def test_constructor_seeds_the_queue(qapp):
    win = TzarcWindow([str(FOLDER_ARCHIVE)])
    assert win.lst_archives.count() == 1


def test_queued_archives_show_their_contents(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    tree = window.tv_contents
    assert tree.topLevelItemCount() == 1
    root = tree.topLevelItem(0)
    assert root.text(0) == FOLDER_ARCHIVE.name
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "config.chump",
        "folder/fisier.txt",
    ]


def test_folders_are_queued_without_listing(window):
    window.load_paths([str(FOLDER)])
    assert window.tv_contents.topLevelItemCount() == 0


def test_remove_takes_the_selected_row(window):
    window.load_paths([str(FOLDER_ARCHIVE), str(V2_ARCHIVE)])
    window.lst_archives.setCurrentRow(0)
    window.on_remove()
    assert window.queue == [str(V2_ARCHIVE)]
    assert window.lst_archives.count() == 1
    assert window.tv_contents.topLevelItemCount() == 1


def test_remove_without_a_selection_does_nothing(window):
    window.on_remove()
    assert window.queue == []


def test_clear_empties_everything(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    window.on_clear()
    assert window.queue == []
    assert window.lst_archives.count() == 0
    assert window.tv_contents.topLevelItemCount() == 0


# ---------------------------------------------------------------------------
# extract / create actions
# ---------------------------------------------------------------------------

def test_extract_button_unpacks_every_queued_archive(window, dialogs, tmp_path, capsys):
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    window.load_paths([str(archive)])
    window.on_extract()
    made = tmp_path / archive.stem
    assert (made / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()
    assert (made / "folder" / "fisier.txt").read_bytes() == b"abcdabcdabcd"
    assert ("info", "Finished extracting files") in dialogs


def test_extract_reports_bad_archives_and_carries_on(window, dialogs, tmp_path):
    junk = tmp_path / "junk.tzarc"
    junk.write_bytes(b"not an archive")
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    window.load_paths([str(junk), str(archive)])
    window.on_extract()
    kinds = [kind for kind, _ in dialogs]
    assert dialogs[-1] == ("info", "Finished extracting files")
    assert kinds.count("error") == 2  # once while listing, once while extracting
    assert (tmp_path / archive.stem / "config.chump").is_file()


def test_create_button_archives_every_queued_folder(window, dialogs, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    window.on_create()
    made = source.with_suffix(".tzarc")
    assert made.is_file()
    archive = read_archive(made)
    assert archive.version == V1
    assert archive.names() == ["config.chump", "folder/fisier.txt"]
    assert ("info", "Finished creating archives") in dialogs


def test_v2_checkbox_makes_compressed_archives(window, dialogs, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.chk_v2.setChecked(True)
    window.load_paths([str(source)])
    window.on_create()
    archive = read_archive(source.with_suffix(".tzarc"))
    assert archive.version == V2
    assert archive.read("config.chump") == (FOLDER / "config.chump").read_bytes()


def test_create_skips_queued_files(window, dialogs, tmp_path):
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    window.load_paths([str(archive)])
    window.on_create()
    assert not (tmp_path / (FOLDER_ARCHIVE.name + ".tzarc")).exists()
    assert ("info", "Finished creating archives") in dialogs


# ---------------------------------------------------------------------------
# drag and drop
# ---------------------------------------------------------------------------

class _FakeMime:
    def __init__(self, urls):
        self._urls = urls

    def hasUrls(self):
        return True

    def urls(self):
        return self._urls


class _FakeDrop:
    def __init__(self, paths):
        from PyQt6.QtCore import QUrl

        self._mime = _FakeMime([QUrl.fromLocalFile(p) for p in paths])
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True


def test_dropping_paths_queues_them(window):
    event = _FakeDrop([str(FOLDER_ARCHIVE)])
    window.dragEnterEvent(event)
    assert event.accepted
    window.dropEvent(event)
    # QUrl normalises separators, so compare as paths
    assert [Path(p) for p in window.queue] == [FOLDER_ARCHIVE]
    assert window.lst_archives.count() == 1
