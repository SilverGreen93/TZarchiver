"""Reading and writing of Trainz archive files (``*.tzarc``).

This module is pure logic: it never imports Qt and never shows UI.  See
``tzarc-format.md`` in the project root for the format description; the pieces
both archive formats share live in ``archive.py``.

Version 1 is uncompressed and stores every field big endian.  Version 2 keeps
the ``TZac`` + version header uncompressed and wraps the whole version 1 body
(starting at the file count field) in little endian bookkeeping plus a series of
independently zlib-compressed 65000 byte blocks.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Sequence

from .archive import ArchiveBase, ArchiveError, Entry, default_extract_dir

__all__ = [
    "MAGIC",
    "TRAILER",
    "V1",
    "V2",
    "CHUNK_SIZE",
    "MAX_NAME_LENGTH",
    "TzarcError",
    "Entry",
    "Archive",
    "read_archive",
    "create_archive",
    "default_extract_dir",
    "pack_v1",
    "unpack_v2",
]

MAGIC = b"TZac"
#: Four bytes between the directory and the file contents.  Unique per archive,
#: not derived from the contents; the original app always wrote these values.
TRAILER = bytes((125, 47, 13, 99))

V1 = 1
V2 = 2

#: Size of the uncompressed chunks the v2 body is split into.
CHUNK_SIZE = 65000
#: Name length is stored in a single byte.
MAX_NAME_LENGTH = 255


class TzarcError(ArchiveError):
    """Raised for anything that is not a readable/writable tzarc archive."""


class Archive(ArchiveBase):
    """An archive plus the contents of every file it holds."""

    error = TzarcError

    def __init__(self, version: int = V1, entries: Iterable[Entry] = (), contents: Iterable[bytes] = ()):
        if version not in (V1, V2):
            raise TzarcError(f"TZarc version {version} is not supported!")
        self.version = version
        self.entries: list[Entry] = list(entries)
        data = list(contents)
        if len(data) != len(self.entries):
            raise TzarcError("archive has a different number of entries and contents")
        self._data: dict[str, bytes] = {e.name: d for e, d in zip(self.entries, data)}

    # -- access -----------------------------------------------------------
    def __contains__(self, name: str) -> bool:
        return name in self._data

    def read(self, name: str) -> bytes:
        """Return the contents of ``name``."""
        try:
            return self._data[name]
        except KeyError:
            raise TzarcError(f"{name} is not in this archive") from None

    @property
    def format_label(self) -> str:
        """How the archive is named in listings: "v1" or "v2"."""
        return f"v{self.version}"

    # -- output -----------------------------------------------------------
    def write(self, path: str | Path, version: int | None = None) -> Path:
        """Serialize the archive to ``path`` (``TZac`` header + body)."""
        version = self.version if version is None else version
        path = Path(path)
        body = pack_v1(self.entries, (self.read(e.name) for e in self.entries))
        if version == V1:
            payload = body
        elif version == V2:
            payload = _make_v2_payload(body)
        else:
            raise TzarcError(f"TZarc version {version} is not supported!")
        path.write_bytes(MAGIC + version.to_bytes(4, "big") + payload)
        return path

    # -- extracting (the how of it; archive.py drives the where) ----------
    def write_contents(self, name: str, target: BinaryIO) -> None:
        """Hand the stored bytes of ``name`` to the open file ``target``."""
        target.write(self.read(name))


def read_archive(path: str | Path) -> Archive:
    """Parse an archive file, transparently handling v1 and v2."""
    raw = Path(path).read_bytes()
    if not raw.startswith(MAGIC):
        raise TzarcError(f"File format not supported for {path}")
    if len(raw) < 8:
        raise TzarcError(f"{path} is truncated")
    version = int.from_bytes(raw[4:8], "big")
    if version == V1:
        body = raw[8:]
    elif version == V2:
        body = unpack_v2(raw[8:])
    else:
        raise TzarcError(f"TZarc version {version} is not supported!")
    entries, contents = _parse_v1_body(body, source=str(path))
    return Archive(version, entries, contents)


def create_archive(source: str | Path, version: int = V1) -> Archive:
    """Build an archive from a folder (or a single file), like the app does.

    Files are collected recursively; their names inside the archive are the
    paths relative to ``source`` with forward slashes.
    """
    source = Path(source)
    if source.is_file():
        files = [source]
        root = source.parent
    else:
        files = [p for p in sorted(source.rglob("*")) if p.is_file()]
        root = source

    entries: list[Entry] = []
    contents: list[bytes] = []
    for file in files:
        name = file.relative_to(root).as_posix()
        data = file.read_bytes()
        entries.append(Entry(name, len(data)))
        contents.append(data)
    return Archive(version, entries, contents)


# -- version 1 ------------------------------------------------------------
def pack_v1(entries: Sequence[Entry] | Iterable[Entry], contents: Iterable[bytes]) -> bytes:
    """Build a version 1 body (file count field onward)."""
    entries = list(entries)
    out = bytearray(struct.pack(">I", len(entries)))
    for entry in entries:
        name_bytes = entry.name.encode("utf-8")
        if len(name_bytes) > MAX_NAME_LENGTH:
            raise TzarcError(f"file name too long for the tzarc format: {entry.name}")
        out.append(len(name_bytes))
        out += name_bytes
        out += struct.pack(">Q", entry.size)
    out += TRAILER
    out += b"".join(contents)
    return bytes(out)


def _parse_v1_body(body: bytes, source: str = "archive") -> tuple[list[Entry], list[bytes]]:
    """Split a version 1 body into its directory and the file contents."""
    pos = 0

    def take(n: int, what: str) -> bytes:
        nonlocal pos
        if pos + n > len(body):
            raise TzarcError(f"{source} is truncated (expected {what})")
        chunk = body[pos : pos + n]
        pos += n
        return chunk

    (count,) = struct.unpack(">I", take(4, "file count"))
    entries: list[Entry] = []
    for _ in range(count):
        (name_len,) = struct.unpack(">B", take(1, "name length"))
        name = take(name_len, "file name").decode("utf-8", "replace")
        (size,) = struct.unpack(">Q", take(8, "file size"))
        entries.append(Entry(name, size))
    take(4, "random value")  # unique per archive, ignored

    contents: list[bytes] = []
    for entry in entries:
        contents.append(take(entry.size, f"contents of {entry.name}"))
    return entries, contents


# -- version 2 ------------------------------------------------------------
def unpack_v2(payload: bytes) -> bytes:
    """Return the version 1 body hidden in a v2 payload (after the header)."""
    if len(payload) < 12:
        raise TzarcError("invalid TZarc v2 header")
    total = int.from_bytes(payload[0:8], "little")
    count = int.from_bytes(payload[8:12], "little")
    if total < 0 or count < 0:
        raise TzarcError("invalid TZarc v2 header")
    table_end = 12 + 2 * count
    if table_end > len(payload):
        raise TzarcError("invalid TZarc v2 header")

    body = bytearray()
    offset = table_end
    for index in range(count):
        (size,) = struct.unpack_from("<H", payload, 12 + 2 * index)
        size += 1  # stored as compressed size - 1
        if offset + size > len(payload):
            raise TzarcError(f"unexpected end of TZarc v2 data in block {index}")
        block = payload[offset : offset + size]
        offset += size
        if size < 6 or (block[0] & 0xF) != 8 or ((block[0] << 8) | block[1]) % 31 != 0:
            raise TzarcError(f"invalid zlib header in TZarc v2 block {index}")
        try:
            body += zlib.decompress(block)
        except zlib.error as exc:
            raise TzarcError(f"invalid zlib data in TZarc v2 block {index}") from exc

    if len(body) != total:
        raise TzarcError("TZarc v2 uncompressed size does not match the blocks")
    return bytes(body)


def _make_v2_payload(body: bytes) -> bytes:
    """Wrap a version 1 body in the v2 block layout."""
    chunks = [body[i : i + CHUNK_SIZE] for i in range(0, len(body), CHUNK_SIZE)]
    compressed = [zlib.compress(chunk) for chunk in chunks]
    out = bytearray(struct.pack("<Q", len(body)))
    out += struct.pack("<I", len(chunks))
    for chunk in compressed:
        out += struct.pack("<H", len(chunk) - 1)
    out += b"".join(compressed)
    return bytes(out)


def iter_entries(archive: Archive) -> Iterator[Entry]:
    """Iterate the directory entries of ``archive``."""
    yield from archive.entries
