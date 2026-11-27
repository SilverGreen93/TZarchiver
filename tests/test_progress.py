"""Tests for the progress and cancel seam of the archive layer.

A long extract or create run reports through an ``ArchiveTask``: how big the
stretch it is starting is, how much of it is down, and whether it may carry on.
These tests read those reports back and check what is left on disk when the
task says stop; the window that turns them into a progress bar is covered in
``test_gui.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from ja_builder import build_ja, sample_members  # noqa: E402

from tzarchiver.archive import Cancelled, open_archive  # noqa: E402
from tzarchiver.tzarc import V1, V2, Archive, Entry, create_archive  # noqa: E402


class Recorder:
    """An ``ArchiveTask`` that writes down everything it is told.

    ``stop_after_bytes`` stands in for the user's Cancel press: the task says no
    as soon as that much work has gone by, which is how a run is stopped between
    two files or in the middle of writing one big file out.
    """

    def __init__(self, stop_after_bytes: int | None = None):
        self.plans: list[int] = []
        self.names: list[str] = []
        self.done = 0
        self.stop_after_bytes = stop_after_bytes

    # -- the reports ------------------------------------------------------
    def plan(self, total: int) -> None:
        self.plans.append(total)

    def starting(self, name: str) -> None:
        self.names.append(name)

    def work(self, count: int) -> None:
        self.done += count

    # -- the veto ---------------------------------------------------------
    def should_continue(self) -> bool:
        return self.stop_after_bytes is None or self.done < self.stop_after_bytes


@pytest.fixture
def tz_file(tmp_path):
    """A three file v1 archive with sizes this module knows exactly."""
    archive = Archive(
        V1,
        [Entry("one.txt", 4), Entry("two.txt", 6), Entry("three.txt", 3)],
        [b"aaaa", b"bbbbbb", b"ccc"],
    )
    return archive.write(tmp_path / "three.tzarc")


@pytest.fixture
def ja_file(tmp_path):
    """A built-from-the-spec .ja file with four members of assorted encodings."""
    path = tmp_path / "Data.ja"
    path.write_bytes(build_ja(sample_members()))
    return path


# ---------------------------------------------------------------------------
# what a run reports
# ---------------------------------------------------------------------------

def test_extracting_names_every_file_and_counts_its_bytes(tz_file, tmp_path):
    recorder = Recorder()
    open_archive(tz_file).extract(tmp_path / "out", recorder)
    assert recorder.names == ["one.txt", "two.txt", "three.txt"]
    assert recorder.plans == [13]  # one bar for the whole archive
    assert recorder.done == 13


def test_extracting_one_file_reports_only_that_file(tz_file, tmp_path):
    recorder = Recorder()
    open_archive(tz_file).extract_entry("two.txt", tmp_path / "out", recorder)
    assert recorder.names == ["two.txt"]
    assert recorder.done == 6


def test_a_compressed_archive_reports_the_bytes_it_expands(tz_file, tmp_path):
    """Version 2 stores blocks, but progress still adds up to the file size."""
    source = open_archive(tz_file)
    repacked = Archive(V2, source.entries, (source.read(name) for name in source.names()))
    target = repacked.write(tmp_path / "three v2.tzarc", version=V2)

    recorder = Recorder()
    open_archive(target).extract(tmp_path / "out", recorder)
    assert recorder.names == ["one.txt", "two.txt", "three.txt"]
    assert recorder.done == 13


def test_a_ja_extract_reports_the_expanded_sizes(ja_file, tmp_path):
    archive = open_archive(ja_file)
    recorder = Recorder()
    archive.extract(tmp_path / "out", recorder)
    assert recorder.names == list(archive.names())
    expanded = sum(entry.size for entry in archive.entries)
    assert recorder.plans == [expanded]  # the sizes are known from the index
    assert recorder.done == expanded


def test_writing_an_archive_reports_the_bytes_it_puts_on_disk(tz_file, tmp_path):
    archive = open_archive(tz_file)
    source = Archive(V1, archive.entries, (archive.read(n) for n in archive.names()))
    recorder = Recorder()
    target = source.write(tmp_path / "copy.tzarc", task=recorder)
    assert recorder.plans == [target.stat().st_size]
    assert recorder.done == target.stat().st_size
    assert recorder.names == ["copy.tzarc"]


def test_creating_from_a_folder_reports_the_packing_and_the_write(tmp_path):
    folder = tmp_path / "content"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_bytes(b"x" * 500)
    (folder / "sub" / "b.bin").write_bytes(b"y" * 2500)

    recorder = Recorder()
    archive = create_archive(folder, version=V2, task=recorder)
    target = archive.write(tmp_path / "content.tzarc", version=V2, task=recorder)

    assert archive.names() == ["a.txt", "sub/b.bin"]
    assert recorder.names == ["a.txt", "sub/b.bin", "content.tzarc"]
    assert recorder.plans[0] == 3000  # reading the folder in
    assert recorder.plans[-1] == target.stat().st_size  # putting the archive on disk
    assert recorder.done == sum(recorder.plans)  # every phase reported what it planned


# ---------------------------------------------------------------------------
# what a cancel leaves behind
# ---------------------------------------------------------------------------

def test_cancelling_before_the_first_file_writes_nothing(tz_file, tmp_path):
    recorder = Recorder(stop_after_bytes=0)
    dest = tmp_path / "out"
    with pytest.raises(Cancelled):
        open_archive(tz_file).extract(dest, recorder)
    assert recorder.names == []
    assert not any(dest.iterdir())  # not even an empty file for the first entry


def test_cancelling_half_way_keeps_the_files_already_written(tz_file, tmp_path):
    recorder = Recorder(stop_after_bytes=4)  # one 4 byte file fits, the next does not
    dest = tmp_path / "out"
    with pytest.raises(Cancelled):
        open_archive(tz_file).extract(dest, recorder)
    assert (dest / "one.txt").read_bytes() == b"aaaa"
    assert not (dest / "two.txt").exists()
    assert not (dest / "three.txt").exists()


def test_a_cancel_lands_inside_one_large_file(tmp_path):
    """A member bigger than a block is interruptible between blocks."""
    contents = bytes(range(256)) * 1200  # ~300 KB, and not all one byte
    archive = Archive(V1, [Entry("big.bin", len(contents))], [contents])
    source = archive.write(tmp_path / "big.tzarc")

    recorder = Recorder(stop_after_bytes=100_000)
    dest = tmp_path / "out"
    with pytest.raises(Cancelled):
        open_archive(source).extract(dest, recorder)

    written = (dest / "big.bin").stat().st_size
    assert 0 < written < len(contents)
    assert (dest / "big.bin").read_bytes() == contents[:written]


def test_a_cancel_lands_inside_a_compressed_ja_member(tmp_path):
    """A CFIL member is expanded block by block, so it can be stopped inside."""
    from ja_builder import build_ja, member

    contents = bytes(range(256)) * 400  # 100 KB: four copied blocks
    path = tmp_path / "Big.ja"
    path.write_bytes(build_ja([member("huge.bin", contents, "copy")]))

    recorder = Recorder(stop_after_bytes=len(contents) // 3)
    dest = tmp_path / "out"
    with pytest.raises(Cancelled):
        open_archive(path).extract_entry("huge.bin", dest, recorder)

    written = (dest / "huge.bin").stat().st_size
    assert 0 < written < len(contents)
    assert (dest / "huge.bin").read_bytes() == contents[:written]
    assert recorder.names == ["huge.bin"]


def test_cancelling_a_create_leaves_no_archive_behind(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(6):
        (folder / f"{index}.bin").write_bytes(bytes([index]) * 1000)

    recorder = Recorder(stop_after_bytes=2000)  # two of the six files are read
    with pytest.raises(Cancelled):
        create_archive(folder, task=recorder)
    assert len(recorder.names) == 2
    assert not (tmp_path / "many.tzarc").exists()


def test_a_stopped_task_is_refused_before_anything_is_written(tz_file, tmp_path):
    """Asking twice costs nothing: the check happens before the packing starts."""
    archive = open_archive(tz_file)
    source = Archive(V1, archive.entries, (archive.read(n) for n in archive.names()))
    recorder = Recorder(stop_after_bytes=0)
    target = tmp_path / "never.tzarc"
    with pytest.raises(Cancelled):
        source.write(target, task=recorder)
    assert recorder.plans == []
    assert not target.exists()


def test_working_without_a_task_is_unchanged(tz_file, tmp_path):
    """The default remains a plain run: every parameter is optional."""
    archive = open_archive(tz_file)
    assert archive.extract(tmp_path / "out") == tmp_path / "out"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "one.txt",
        "three.txt",
        "two.txt",
    ]
