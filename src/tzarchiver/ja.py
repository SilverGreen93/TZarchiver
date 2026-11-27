"""Reading of Trainz Jet Archive files (``*.ja``) - read only.

Jet Archives are the chunked containers older Trainz versions (TRS2004,
TS2010) shipped their built-in content in; see ``ja-format.md`` in the project
root for the format.  A single archive easily holds tens of thousands of files
and well over a gigabyte, so this module never loads one into memory: the
``INFO`` header and the ``IDX `` index are read up front and every file is
sought out, expanded and written on demand.

Only reading is implemented.  Writing one would need a byte pair encoding
compressor as well as the chunk layout, and nothing in Trainz needs archives
this tool cannot already make as ``*.tzarc``.

The shared extraction, listing and safety behaviour comes from ``archive.py``.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from .archive import ArchiveBase, ArchiveError

__all__ = [
    "MAGIC",
    "INFO_TAG",
    "FIL_TAG",
    "IDX_TAG",
    "FLAG_STORED",
    "FLAG_COMPRESSED",
    "JaError",
    "JaEntry",
    "JaArchive",
    "read_ja",
    "crc_bzip2",
    "expand_cfil",
]

MAGIC = b"ARCH"
INFO_TAG = b"INFO"
FIL_TAG = b"FIL "
IDX_TAG = b"IDX "

#: 'ARC0' written as a little endian integer, the archive id inside INFO
ARCHIVE_ID = 0x41524330
#: the Jet Archiver versions seen in the wild: 1.1 (TRS2004) up to 1.2 (TS2010)
MIN_VERSION = 0x101
MAX_VERSION = 0x102

INFO_SIZE = 32
#: a file name is a MAX_PATH buffer, terminated by the first NUL
NAME_FIELD = 260
FIL_HEADER_SIZE = 288
#: an index row: two offsets plus an exact copy of the FIL header
IDX_ENTRY_SIZE = 296

FLAG_STORED = 0x00
FLAG_COMPRESSED = 0x80

#: stand-alone compressed files (``*.cfil``) and compressed entries share this
CFIL_MAGIC = b"CFIL"
CFIL_VERSION = 0x101
CFIL_HEADER_SIZE = 12
BLOCK_HEADER_SIZE = 2
#: block header bit meaning "copied as is" instead of byte pair encoded
RAW_BLOCK = 0x8000
#: how much a file is read at a time when copying stored bytes
COPY_CHUNK = 1 << 20


class JaError(ArchiveError):
    """Raised for anything that is not a readable Jet Archive."""


# -- checksum -------------------------------------------------------------
def _build_crc_table() -> tuple:
    """CRC-32/BZIP2 table: polynomial 0x04C11DB7, MSB first, not reflected."""
    table = []
    for value in range(256):
        crc = value << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
        table.append(crc)
    return tuple(table)


_CRC_TABLE = _build_crc_table()


def crc_bzip2(data: bytes) -> int:
    """The checksum a Jet Archive stores per file.

    This is CRC-32/BZIP2, not the usual reflected zlib CRC-32; the archives
    themselves carry it for every file, compressed or stored.  It is a plain
    Python loop, so use it to check a file or two rather than a whole archive.
    """
    crc = 0xFFFFFFFF
    table = _CRC_TABLE
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ byte]
    return crc ^ 0xFFFFFFFF


# -- byte pair encoding (Philip Gage's BPE, Auran's packet framing) --------
def _expand_bpe_block(block: bytes) -> bytearray:
    """Expand one compressed CFIL block: back to back BPE packets.

    Each packet carries a pair table and then the packed bytes.  The table maps
    a code to either itself (a plain byte) or to a pair of other codes, and the
    packed bytes are expanded depth first from those codes.  Unlike Gage's
    original, a skipped run here is followed by a fresh count byte, which is
    what the Jet Archiver and JAX write.
    """
    out = bytearray()
    position = 0
    end = len(block)
    try:
        while position < end:
            left = list(range(256))
            right = [0] * 256
            code = 0
            while code < 256:
                count = block[position]
                position += 1
                if count > 127:  # this many codes keep the meaning they have now
                    code += count - 127
                    continue
                for _ in range(count + 1):
                    left[code] = block[position]
                    position += 1
                    if left[code] != code:
                        right[code] = block[position]
                        position += 1
                    code += 1
            length = (block[position] << 8) | block[position + 1]  # big endian
            position += 2
            stack = []
            for _ in range(length):
                stack.append(block[position])
                position += 1
                while stack:
                    top = stack.pop()
                    if left[top] == top:
                        out.append(top)
                    else:
                        stack.append(right[top])
                        stack.append(left[top])
    except IndexError:
        raise JaError("compressed data ends in the middle of a block") from None
    return out


def _stream_cfil(handle: BinaryIO) -> Iterator[bytes]:
    """Yield the pieces the CFIL stream ``handle`` is sitting on expands to.

    Blocks are read and expanded one at a time, which keeps even a 60 MB member
    of a built-in archive small in memory.
    """
    header = handle.read(CFIL_HEADER_SIZE)
    if len(header) < CFIL_HEADER_SIZE:
        raise JaError("compressed data ends inside its CFIL header")
    if header[:4] != CFIL_MAGIC:
        raise JaError("compressed data has no CFIL header")
    version, total = struct.unpack_from("<II", header, 4)
    if version != CFIL_VERSION:
        raise JaError(f"CFIL version {version:#x} is not supported!")
    written = 0
    while written < total:
        raw = handle.read(BLOCK_HEADER_SIZE)
        if len(raw) < BLOCK_HEADER_SIZE:
            raise JaError("compressed data ends inside a block header")
        (header_value,) = struct.unpack("<H", raw)
        copied = bool(header_value & RAW_BLOCK)
        length = header_value & 0x7FFF if copied else header_value
        if length == 0:
            raise JaError("compressed data has an empty block")
        block = handle.read(length)
        if len(block) < length:
            raise JaError("compressed data ends inside a block")
        piece = block if copied else bytes(_expand_bpe_block(block))
        written += len(piece)
        yield piece


def expand_cfil(data: bytes) -> bytes:
    """Expand a whole CFIL stream held in memory, e.g. a stand-alone ``*.cfil``."""
    return b"".join(_stream_cfil(io.BytesIO(data)))


# -- the archive itself ----------------------------------------------------
@dataclass(frozen=True)
class JaEntry:
    """One index row: where a file sits in the archive and how it is stored.

    ``size`` is the length the file has once expanded, ``stored_size`` the
    number of bytes that follow its FIL header, and ``checksum`` the
    CRC-32/BZIP2 of the expanded contents.
    """

    name: str
    size: int
    stored_size: int
    checksum: int
    flags: int
    offset: int

    @property
    def compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)


@dataclass(frozen=True)
class _Header:
    """What the INFO chunk says about the archive."""

    version: int
    count: int
    index_offset: int
    build_version: int
    product_code: int


class JaArchive(ArchiveBase):
    """A Jet Archive: its header and index, with contents read from disk."""

    error = JaError

    def __init__(
        self,
        path: str | Path,
        version: int = MAX_VERSION,
        entries: tuple = (),
        build_version: int = 0,
        product_code: int = 0,
    ) -> None:
        self.path = Path(path)
        self.version = version
        self.entries: list[JaEntry] = list(entries)
        self.build_version = build_version
        self.product_code = product_code
        self._by_name = {entry.name: entry for entry in self.entries}

    # -- listing ----------------------------------------------------------
    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    @property
    def format_label(self) -> str:
        """The format the way people name it: 0x102 is Jet Archiver 1.2."""
        return f"ja {(self.version >> 8) & 0xFF}.{self.version & 0xFF}"

    def _entry(self, name: str) -> JaEntry:
        try:
            return self._by_name[name]
        except KeyError:
            raise JaError(f"{name} is not in this archive") from None

    # -- contents ---------------------------------------------------------
    def write_contents(self, name: str, target: BinaryIO) -> None:
        """Copy one member from the archive file into the open file ``target``.

        Compressed members are expanded block by block, so only a 16 KiB piece
        of a huge file is ever in memory.
        """
        entry = self._entry(name)
        with self.path.open("rb") as source:
            source.seek(entry.offset)
            if entry.compressed:
                for piece in _stream_cfil(source):
                    target.write(piece)
            else:
                _copy_exact(source, target, entry.stored_size, name)

    def verify(self, name: str) -> bool:
        """Expand ``name`` and compare it with the checksum the archive stores.

        One file at a time only: the checksum is computed in Python, so running
        it over a whole built-in archive would take longer than extracting it.
        """
        return crc_bzip2(self.read(name)) == self._entry(name).checksum


def read_ja(path: str | Path) -> JaArchive:
    """Read a Jet Archive's header and index; its contents stay on disk."""
    path = Path(path)
    with path.open("rb") as handle:
        size = handle.seek(0, io.SEEK_END)
        handle.seek(0)
        header = _read_info(handle, size, path)
        entries = _read_index(handle, size, header, path)
    return JaArchive(path, header.version, entries, header.build_version, header.product_code)


# -- header and index ------------------------------------------------------
def _read(handle: BinaryIO, count: int, what: str) -> bytes:
    """Read exactly ``count`` bytes or say which part is missing."""
    data = handle.read(count)
    if len(data) != count:
        raise JaError(f"Jet Archive is truncated (expected {what})")
    return data


def _read_info(handle: BinaryIO, size: int, path: Path) -> _Header:
    """Walk the ARCH tag and the INFO chunk into a :class:`_Header`."""
    if _read(handle, 4, "the ARCH file id") != MAGIC:
        raise JaError(f"File format not supported for {path}")
    if _read(handle, 4, "the INFO chunk tag") != INFO_TAG:
        raise JaError(f"{path.name} has no INFO chunk")
    (info_length,) = struct.unpack("<I", _read(handle, 4, "the INFO chunk length"))
    if info_length < INFO_SIZE:
        raise JaError(f"{path.name} has a short INFO chunk")
    info = _read(handle, info_length, "the INFO chunk")
    archive_id, version, count, index_offset, build, product = struct.unpack_from("<6I", info)
    if archive_id != ARCHIVE_ID:
        raise JaError(f"{path.name} is not a Jet Archive (archive id {archive_id:#010x})")
    if not MIN_VERSION <= version <= MAX_VERSION:
        raise JaError(f"Jet Archive version {version:#x} is not supported!")
    if index_offset >= size:
        raise JaError(f"{path.name} points its index outside the file")
    return _Header(version, count, index_offset, build, product)


def _read_index(handle: BinaryIO, size: int, header: _Header, path: Path) -> tuple:
    """Turn the IDX chunk into the archive's list of members."""
    handle.seek(header.index_offset)
    if _read(handle, 4, "the IDX chunk tag") != IDX_TAG:
        raise JaError(f"{path.name} has no IDX chunk where its header says")
    (index_length,) = struct.unpack("<I", _read(handle, 4, "the IDX chunk length"))
    if index_length % IDX_ENTRY_SIZE:
        raise JaError(f"{path.name} has an index that is not a whole number of entries")
    count = index_length // IDX_ENTRY_SIZE
    if count != header.count:
        raise JaError(f"{path.name} counts {header.count} files but indexes {count}")
    data = _read(handle, index_length, "the IDX chunk")
    entries = []
    for row in range(0, index_length, IDX_ENTRY_SIZE):
        entry = _parse_index_row(data[row : row + IDX_ENTRY_SIZE])
        if entry.offset + entry.stored_size > size:
            raise JaError(f"{entry.name} points outside the file")
        entries.append(entry)
    return tuple(entries)


def _parse_index_row(row: bytes) -> JaEntry:
    """Split one 296-byte index row; its tail is the FIL header copy."""
    offset, stored_size = struct.unpack_from("<2I", row)
    name = row[8 : 8 + NAME_FIELD].split(b"\0")[0]
    size, _, checksum, _reserved1, _reserved2, _reserved3, flags = struct.unpack_from(
        "<7I", row, 8 + NAME_FIELD
    )
    if not name:
        raise JaError("Jet Archive index has an empty file name")
    return JaEntry(name.decode("utf-8", "replace"), size, stored_size, checksum, flags, offset)


def _copy_exact(source: BinaryIO, target: BinaryIO, count: int, name: str) -> None:
    """Copy ``count`` bytes from one open file to the other."""
    remaining = count
    while remaining > 0:
        piece = source.read(min(COPY_CHUNK, remaining))
        if not piece:
            raise JaError(f"{name} is truncated in the archive")
        target.write(piece)
        remaining -= len(piece)
