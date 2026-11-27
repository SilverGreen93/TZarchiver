"""Shared plumbing for every archive format TZarchiver opens.

Each format lives in its own module - ``tzarc.py`` for ``*.tzarc`` (see
``tzarc-format.md``) and ``ja.py`` for the Jet Archive ``*.ja`` files (see
``ja-format.md``) - and both build on what is here: one error base, one
directory entry record, safe extraction joins, :class:`ArchiveBase` with the
listing and extracting behaviour they share, and :func:`open_archive`, the one
place that decides which format a dropped file is.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

__all__ = [
    "ArchiveError",
    "ArchiveBase",
    "ArchiveTask",
    "Cancelled",
    "Entry",
    "ReportingFile",
    "open_archive",
    "default_extract_dir",
    "safe_join",
]

#: First four bytes of each supported format, kept here so open_archive can
#: pick without importing both readers; the format modules own the real values.
TZARC_MAGIC = b"TZac"
JA_MAGIC = b"ARCH"

#: Entry names are relative; this matches the rooted forms that must never be
#: written to disk below the extraction folder.
_ABSOLUTE_NAME = re.compile(r"^(?:[A-Za-z]:[/\\]|[/\\])")


class ArchiveError(Exception):
    """Raised for anything that is not a readable archive file.

    Each format subclasses it (``TzarcError``, ``JaError``) so its own code can
    keep catching what it raises while callers that do not care about the
    format catch this one.
    """


@dataclass(frozen=True)
class Entry:
    """One file inside an archive.

    ``name`` uses forward slashes for subfolders, as stored in the archive.
    """

    name: str
    size: int


def default_extract_dir(archive_path: str | Path) -> Path:
    """Folder the original app extracts to: ``<archive dir>/<archive name>``."""
    path = Path(archive_path)
    return path.parent / path.stem


def open_archive(path: str | Path) -> ArchiveBase:
    """Open any supported archive file; its first bytes pick the reader.

    ``TZac`` is a tzarc, ``ARCH`` (the first chunk tag of) a Jet Archive.
    Looking at the file instead of its name also opens a ``.ja`` renamed to
    ``.tzarc`` and reports the real problem for anything else.  Only the header
    is read here: a Jet Archive can hold gigabytes, so its contents are pulled
    out one file at a time by the reader that takes over.
    """
    path = Path(path)
    with path.open("rb") as handle:  # a missing path raises OSError, as before
        magic = handle.read(4)
    if magic == JA_MAGIC:
        from .ja import read_ja  # local: ja.py itself imports this module

        return read_ja(path)
    if magic == TZARC_MAGIC:
        from .tzarc import read_archive  # local for the same reason

        return read_archive(path)
    raise ArchiveError(f"File format not supported for {path}")


class Cancelled(Exception):
    """Raised when a running job's task asks it to stop part way through.

    Whatever was written by then stays on the disk, exactly as it does when an
    archive turns out to be damaged halfway through.
    """


class ArchiveTask:
    """How a running archive job reports itself and hears about cancellation.

    A caller that wants to follow the work - the GUI's progress bar - hands one
    of these to :meth:`ArchiveBase.extract`, :meth:`extract_entry`,
    :meth:`extract_folder`, ``tzarc.create_archive`` and ``tzarc.Archive.write``:

    * ``plan`` says how many bytes this stretch of work is worth, so the bar
      can be sized before any of it happens;
    * ``starting`` names the file being worked on right now;
    * ``work`` counts the bytes as they are read or written;
    * ``should_continue`` is asked before every file and before every block is
      handed to the disk, so a cancel lands inside a single huge member and
      not only between files.

    Everything here does nothing and every archive method takes ``None`` (the
    default) to mean "nobody is watching", which behaves as it always did.
    """

    def plan(self, total: int) -> None:
        """This many bytes of work lie ahead."""

    def starting(self, name: str) -> None:
        """The job is working on this file now."""

    def work(self, count: int) -> None:
        """This many bytes have just been read or written."""

    def should_continue(self) -> bool:
        """False stops the job, raising :class:`Cancelled`."""
        return True

    @staticmethod
    def check(task: "ArchiveTask | None") -> None:
        """Stop the job if ``task`` asks for that; ``None`` keeps it going."""
        if task is not None and not task.should_continue():
            raise Cancelled()


class ReportingFile:
    """A file object that reports every block it is given to a task.

    The archive writers only ever call ``write``, so wrapping the real file
    like this is enough to follow any format's extraction - including one that
    streams a member out in blocks - without the format knowing the difference.
    """

    #: how much goes to the disk at a time while a task is watching: big enough
    #: to stay fast, small enough to be worth checking against a cancel request
    BLOCK = 256 * 1024

    def __init__(self, target: BinaryIO, task: ArchiveTask) -> None:
        self._target = target
        self._task = task

    def write(self, data: bytes) -> None:
        """Hand ``data`` to the real file, one block at a time.

        The block split is what lets a cancel land inside a member that is
        hundreds of megabytes long: a format that hands over the whole file in
        one call still gets asked before every piece of it goes to the disk.
        """
        for start in range(0, len(data), self.BLOCK):
            ArchiveTask.check(self._task)
            block = data[start : start + self.BLOCK]
            self._target.write(block)
            self._task.work(len(block))


class ArchiveBase:
    """The listing and extracting behaviour every format has in common.

    A format brings ``entries`` (records with ``name`` and ``size``),
    ``format_label``, its own ``error`` type and :meth:`write_contents`, which
    is the only part that depends on how the bytes are stored.  That is what
    lets the GUI's "Extract to..." and the CLI's ``-x`` work the same on a
    plain tzarc and on a compressed Jet Archive.
    """

    #: the error type this format reports problems with
    error = ArchiveError
    #: how the format is named in listings and in the GUI tree, e.g. "v2"
    format_label = ""
    #: every file in the archive, as records with ``name`` and ``size``; each
    #: format fills this in when it reads its own index
    entries: list

    # -- listing ----------------------------------------------------------
    def names(self) -> list[str]:
        return [entry.name for entry in self.entries]

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, name: str) -> bool:
        return any(entry.name == name for entry in self.entries)

    # -- contents ---------------------------------------------------------
    def read(self, name: str) -> bytes:
        """Return the whole contents of ``name``.

        Formats that hold their contents in memory replace this; the ones that
        read from disk get it by collecting what :meth:`write_contents` writes.
        """
        buffer = io.BytesIO()
        self.write_contents(name, buffer)
        return buffer.getvalue()

    def write_contents(self, name: str, target: BinaryIO) -> None:
        """Copy the contents of ``name`` into the open file ``target``.

        Raises this format's error type when ``name`` is not in the archive.
        """
        raise NotImplementedError

    # -- extracting -------------------------------------------------------
    def extract(self, dest_dir: str | Path | None = None, task: ArchiveTask | None = None) -> Path:
        """Write every file below ``dest_dir``, creating subfolders as needed.

        Forward slashes in entry names become real directories.  ``dest_dir``
        is required: :func:`default_extract_dir` supplies the name the original
        apps used.  ``task``, when given, is told how big the job is before it
        starts and then hears about every file and every block written.
        """
        if dest_dir is None:
            raise self.error("extract() needs a destination directory")
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        if task is not None:
            task.plan(sum(entry.size for entry in self.entries))
        for entry in self.entries:
            ArchiveTask.check(task)  # asked before the file is opened: no empty leftovers
            target = self._safe_join(dest, entry.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                self._write_one(entry, handle, task)
        return dest

    def extract_entry(self, name: str, dest_dir: str | Path, task: ArchiveTask | None = None) -> Path:
        """Write the single file ``name`` into ``dest_dir``, by its own name.

        The folders the entry sits in inside the archive are not recreated:
        the chosen destination becomes the file's folder.
        """
        dest = Path(dest_dir)
        base = name.replace("\\", "/").split("/")[-1]
        entry = next((item for item in self.entries if item.name == name), Entry(name, 0))
        ArchiveTask.check(task)  # asked before anything is created
        dest.mkdir(parents=True, exist_ok=True)
        target = self._safe_join(dest, base)
        if task is not None:
            task.plan(entry.size)
        with target.open("wb") as handle:
            self._write_one(entry, handle, task)
        return target

    def extract_folder(self, prefix: str, dest_dir: str | Path, task: ArchiveTask | None = None) -> Path:
        """Write every file below the folder ``prefix`` into ``dest_dir``.

        The folder itself is recreated inside ``dest_dir`` under its own name
        and keeps the structure of everything below it.
        """
        prefix = prefix.replace("\\", "/").strip("/")
        start = prefix + "/"
        wanted = [entry for entry in self.entries if entry.name.replace("\\", "/").startswith(start)]
        if not wanted:
            raise self.error(f"folder {prefix} is not in this archive")
        dest = Path(dest_dir) / Path(prefix).name
        dest.mkdir(parents=True, exist_ok=True)
        if task is not None:
            task.plan(sum(entry.size for entry in wanted))
        for entry in wanted:
            ArchiveTask.check(task)  # asked before the file is opened: no empty leftovers
            target = self._safe_join(dest, entry.name[len(start) :])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                self._write_one(entry, handle, task)
        return dest

    def _write_one(self, entry: Entry, handle: BinaryIO, task: ArchiveTask | None) -> None:
        """Copy ``entry`` into the open ``handle``, reporting to ``task``.

        The caller has already asked whether the job may carry on, which is why
        the check happens before the file is opened rather than here: a job
        stopped at this point should not leave an empty file behind.
        """
        if task is None:
            self.write_contents(entry.name, handle)
            return
        task.starting(entry.name)
        self.write_contents(entry.name, ReportingFile(handle, task))

    def _safe_join(self, dest: Path, name: str) -> Path:
        """:func:`safe_join` reporting through this format's error type."""
        return safe_join(dest, name, self.error)


def safe_join(dest: Path, name: str, error: type[ArchiveError] = ArchiveError) -> Path:
    """Join an entry name onto ``dest`` while rejecting path escapes.

    Entry names are always relative with forward slashes, so anything rooted
    (``/x``, ``C:\\x``, ``\\\\server\\x``) or climbing out with ``..`` is refused
    instead of being quietly rewritten.  ``error`` is the exception type the
    calling format raises with, so its own callers keep catching their own error.
    """
    if _ABSOLUTE_NAME.match(name):
        raise error(f"unsafe file name in archive: {name}")
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        raise error(f"unsafe file name in archive: {name}")
    return dest.joinpath(*parts)
