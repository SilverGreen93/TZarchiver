"""Tests for the PyQt6 GUI.

These run offscreen (no window appears); message boxes are replaced so no
dialog can block the test run.  Everything is skipped when PyQt6 is missing.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QTreeWidget,
)

from tzarchiver import gui  # noqa: E402
from tzarchiver.gui import (  # noqa: E402
    APP_TITLE,
    CREATE_TAB,
    EXTRACT_TAB,
    KEY_V2,
    PLACEHOLDER_CREATE,
    PLACEHOLDER_EXTRACT,
    SETTINGS_FILE,
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
def window(qapp, scratch_settings):
    win = TzarcWindow()
    yield win


@pytest.fixture(autouse=True)
def scratch_settings(tmp_path, monkeypatch):
    """Point the remembered-state file at a scratch file for the whole test.

    Without this the suite would read whatever the developer last ticked and
    write its own choices into the real per-user settings file.  The fixture
    hands back a reader for the same file so a test can play the previous run.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def read():
        return gui._load_settings()

    return read


# ---------------------------------------------------------------------------
# window chrome
# ---------------------------------------------------------------------------

def test_window_title_carries_the_version(window):
    assert window.windowTitle() == APP_TITLE


def test_window_is_resizable_and_starts_portrait_at_the_minimum(window):
    assert window.size() == window.minimumSize()
    assert window.minimumSize() != window.maximumSize()
    # the button row sets the floor for the width, the explicit 480 for the height
    assert window.minimumSize().width() >= 380 and window.minimumSize().height() == 480


def test_two_tabs_host_the_two_queues(window):
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ["Extract", "Create"]
    assert window.tabs.widget(EXTRACT_TAB) is window.tv_extract
    assert window.tabs.widget(CREATE_TAB).isAncestorOf(window.tv_create)


def test_the_trees_indent_by_half_of_what_qt_asks_for(window):
    """Qt's style answer (20 or 30 px) is wide here, so both trees halve it."""
    default = QTreeWidget().indentation()
    assert default // 2 >= 10  # still room for the branch mark
    assert window.tv_extract.indentation() == default // 2
    assert window.tv_create.indentation() == default // 2


def test_v2_checkbox_lives_on_the_create_tab_only(window):
    assert window.tabs.widget(CREATE_TAB).isAncestorOf(window.chk_v2)
    assert not window.tabs.widget(EXTRACT_TAB).isAncestorOf(window.chk_v2)


def test_the_current_tabs_buttons_are_the_ones_shown(window):
    extract = (window.btn_extract, window.btn_extract_to)
    create = (window.btn_create, window.btn_create_in)
    for button in extract:
        assert button.isVisibleTo(window)
    for button in create:
        assert not button.isVisibleTo(window)
    window.tabs.setCurrentIndex(CREATE_TAB)
    for button in create:
        assert button.isVisibleTo(window)
    for button in extract:
        assert not button.isVisibleTo(window)


def test_action_buttons_share_one_width_and_a_short_height(window):
    buttons = (window.btn_extract, window.btn_extract_to, window.btn_create, window.btn_create_in, window.btn_clear)
    sizes = {b.minimumSize() for b in buttons}
    assert len(sizes) == 1
    assert next(iter(sizes)).height() == 23


def test_action_buttons_follow_their_queue(window):
    assert not window.btn_extract.isEnabled()
    assert not window.btn_extract_to.isEnabled()
    assert not window.btn_create.isEnabled()
    assert not window.btn_create_in.isEnabled()
    window.load_paths([str(FOLDER_ARCHIVE)])
    assert window.btn_extract.isEnabled()
    assert window.btn_extract_to.isEnabled()
    assert not window.btn_create.isEnabled()
    window.tabs.setCurrentIndex(EXTRACT_TAB)
    window.on_clear()
    assert not window.btn_extract.isEnabled()
    assert not window.btn_extract_to.isEnabled()


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
        "folder",
    ]
    folder = root.child(1)
    assert [folder.child(i).text(0) for i in range(folder.childCount())] == ["fisier.txt"]


def test_queued_folders_show_their_files_as_a_tree(window):
    window.load_paths([str(FOLDER)])
    root = window.tv_create.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "config.chump",
        "folder",
    ]
    folder = root.child(1)
    assert [folder.child(i).text(0) for i in range(folder.childCount())] == ["fisier.txt"]


def test_nested_folder_levels_get_one_row_each(window, tmp_path):
    source = tmp_path / "deep"
    deepest = source / "a" / "b" / "c"
    deepest.mkdir(parents=True)
    (deepest / "x.txt").write_text("x", encoding="utf-8")
    (source / "top.txt").write_text("x", encoding="utf-8")
    window.load_paths([str(source)])
    root = window.tv_create.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == ["a", "top.txt"]
    deepest = root.child(0).child(0).child(0)  # a -> b -> c
    assert deepest.text(0) == "c"
    assert [deepest.child(i).text(0) for i in range(deepest.childCount())] == ["x.txt"]


def test_empty_subfolders_are_not_listed(window, tmp_path):
    # nothing inside them ever reaches the archive, so they are not shown either
    source = tmp_path / "src"
    (source / "empty").mkdir(parents=True)
    (source / "file.txt").write_text("x", encoding="utf-8")
    window.load_paths([str(source)])
    root = window.tv_create.topLevelItem(0)
    assert [root.child(i).text(0) for i in range(root.childCount())] == ["file.txt"]


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


# ---------------------------------------------------------------------------
# Jet Archive (.ja) files in the Extract tab
# ---------------------------------------------------------------------------

def _write_ja(tmp_path):
    from ja_builder import build_ja, sample_members

    path = tmp_path / "Data.ja"
    path.write_bytes(build_ja(sample_members()))
    return path


def test_a_jet_archive_shows_its_version_and_tree(window, tmp_path):
    path = _write_ja(tmp_path)
    window.load_paths([str(path)])
    root = window.tv_extract.topLevelItem(0)
    assert root.text(0) == "Data.ja (ja 1.2)"
    assert [root.child(i).text(0) for i in range(root.childCount())] == [
        "config.chump",
        "sounds",
        "license.txt",
    ]
    sounds = root.child(1)
    assert [sounds.child(i).text(0) for i in range(sounds.childCount())] == ["beep.wav", "loop"]
    assert [sounds.child(1).child(i).text(0) for i in range(sounds.child(1).childCount())] == [
        "beep2.wav"
    ]


def test_extract_all_unpacks_a_jet_archive(window, dialogs, tmp_path):
    from ja_builder import BIG

    path = _write_ja(tmp_path)
    window.load_paths([str(path)])
    window.on_extract()
    made = tmp_path / "Data"
    assert (made / "config.chump").read_bytes() == (
        b"a small file, stored as is\n" * 3
    )
    assert (made / "sounds" / "beep.wav").read_bytes() == BIG
    assert (made / "sounds" / "loop" / "beep2.wav").read_bytes() == BIG
    assert dialogs[-1] == ("info", "Finished extracting files")


def test_extract_to_on_a_jet_archive_folder_recreates_it(window, dialogs, monkeypatch, tmp_path):
    from ja_builder import BIG

    path = _write_ja(tmp_path)
    window.load_paths([str(path)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(1))  # the "sounds" row
    assert (dest / "sounds" / "beep.wav").read_bytes() == BIG
    assert (dest / "sounds" / "loop" / "beep2.wav").read_bytes() == BIG
    assert not (dest / "license.txt").exists()


def test_extract_to_on_a_jet_archive_file_writes_just_that_file(window, dialogs, monkeypatch, tmp_path):
    from ja_builder import SMALL

    path = _write_ja(tmp_path)
    window.load_paths([str(path)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(0))  # config.chump
    assert (dest / "config.chump").read_bytes() == SMALL


def test_a_jet_archive_reports_a_bad_file_once_per_row(window, dialogs, tmp_path):
    junk = tmp_path / "notes.ja"
    junk.write_bytes(b"not an archive at all")
    window.load_paths([str(junk)])
    assert dialogs[0][0] == "error"
    assert "File format not supported" in dialogs[0][1]
    window.on_extract()
    assert dialogs[-1] == ("info", "Finished extracting files")


# ---------------------------------------------------------------------------
# extract tab context menu (Extract to...)
# ---------------------------------------------------------------------------

def _copy_archive(tmp_path):
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    return archive


def _right_click(window, tree, item, monkeypatch, click=None):
    """Right-click the row of ``item`` and report the menu actions it showed.

    ``click`` names the action to pick, if any; a click runs that action.
    """
    window.show()
    qapp = QApplication.instance()
    qapp.processEvents()
    if not tree.visualItemRect(item).isValid():  # the row scrolled out of the narrow view
        tree.setCurrentItem(item)
        qapp.processEvents()
    opened = []

    def fake_exec(menu, pos):
        actions = menu.actions()
        titles = [a.text() for a in actions]
        opened.append(titles)
        if click is not None and click in titles:
            return actions[titles.index(click)]
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    handler = window._show_extract_menu if tree is window.tv_extract else window._show_create_menu
    handler(tree.visualItemRect(item).center())
    return opened[0] if opened else []


def test_both_trees_have_their_own_context_menu(window):
    assert window.tv_extract.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert window.tv_create.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_extract_to_on_the_archive_unpacks_into_a_folder_named_after_it(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_extract_to(window.tv_extract.topLevelItem(0))
    made = dest / archive.stem
    assert (made / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()
    assert (made / "folder" / "fisier.txt").read_bytes() == b"abcdabcdabcd"
    assert ("info", f"Finished extracting from {archive.name}") in dialogs


def test_extract_to_on_a_file_writes_just_that_file(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    root = window.tv_extract.topLevelItem(0)
    window.on_extract_to(root.child(0))  # config.chump
    assert (dest / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()
    assert not (dest / "folder").exists()


def test_extract_to_on_a_nested_file_writes_it_without_its_folders(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    folder = window.tv_extract.topLevelItem(0).child(1)  # the "folder" node
    window.on_extract_to(folder.child(0))  # fisier.txt
    assert (dest / "fisier.txt").read_bytes() == b"abcdabcdabcd"


def test_extract_to_on_a_folder_recreates_it_in_the_destination(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    folder = window.tv_extract.topLevelItem(0).child(1)
    window.on_extract_to(folder)
    assert (dest / "folder" / "fisier.txt").read_bytes() == b"abcdabcdabcd"
    assert not (dest / "config.chump").exists()


def test_extract_to_does_nothing_when_the_dialog_is_cancelled(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    window.on_extract_to(window.tv_extract.topLevelItem(0))
    assert not (tmp_path / archive.stem).exists()
    assert dialogs == []


def _patch_question(monkeypatch, answers, asked: list, boxes: list | None = None):
    """Replace the question box's exec: records question and buttons, answers in order.

    ``answers`` may be one button reused for every ask, or a list, one per ask.
    """
    from itertools import repeat

    pool = iter(answers if isinstance(answers, (list, tuple)) else repeat(answers))

    def fake_exec(box):
        asked.append(box.text())
        if boxes is not None:
            boxes.append(box.standardButtons())
        return next(pool)

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)


def test_extract_to_overwrites_an_existing_file_after_asking(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    (dest).mkdir()
    (dest / "config.chump").write_bytes(b"old bytes")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked: list[str] = []
    _patch_question(monkeypatch, QMessageBox.StandardButton.Yes, asked)
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(0))  # config.chump
    assert asked and "config.chump" in asked[0]
    assert (dest / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()


def test_extract_to_keeps_the_file_when_overwrite_is_refused(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    (dest).mkdir()
    (dest / "config.chump").write_bytes(b"old bytes")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked: list[str] = []
    _patch_question(monkeypatch, QMessageBox.StandardButton.No, asked)
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(0))  # config.chump
    assert asked and "config.chump" in asked[0]
    assert (dest / "config.chump").read_bytes() == b"old bytes"
    assert not (dest / "folder").exists()
    assert dialogs == []


def test_extract_to_overwrites_an_existing_folder_after_asking(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    (dest / archive.stem).mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked: list[str] = []
    _patch_question(monkeypatch, QMessageBox.StandardButton.Yes, asked)
    window.on_extract_to(window.tv_extract.topLevelItem(0))  # the tzarc row
    assert asked and archive.stem in asked[0]
    assert (dest / archive.stem / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()


def test_extract_to_refuses_the_whole_archive_folder_and_stops(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    made = dest / archive.stem
    made.mkdir(parents=True)
    (made / "keep.txt").write_text("mine", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    _patch_question(monkeypatch, QMessageBox.StandardButton.No, [])
    window.on_extract_to(window.tv_extract.topLevelItem(0))  # the tzarc row
    assert sorted(p.name for p in made.iterdir()) == ["keep.txt"]
    assert dialogs == []


def test_extract_to_asks_nothing_when_the_target_is_new(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))

    def no_question(*a, **k):
        raise AssertionError("asked to overwrite when nothing was there")

    monkeypatch.setattr(QMessageBox, "exec", no_question)
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(1))  # the folder row
    assert (dest / "folder" / "fisier.txt").is_file()


# ---------------------------------------------------------------------------
# Extract all / Create all overwrite prompts
# ---------------------------------------------------------------------------

B = QMessageBox.StandardButton


def _copy_two_archives(tmp_path):
    made = []
    for name in ("one", "two"):
        archive = tmp_path / f"{name}.tzarc"
        archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
        made.append(archive)
    return made


def test_extract_all_asks_before_reusing_an_existing_folder(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    (tmp_path / archive.stem).mkdir()
    window.load_paths([str(archive)])
    asked, boxes = [], []
    _patch_question(monkeypatch, B.Yes, asked, boxes)
    window.on_extract()
    assert asked and archive.stem in asked[0]
    assert boxes[0] == B.Yes | B.No  # a one-item queue gets the plain Yes/No box
    assert (tmp_path / archive.stem / "config.chump").is_file()
    assert ("info", "Finished extracting files") in dialogs


def test_extract_all_skips_the_archive_when_answered_no(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    made = tmp_path / archive.stem
    made.mkdir()
    (made / "keep.txt").write_text("mine", encoding="utf-8")
    window.load_paths([str(archive)])
    _patch_question(monkeypatch, B.No, [])
    window.on_extract()
    assert sorted(p.name for p in made.iterdir()) == ["keep.txt"]


def test_extract_all_offers_yes_to_all_once_and_replaces_everything(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    for stem in (a1.stem, a2.stem):
        (tmp_path / stem).mkdir()
    window.load_paths([str(a1), str(a2)])
    asked, boxes = [], []
    _patch_question(monkeypatch, [B.YesAll], asked, boxes)
    window.on_extract()
    assert len(asked) == 1  # Yes to All covers the second archive
    assert boxes[0] == B.Yes | B.No | B.YesAll | B.NoAll | B.Cancel
    assert (tmp_path / a1.stem / "config.chump").is_file()
    assert (tmp_path / a2.stem / "config.chump").is_file()


def test_extract_all_no_to_all_skips_every_existing_folder(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    for stem in (a1.stem, a2.stem):
        (tmp_path / stem).mkdir()
    window.load_paths([str(a1), str(a2)])
    _patch_question(monkeypatch, [B.NoAll], [])
    window.on_extract()
    assert not [p for stem in (a1.stem, a2.stem) for p in (tmp_path / stem).iterdir()]


def test_extract_all_asks_again_per_item_on_plain_yes_or_no(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    for stem in (a1.stem, a2.stem):
        (tmp_path / stem).mkdir()
    window.load_paths([str(a1), str(a2)])
    asked = []
    _patch_question(monkeypatch, [B.Yes, B.No], asked)
    window.on_extract()
    assert len(asked) == 2  # a plain answer only settles this item
    assert (tmp_path / a1.stem / "config.chump").is_file()
    assert not (tmp_path / a2.stem / "config.chump").exists()


def test_extract_all_cancel_stops_the_whole_run(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    for stem in (a1.stem, a2.stem):
        (tmp_path / stem).mkdir()
    window.load_paths([str(a1), str(a2)])
    _patch_question(monkeypatch, [B.Cancel], [])
    window.on_extract()
    assert not [p for stem in (a1.stem, a2.stem) for p in (tmp_path / stem).iterdir()]
    assert dialogs == []  # a cancelled run says nothing more


def test_create_all_asks_before_replacing_an_existing_archive(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    source.with_suffix(".tzarc").write_bytes(b"old archive")
    window.load_paths([str(source)])
    asked = []
    _patch_question(monkeypatch, B.Yes, asked)
    window.on_create()
    assert asked and f"{source.name}.tzarc" in asked[0]
    assert read_archive(source.with_suffix(".tzarc")).names() == ["config.chump", "folder/fisier.txt"]


def test_create_all_keeps_the_archive_when_answered_no(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    made = source.with_suffix(".tzarc")
    made.write_bytes(b"old archive")
    window.load_paths([str(source)])
    _patch_question(monkeypatch, B.No, [])
    window.on_create()
    assert made.read_bytes() == b"old archive"


def test_create_all_yes_to_all_replaces_every_existing_archive(window, dialogs, monkeypatch, tmp_path):
    sources = []
    for name in ("one", "two"):
        source = tmp_path / name
        shutil.copytree(FOLDER, source)
        source.with_suffix(".tzarc").write_bytes(b"old")
        sources.append(source)
    window.load_paths([str(s) for s in sources])
    asked, boxes = [], []
    _patch_question(monkeypatch, [B.YesAll], asked, boxes)
    window.on_create()
    assert len(asked) == 1
    assert boxes[0] == B.Yes | B.No | B.YesAll | B.NoAll | B.Cancel
    for source in sources:
        assert read_archive(source.with_suffix(".tzarc")).names() == ["config.chump", "folder/fisier.txt"]


# ---------------------------------------------------------------------------
# Extract all to... / Create all in... buttons
# ---------------------------------------------------------------------------

def test_extract_all_to_unpacks_every_archive_into_the_chosen_folder(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    window.load_paths([str(a1), str(a2)])
    dest = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_extract_all_to()
    assert (dest / "one" / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()
    assert (dest / "two" / "folder" / "fisier.txt").read_bytes() == b"abcdabcdabcd"
    assert not (tmp_path / "one").exists()  # nothing lands beside the archives
    assert ("info", "Finished extracting files") in dialogs


def test_extract_all_to_does_nothing_when_the_dialog_is_cancelled(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    window.load_paths([str(a1), str(a2)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    window.on_extract_all_to()
    assert not (tmp_path / "one").exists()
    assert dialogs == []


def test_extract_all_to_asks_once_about_existing_targets_with_full_buttons(window, dialogs, monkeypatch, tmp_path):
    a1, a2 = _copy_two_archives(tmp_path)
    dest = tmp_path / "out"
    for name in ("one", "two"):
        (dest / name).mkdir(parents=True)
    window.load_paths([str(a1), str(a2)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked, boxes = [], []
    _patch_question(monkeypatch, [B.YesAll], asked, boxes)
    window.on_extract_all_to()
    assert len(asked) == 1  # Yes to All covers both archives
    assert boxes[0] == B.Yes | B.No | B.YesAll | B.NoAll | B.Cancel
    assert (dest / "one" / "config.chump").is_file()
    assert (dest / "two" / "config.chump").is_file()


def test_extract_all_to_asks_plain_yes_no_for_a_one_item_queue(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    dest = tmp_path / "out"
    (dest / archive.stem).mkdir(parents=True)
    window.load_paths([str(archive)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked, boxes = [], []
    _patch_question(monkeypatch, B.No, asked, boxes)
    window.on_extract_all_to()
    assert boxes[0] == B.Yes | B.No
    assert not (dest / archive.stem / "config.chump").exists()


def test_create_all_to_archives_every_folder_into_the_chosen_folder(window, dialogs, monkeypatch, tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    shutil.copytree(FOLDER, one)
    shutil.copytree(FOLDER, two)
    window.load_paths([str(one), str(two)])
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_create_all_in()
    for name in ("one", "two"):
        made = read_archive(dest / f"{name}.tzarc")
        assert made.names() == ["config.chump", "folder/fisier.txt"]
        assert made.version == V1
    assert not (tmp_path / "one.tzarc").exists()  # nothing lands beside the sources
    assert ("info", "Finished creating archives") in dialogs


def test_create_all_to_honors_the_v2_checkbox(window, dialogs, monkeypatch, tmp_path):
    one = tmp_path / "one"
    shutil.copytree(FOLDER, one)
    window.chk_v2.setChecked(True)
    window.load_paths([str(one)])
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_create_all_in()
    assert read_archive(dest / "one.tzarc").version == V2


def test_create_all_to_does_nothing_when_the_dialog_is_cancelled(window, dialogs, monkeypatch, tmp_path):
    one = tmp_path / "one"
    shutil.copytree(FOLDER, one)
    window.load_paths([str(one)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    window.on_create_all_in()
    assert not (tmp_path / "one.tzarc").exists()
    assert dialogs == []


# ---------------------------------------------------------------------------
# create tab context menu (Create in...)
# ---------------------------------------------------------------------------

def test_only_the_queued_folder_row_gets_the_create_menu(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    window.show()
    qapp = QApplication.instance()
    qapp.processEvents()
    tree = window.tv_create
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    opened = []

    def fake_exec(menu, pos):
        opened.append([a.text() for a in menu.actions()])
        return menu.actions()[0]  # as if Create in... had been clicked

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    rect = tree.visualItemRect(tree.topLevelItem(0))
    assert rect.isValid() and not rect.isNull()
    window._show_create_menu(rect.center())
    assert opened == [["Create in...", "Remove"]]

    def no_menu(*a):
        opened.append("menu over a file row")

    monkeypatch.setattr(QMenu, "exec", no_menu)
    for row in (tree.topLevelItem(0).child(0), tree.topLevelItem(0).child(1)):  # file and folder
        if not tree.visualItemRect(row).isValid():  # the row scrolled out of the narrow view
            tree.setCurrentItem(row)
            qapp.processEvents()
        window._show_create_menu(tree.visualItemRect(row).center())
    assert opened == [["Create in...", "Remove"]]  # the rows below the folder stayed silent


def test_create_in_writes_the_archive_into_the_chosen_folder(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_create_in(window.tv_create.topLevelItem(0))
    made = dest / "folder.tzarc"
    assert read_archive(made).names() == ["config.chump", "folder/fisier.txt"]
    assert read_archive(made).version == V1
    assert not (tmp_path / "folder.tzarc").exists()  # nothing beside the source
    assert ("info", "Finished creating archive for folder") in dialogs


def test_create_in_follows_the_v2_checkbox(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.chk_v2.setChecked(True)
    window.load_paths([str(source)])
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window.on_create_in(window.tv_create.topLevelItem(0))
    assert read_archive(dest / "folder.tzarc").version == V2


def test_create_in_does_nothing_when_the_dialog_is_cancelled(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    window.on_create_in(window.tv_create.topLevelItem(0))
    assert not (tmp_path / "folder.tzarc").exists()
    assert dialogs == []


def test_create_in_asks_before_replacing_an_existing_archive(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    dest = tmp_path / "out"
    dest.mkdir()
    made = dest / "folder.tzarc"
    made.write_bytes(b"old archive")
    window.load_paths([str(source)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked = []
    _patch_question(monkeypatch, B.No, asked)
    window.on_create_in(window.tv_create.topLevelItem(0))
    assert asked and "folder.tzarc" in asked[0]
    assert made.read_bytes() == b"old archive"
    assert dialogs == []


def test_create_in_replaces_the_archive_after_asking(window, dialogs, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "folder.tzarc").write_bytes(b"old archive")
    window.load_paths([str(source)])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    asked = []
    _patch_question(monkeypatch, B.Yes, asked)
    window.on_create_in(window.tv_create.topLevelItem(0))
    assert asked and "folder.tzarc" in asked[0]
    assert read_archive(dest / "folder.tzarc").names() == ["config.chump", "folder/fisier.txt"]


# ---------------------------------------------------------------------------
# Remove from the lists (both context menus)
# ---------------------------------------------------------------------------

def test_remove_offers_itself_only_on_top_level_extract_rows(window, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    tree = window.tv_extract
    assert _right_click(window, tree, tree.topLevelItem(0), monkeypatch) == ["Extract to...", "Remove"]
    child = tree.topLevelItem(0).child(0)
    assert _right_click(window, tree, child, monkeypatch) == ["Extract to..."]  # no Remove below the top


def test_remove_takes_an_archive_out_of_the_extract_queue(window, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    tree = window.tv_extract
    _right_click(window, tree, tree.topLevelItem(0), monkeypatch, click="Remove")
    assert window.extract_files == []
    assert tree.topLevelItem(0).text(0) == PLACEHOLDER_EXTRACT  # the hint is back
    assert tree.topLevelItem(0).isDisabled()
    assert not window.btn_extract.isEnabled()
    window.load_paths([str(archive)])  # the seen-key was forgotten too: requeueable
    assert window.extract_files == [str(archive)]
    assert tree.topLevelItemCount() == 1 and not tree.topLevelItem(0).isDisabled()


def test_remove_keeps_the_other_extract_entries(window, monkeypatch, tmp_path):
    first = tmp_path / "folder v1.tzarc"
    first.write_bytes(FOLDER_ARCHIVE.read_bytes())
    second = tmp_path / "kuid 173000 100413 v2.tzarc"
    second.write_bytes(V2_ARCHIVE.read_bytes())
    window.load_paths([str(first), str(second)])
    tree = window.tv_extract
    _right_click(window, tree, tree.topLevelItem(0), monkeypatch, click="Remove")
    assert window.extract_files == [str(second)]
    assert tree.topLevelItemCount() == 1
    assert tree.topLevelItem(0).text(0) == f"{second.name} (v2)"
    assert window.btn_extract.isEnabled()


def test_remove_takes_a_folder_out_of_the_create_queue(window, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    other = tmp_path / "other"
    shutil.copytree(FOLDER, other)
    window.load_paths([str(source), str(other)])
    tree = window.tv_create
    assert _right_click(window, tree, tree.topLevelItem(0), monkeypatch) == ["Create in...", "Remove"]
    _right_click(window, tree, tree.topLevelItem(0), monkeypatch, click="Remove")
    assert window.create_dirs == [str(other)]
    assert tree.topLevelItemCount() == 1
    assert tree.topLevelItem(0).text(0) == other.name
    assert window.btn_create.isEnabled()
    window.load_paths([str(source)])  # forgetting the seen-key allows it back in
    assert window.create_dirs == [str(other), str(source)]


def test_remove_of_the_last_create_folder_brings_the_hint_back(window, monkeypatch, tmp_path):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.load_paths([str(source)])
    tree = window.tv_create
    _right_click(window, tree, tree.topLevelItem(0), monkeypatch, click="Remove")
    assert window.create_dirs == []
    assert tree.topLevelItem(0).text(0) == PLACEHOLDER_CREATE
    assert tree.topLevelItem(0).isDisabled()
    assert not window.btn_create.isEnabled()


def test_remove_menu_never_opens_over_the_drag_hints(window, monkeypatch):
    assert _right_click(window, window.tv_extract, window.tv_extract.topLevelItem(0), monkeypatch) == []
    assert _right_click(window, window.tv_create, window.tv_create.topLevelItem(0), monkeypatch) == []


# ---------------------------------------------------------------------------
# filter box under the tabs
# ---------------------------------------------------------------------------

def _visible_rows(tree):
    """Shown top-level rows mapped to their shown descendant names."""
    rows = {}
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top.isHidden():
            continue
        shown = []

        def walk(node):
            for j in range(node.childCount()):
                child = node.child(j)
                if not child.isHidden():
                    shown.append(child.text(0))
                    walk(child)

        walk(top)
        rows[top.text(0)] = shown
    return rows


def test_filter_field_sits_between_the_tabs_and_the_buttons(window, qapp):
    window.show()
    qapp.processEvents()
    assert window.tabs.geometry().bottom() <= window.edit_filter.geometry().top()
    assert window.edit_filter.geometry().bottom() <= window.btn_extract.geometry().top()


def test_filter_keeps_matching_files_with_only_their_parents(window, tmp_path):
    one = tmp_path / "kuid123"
    two = tmp_path / "kuid345"
    one.mkdir()
    two.mkdir()
    for name in ("abcd", "mnop"):
        (one / name).write_text("x", encoding="utf-8")
    (two / "qwerty").write_text("x", encoding="utf-8")
    window.load_paths([str(one), str(two)])
    window.edit_filter.setText("m")  # applies letter by letter as the user types
    assert _visible_rows(window.tv_create) == {"kuid123": ["mnop"]}
    window.edit_filter.setText("bc")
    assert _visible_rows(window.tv_create) == {"kuid123": ["abcd"]}
    window.edit_filter.setText("")
    assert _visible_rows(window.tv_create) == {
        "kuid123": ["abcd", "mnop"],
        "kuid345": ["qwerty"],
    }


def test_filter_reveals_matches_inside_collapsed_archive_folders(window, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    root = window.tv_extract.topLevelItem(0)
    folder = root.child(1)
    assert not folder.isExpanded()
    window.edit_filter.setText("fisier")
    assert not folder.isHidden() and folder.isExpanded()  # opened so the match is reachable
    assert root.child(0).isHidden()  # config.chump misses the filter
    assert not folder.child(0).isHidden()


def test_filter_opens_a_queued_folder_down_to_its_match(window, tmp_path):
    source = tmp_path / "kuid123"
    deep = source / "sub" / "deeper"
    deep.mkdir(parents=True)
    (deep / "target.txt").write_text("x", encoding="utf-8")
    (source / "other.txt").write_text("x", encoding="utf-8")
    window.load_paths([str(source)])
    window.edit_filter.setText("target")
    assert _visible_rows(window.tv_create) == {"kuid123": ["sub", "deeper", "target.txt"]}
    root = window.tv_create.topLevelItem(0)
    assert root.child(0).isHidden()  # other.txt misses the filter
    assert root.child(1).isExpanded() and root.child(1).child(0).isExpanded()


def test_filter_ignores_case(window, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    window.edit_filter.setText("CHUMP")
    assert _visible_rows(window.tv_extract) == {f"{archive.name} (v1)": ["config.chump"]}


def test_filter_matching_the_archive_row_keeps_its_whole_listing(window, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    window.edit_filter.setText(archive.name)  # only the top row's name matches
    assert _visible_rows(window.tv_extract) == {
        f"{archive.name} (v1)": ["config.chump", "folder", "fisier.txt"],
    }


def test_the_drag_hint_is_never_filtered(window):
    window.edit_filter.setText("xyz")
    hint = window.tv_extract.topLevelItem(0)
    assert hint.text(0) == PLACEHOLDER_EXTRACT and not hint.isHidden()


def test_drops_while_a_filter_is_active_are_filtered_too(window, tmp_path):
    window.edit_filter.setText("zzz")
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    assert window.tv_extract.topLevelItem(0).isHidden()
    assert window.extract_files == [str(archive)]  # only the view is filtered, not the queue
    window.edit_filter.setText("")
    assert not window.tv_extract.topLevelItem(0).isHidden()


def test_the_right_click_menu_offers_extract_to_and_runs_it(window, dialogs, monkeypatch, tmp_path):
    archive = _copy_archive(tmp_path)
    window.load_paths([str(archive)])
    window.show()
    qapp = QApplication.instance()
    qapp.processEvents()
    dest = tmp_path / "out"
    opened = []

    def fake_exec(menu, pos):
        opened.append([a.text() for a in menu.actions()])
        return menu.actions()[0]  # as if Extract to... had been clicked

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(dest)))
    window._show_extract_menu(QPoint(10, 10))  # over the archive row
    assert opened == [["Extract to...", "Remove"]]
    assert (dest / archive.stem / "config.chump").is_file()


def test_the_right_click_menu_stays_hidden_on_the_drag_hint(window, monkeypatch, qapp):
    window.show()
    qapp.processEvents()

    def fake_exec(menu, pos):
        raise AssertionError("a menu opened over the placeholder")

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    window._show_extract_menu(QPoint(10, 10))  # only the placeholder row is there


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
# remembered state
# ---------------------------------------------------------------------------

def test_the_v2_checkbox_starts_off_when_nothing_was_stored(window):
    assert not window.chk_v2.isChecked()


def test_a_v2_choice_left_by_an_earlier_run_is_restored(qapp, scratch_settings):
    gui._save_settings({KEY_V2: True})
    assert TzarcWindow().chk_v2.isChecked()


def test_a_v2_choice_is_carried_to_the_next_window(window, qapp):
    window.chk_v2.setChecked(True)
    assert TzarcWindow().chk_v2.isChecked()
    window.chk_v2.setChecked(False)  # unticking is remembered too
    assert not TzarcWindow().chk_v2.isChecked()


def test_the_remembered_choice_creates_v2_archives(window, dialogs, tmp_path, qapp):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    window.chk_v2.setChecked(True)
    again = TzarcWindow()  # as if the app had been closed and opened again
    assert again.chk_v2.isChecked()
    again.load_paths([str(source)])
    again.on_create()
    assert read_archive(source.with_suffix(".tzarc")).version == V2


def test_the_choice_is_written_as_soon_as_it_is_ticked(window, qapp, scratch_settings):
    window.chk_v2.setChecked(True)
    assert scratch_settings().get(KEY_V2) is True


def test_the_settings_file_is_plain_json(window, qapp):
    """The file is hand-editable JSON named settings.json under TZarchiver/."""
    window.chk_v2.setChecked(True)
    path = gui._settings_path()
    assert path.name == SETTINGS_FILE and path.parent.name == gui.SETTINGS_APP
    assert json.loads(path.read_text(encoding="utf-8")) == {KEY_V2: True}


def test_a_broken_settings_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    """A half-written file must not stop the GUI; it starts unchecked."""
    folder = tmp_path / gui.SETTINGS_APP
    folder.mkdir()
    (folder / SETTINGS_FILE).write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not TzarcWindow().chk_v2.isChecked()


def test_the_settings_folder_is_created_when_it_is_missing(tmp_path, monkeypatch):
    """First run on a fresh profile: nothing has to exist beforehand."""
    folder = tmp_path / gui.SETTINGS_APP
    monkeypatch.setenv("APPDATA", str(folder.parent))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(folder.parent))
    assert gui._load_settings() == {}
    gui._save_settings({KEY_V2: True})
    assert (folder / SETTINGS_FILE).is_file()


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
