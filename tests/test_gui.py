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

from PyQt6.QtCore import QPoint, QSize, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QLabel, QMenu, QMessageBox  # noqa: E402

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
        "folder",
    ]
    folder = root.child(1)
    assert [folder.child(i).text(0) for i in range(folder.childCount())] == ["fisier.txt"]


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


# ---------------------------------------------------------------------------
# extract tab context menu (Extract to...)
# ---------------------------------------------------------------------------

def _copy_archive(tmp_path):
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    return archive


def test_only_the_extract_tree_has_a_context_menu(window):
    assert window.tv_extract.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert window.tv_create.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu


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


def _patch_question(monkeypatch, answer, asked: list):
    """Replace the yes/no box with one that records the question and answers it."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda parent, title, text, *a, **k: asked.append(text) or answer),
    )


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

    monkeypatch.setattr(QMessageBox, "question", staticmethod(no_question))
    window.on_extract_to(window.tv_extract.topLevelItem(0).child(1))  # the folder row
    assert (dest / "folder" / "fisier.txt").is_file()


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
    assert opened == [["Extract to..."]]
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
