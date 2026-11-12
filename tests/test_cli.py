"""Tests for tzarchiver.cli: argument handling, listing, extracting, creating."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tzarchiver.cli import describe, main, run_cli
from tzarchiver.tzarc import V1, V2, read_archive

FIXTURES = Path(__file__).parent / "test_files"
FOLDER = FIXTURES / "folder"
FOLDER_ARCHIVE = FIXTURES / "folder v1.tzarc"
V2_ARCHIVE = FIXTURES / "kuid 173000 100413 v2.tzarc"


# ---------------------------------------------------------------------------
# entry-mode selection
# ---------------------------------------------------------------------------

def test_no_arguments_launch_the_gui(monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    seen = []
    monkeypatch.setattr("tzarchiver.gui.run_gui", lambda paths=None: seen.append(paths) or 0)
    assert main([]) == 0
    assert seen == [[]]


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--extract" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# list mode
# ---------------------------------------------------------------------------

def test_lists_a_v1_archive(capsys):
    assert main([str(FOLDER_ARCHIVE)]) == 0
    out = capsys.readouterr().out
    assert "folder v1.tzarc (v1, 2 files)" in out
    assert "config.chump  [83 bytes]" in out
    assert "folder/fisier.txt  [12 bytes]" in out


def test_lists_a_v2_archive(capsys):
    assert main([str(V2_ARCHIVE)]) == 0
    out = capsys.readouterr().out
    assert "kuid 173000 100413 v2.tzarc (v2, 12 files)" in out
    assert "$screenshot$.jpg" in out


def test_describe_lists_names_and_sizes():
    text = describe(FOLDER_ARCHIVE)
    lines = text.splitlines()
    assert lines[0] == "folder v1.tzarc (v1, 2 files)"
    assert lines[1].strip().startswith("config.chump")


def test_missing_file_is_reported(tmp_path, capsys):
    assert main([str(tmp_path / "nope.tzarc")]) == 1
    assert "Error:" in capsys.readouterr().err


def test_non_archive_is_reported(tmp_path, capsys):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"plain file, not a tzarc")
    assert main([str(junk)]) == 1
    assert "File format not supported" in capsys.readouterr().err


def test_one_bad_path_does_not_stop_the_others(tmp_path, capsys):
    assert main([str(tmp_path / "nope.tzarc"), str(FOLDER_ARCHIVE)]) == 1
    assert "folder v1.tzarc (v1, 2 files)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# extract mode
# ---------------------------------------------------------------------------

def test_extract_to_out_dir(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["-x", "-o", str(out), str(FOLDER_ARCHIVE)]) == 0
    assert (out / "config.chump").read_bytes() == (FOLDER / "config.chump").read_bytes()
    assert (out / "folder" / "fisier.txt").read_bytes() == b"abcdabcdabcd"
    assert f"extracted to {out}" in capsys.readouterr().out


def test_extract_defaults_to_a_folder_named_after_the_archive(tmp_path, capsys):
    archive = tmp_path / FOLDER_ARCHIVE.name
    archive.write_bytes(FOLDER_ARCHIVE.read_bytes())
    assert main(["--extract", str(archive)]) == 0
    made = tmp_path / FOLDER_ARCHIVE.stem
    assert sorted(p.name for p in made.iterdir()) == ["config.chump", "folder"]
    assert "extracted to" in capsys.readouterr().out


def test_extract_a_v2_archive(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["-x", "-o", str(out), str(V2_ARCHIVE)]) == 0
    assert (out / "config.chump").is_file()
    assert (out / "w8.im").is_file()


# ---------------------------------------------------------------------------
# create mode
# ---------------------------------------------------------------------------

def test_creating_a_folder_writes_it_next_to_the_source(tmp_path, capsys):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    assert main([str(source)]) == 0
    archive = source.with_suffix(".tzarc")
    assert archive.is_file()
    read = read_archive(archive)
    assert read.version == V1
    assert read.names() == ["config.chump", "folder/fisier.txt"]
    assert read.read("folder/fisier.txt") == (source / "folder" / "fisier.txt").read_bytes()
    assert f"created {archive} (2 files, v1)" in capsys.readouterr().out


def test_creating_with_v2_flag_still_reads_back(tmp_path, capsys):
    source = tmp_path / "folder"
    shutil.copytree(FOLDER, source)
    assert main([str(source), "--v2"]) == 0
    archive = source.with_suffix(".tzarc")
    read = read_archive(archive)
    assert read.version == V2
    assert read.read("config.chump") == (source / "config.chump").read_bytes()
    assert "(2 files, v2)" in capsys.readouterr().out


def test_creating_several_folders_is_allowed(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    shutil.copytree(FOLDER, one)
    shutil.copytree(FOLDER, two)
    assert run_cli([str(one), str(two)])
    assert one.with_suffix(".tzarc").is_file()
    assert two.with_suffix(".tzarc").is_file()


def test_run_cli_reports_failure_when_any_path_fails(tmp_path):
    assert not run_cli([str(tmp_path / "nope")])
