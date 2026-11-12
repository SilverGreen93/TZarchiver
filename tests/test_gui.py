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

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

from tzarchiver.gui import (  # noqa: E402
    APP_TITLE,
    CREATE_TAB,
    EXTRACT_TAB,
    PLACEHOLDER_CREATE,
    PLACEHOLDER_EXTRACT,
    TzarcWindow,
)
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


def test_window_is_resizable_and_starts_portrait_at_the_minimum(window):
    assert window.size() == window.minimumSize() == QSize(380, 480)
    assert window.minimumSize() != window.maximumSize()


def test_two_tabs_host_the_two_queues(window):
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Extract", "Create"]
    assert window.tabs.widget(EXTRACT_TAB) is window.tv_extract
    assert window.tabs.widget(CREATE_TAB).isAncestorOf(window.tv_create)


def test_v2_checkbox_lives_on_the_create_tab_only(window):
    assert window.tabs.widget(CREATE_TAB).isAncestorOf(window.chk_v2)
    assert not window.tabs.widget(EXTRACT_TAB).isAncestorOf(window.chk_v2)


def test_the_current_tabs_button_is_the_one_shown(window):
    assert window.btn_extract.isVisibleTo(window)
    assert not window.btn_create.isVisibleTo(window)
    window.tabs.setCurrentIndex(CREATE_TAB)
    assert window.btn_create.isVisibleTo(window)
    assert not window.btn_extract.isVisibleTo(window)


def test_action_buttons_share_one_width_and_a_short_height(window):
    sizes = {b.minimumSize() for b in (window.btn_extract, window.btn_create, window.btn_clear)}
    assert len(sizes) == 1
    assert next(iter(sizes)).height() == 23


def test_action_buttons_follow_their_queue(window):
    assert not window.btn_extract.isEnabled()
    assert not window.btn_create.isEnabled()
    window.load_paths([str(FOLDER_ARCHIVE)])
    assert window.btn_extract.isEnabled()
    assert not window.btn_create.isEnabled()
    window.tabs.setCurrentIndex(EXTRACT_TAB)
    window.on_clear()
    assert not window.btn_extract.isEnabled()


# ---------------------------------------------------------------------------
# placeholders
# ---------------------------------------------------------------------------

def test_empty_trees_carry_the_drag_hint(window):
    for tree, text in ((window.tv_extract, PLACEHOLDER_EXTRACT), (window.tv_create, PLACEHOLDER_CREATE)):
        assert tree.topLevelItemCount() == 1
        item = tree.topLevelItem(0)
        assert item.text(0) == text
        assert item.isDisabled()


def test_the_hint_disappears_when_the_first_path_arrives(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    item = window.tv_extract.topLevelItem(0)
    assert item.text(0).startswith(FOLDER_ARCHIVE.name)
    assert not item.isDisabled()


# ---------------------------------------------------------------------------
# queue
# ---------------------------------------------------------------------------

def test_dropped_files_land_on_the_extract_tab(window):
    window.load_paths([str(FOLDER_ARCHIVE), str(V2_ARCHIVE)])
    assert window.extract_files == [str(FOLDER_ARCHIVE), str(V2_ARCHIVE)]
    assert window.create_dirs == []
    assert window.tabs.currentIndex() == EXTRACT_TAB
    assert window.tv_extract.topLevelItemCount() == 2
    assert window.tv_extract.topLevelItem(0).text(0) == f"{FOLDER_ARCHIVE.name} (v1)"


def test_dropped_folders_land_on_the_create_tab(window):
    window.load_paths([str(FOLDER)])
    assert window.create_dirs == [str(FOLDER)]
    assert window.extract_files == []
    assert window.tabs.currentIndex() == CREATE_TAB


def test_constructor_seeds_the_queue(qapp):
    win = TzarcWindow([str(FOLDER)])
    assert win.create_dirs == [str(FOLDER)]


def test_queued_archives_show_their_contents(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    root = window.tv_extract.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "config.chump",
        "folder/fisier.txt",
    ]


def test_queued_folders_show_their_files(window):
    window.load_paths([str(FOLDER)])
    root = window.tv_create.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "config.chump",
        "folder/fisier.txt",
    ]


def test_mixed_drops_fill_both_trees_and_pick_the_busier_tab(window):
    window.load_paths([str(FOLDER_ARCHIVE), str(FOLDER), str(FIXTURES)])
    assert window.tv_extract.topLevelItemCount() == 1
    assert window.tv_create.topLevelItemCount() == 2
    assert window.tabs.currentIndex() == CREATE_TAB


def test_queued_archives_show_their_version(window):
    window.load_paths([str(FOLDER_ARCHIVE), str(V2_ARCHIVE)])
    assert window.tv_extract.topLevelItem(0).text(0) == f"{FOLDER_ARCHIVE.name} (v1)"
    assert window.tv_extract.topLevelItem(1).text(0) == f"{V2_ARCHIVE.name} (v2)"


def test_bad_archives_are_reported_but_stay_listed(window, dialogs):
    junk = Path(__file__).parent / "conftest.py"
    window.load_paths([str(junk)])
    assert window.tv_extract.topLevelItemCount() == 1
    assert window.tv_extract.topLevelItem(0).text(0) == junk.name  # no version, it never parsed
    assert window.tv_extract.topLevelItem(0).childCount() == 0
    assert [kind for kind, _ in dialogs] == ["error"]


def test_the_same_path_dropped_twice_is_queued_once(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    window.load_paths([str(FOLDER_ARCHIVE)])
    assert window.extract_files == [str(FOLDER_ARCHIVE)]
    assert window.tv_extract.topLevelItemCount() == 1
    window.load_paths([str(FOLDER), str(FOLDER)])  # duplicates within one drop too
    assert window.create_dirs == [str(FOLDER)]
    assert window.tv_create.topLevelItemCount() == 1


def test_duplicate_detection_compares_the_whole_path(window, tmp_path):
    # same basename, different folders: both must be queued
    sibling = tmp_path / "copy"
    sibling.mkdir()
    other = sibling / FOLDER.name
    other.mkdir()
    window.load_paths([str(FOLDER)])
    window.load_paths([str(other)])
    assert window.create_dirs == [str(FOLDER), str(other)]
    # same path, different spelling: case and separators must count as once
    spelled = str(FOLDER).replace("\\", "/").lower()
    assert spelled != str(FOLDER)
    window.load_paths([spelled])
    assert window.create_dirs == [str(FOLDER), str(other)]
    assert window.tv_create.topLevelItemCount() == 2


def test_clear_allows_the_same_path_to_be_queued_again(window):
    window.load_paths([str(FOLDER)])
    window.on_clear()
    window.load_paths([str(FOLDER)])
    assert window.create_dirs == [str(FOLDER)]


def test_clear_empties_only_the_current_tab(window):
    window.load_paths([str(FOLDER_ARCHIVE)])
    window.load_paths([str(FOLDER)])
    window.on_clear()  # create tab is current
    assert window.create_dirs == []
    assert window.tv_create.topLevelItem(0).text(0) == PLACEHOLDER_CREATE
    assert window.extract_files == [str(FOLDER_ARCHIVE)]
    assert window.tv_extract.topLevelItemCount() == 1


# ---------------------------------------------------------------------------
# extract / create actions
# ---------------------------------------------------------------------------

def test_extract_all_unpacks_every_queued_archive(window, dialogs, tmp_path):
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


def test_create_all_archives_every_queued_folder(window, dialogs, tmp_path):
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


def test_each_button_only_touches_its_own_tab(window, dialogs, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    window.on_extract()  # the extract queue is empty
    assert not (tmp_path / (source.name + ".tzarc")).exists()


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
    assert [Path(p) for p in window.extract_files] == [FOLDER_ARCHIVE]
    assert window.tv_extract.topLevelItemCount() == 1


def test_dropping_a_folder_switches_to_the_create_tab(window):
    event = _FakeDrop([str(FOLDER)])
    window.dropEvent(event)
    assert window.tabs.currentIndex() == CREATE_TAB
    assert window.tv_create.topLevelItemCount() == 1


# ---------------------------------------------------------------------------
# footer
# ---------------------------------------------------------------------------

def test_footer_link_shares_the_copyright_row(window, qapp):
    window.show()
    qapp.processEvents()
    found = [w for w in window.findChildren(QLabel) if "GitHub" in w.text()]
    assert found, "no GitHub link label in the footer"
    link = found[0]
    assert "GitHub" in link.text()
    assert 'href="https://github.com/SilverGreen93/TZarchiver"' in link.text()
    credit = next(w for w in window.findChildren(QLabel) if "©" in w.text())
    # same footer row: credit at the left, link at the right, same y
    assert credit.y() == link.y() and credit.x() < link.x()
