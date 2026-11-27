"""Small writer for the Jet Archive format, so the tests have real ``*.ja`` bytes.

The archives the game ships are hundreds of MB of copyrighted content, so
nothing binary is committed here.  Everything the tests need is instead put
together from the layout in ``ja-format.md``: an INFO chunk, one FIL chunk per
file and an IDX chunk whose rows copy those headers.  Only the parts a reader
has to check are built - there is no compressor, the compressed members are
encoded by hand with the byte pair encoding packet rules.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from tzarchiver.ja import (
    ARCHIVE_ID,
    CFIL_MAGIC,
    CFIL_VERSION,
    FIL_HEADER_SIZE,
    FIL_TAG,
    FLAG_COMPRESSED,
    FLAG_STORED,
    IDX_TAG,
    INFO_SIZE,
    INFO_TAG,
    MAGIC,
    NAME_FIELD,
    RAW_BLOCK,
    crc_bzip2,
)

#: payload that still fits one byte pair encoded block (table + length + data)
BPE_PAYLOAD_LIMIT = 16000
#: a copied block is at most this long, its header length is 15 bits
COPY_BLOCK_LIMIT = 0x7FFF


def identity_table() -> bytes:
    """Pair table where every code means itself, as two runs of 128 codes."""
    return bytes((0x7F,)) + bytes(range(128)) + bytes((0x7F,)) + bytes(range(128, 256))


def bpe_packet(table: bytes, packed: bytes) -> bytes:
    """One hand written byte pair encoded block: table, count, packed codes."""
    block = table + struct.pack(">H", len(packed)) + packed
    return struct.pack("<H", len(block)) + block


def cfil_bpe(data: bytes, block_size: int = BPE_PAYLOAD_LIMIT) -> bytes:
    """Wrap ``data`` in a CFIL stream of byte pair encoded packets.

    Each packet carries an identity pair table, where every code expands to
    itself, followed by the payload and a big endian count of its codes.  That
    is the shape the archiver uses for data it cannot shrink.
    """
    out = [CFIL_MAGIC + struct.pack("<II", CFIL_VERSION, len(data))]
    for start in range(0, max(len(data), 1), block_size):
        piece = data[start : start + block_size]
        out.append(bpe_packet(identity_table(), piece))
    return b"".join(out)


def cfil_copy(data: bytes) -> bytes:
    """Wrap ``data`` in a CFIL stream of copied (uncompressed) blocks."""
    out = [CFIL_MAGIC + struct.pack("<II", CFIL_VERSION, len(data))]
    for start in range(0, max(len(data), 1), COPY_BLOCK_LIMIT):
        piece = data[start : start + COPY_BLOCK_LIMIT]
        out.append(struct.pack("<H", RAW_BLOCK | len(piece)) + piece)
    return b"".join(out)


def plain(stored: bytes) -> bytes:
    """Undo a hand built CFIL stream to get the contents it carries.

    A damaged stream simply ends where its bytes do, which is what the tests
    that store a broken one need.
    """
    if not stored.startswith(CFIL_MAGIC):
        return stored
    total = struct.unpack_from("<I", stored, 8)[0]
    out = bytearray()
    position = 12
    while len(out) < total and position + 2 <= len(stored):
        (value,) = struct.unpack_from("<H", stored, position)
        position += 2
        length = value & 0x7FFF
        piece = stored[position : position + length]
        if not piece:
            break
        position += len(piece)
        if not value & RAW_BLOCK:
            piece = piece[len(identity_table()) + 2 :]  # skip the identity table
        out += piece
    return bytes(out[:total])


@dataclass(frozen=True)
class Member:
    """One archive member: what is stored, and what it means once expanded."""

    name: str
    stored: bytes
    flags: int
    contents: bytes


def member(name: str, contents: bytes, encoding: str = "plain") -> Member:
    """Pack ``contents`` as one member: stored as is, or wrapped in a CFIL stream.

    ``bpe`` uses byte pair encoded blocks, ``copy`` CFIL blocks that are copied
    without being encoded; both set the compressed flag.
    """
    if encoding == "plain":
        return Member(name, contents, FLAG_STORED, contents)
    if encoding == "bpe":
        return Member(name, cfil_bpe(contents), FLAG_COMPRESSED, contents)
    if encoding == "copy":
        return Member(name, cfil_copy(contents), FLAG_COMPRESSED, contents)
    raise ValueError(f"unknown encoding {encoding}")


def fil_header(item: Member) -> bytes:
    """Build one 288 byte FIL header; junk fills the name after its NUL."""
    raw = item.name.encode("utf-8")
    if len(raw) >= NAME_FIELD:
        raise ValueError(f"{item.name} does not fit in a file name field")
    name_field = raw + b"\0" + b"\xcc" * (NAME_FIELD - len(raw) - 1)
    fields = struct.pack(
        "<7I",
        len(item.contents),
        len(item.stored),
        crc_bzip2(item.contents),
        0,
        0,
        0,
        item.flags,
    )
    return name_field + fields


def build_ja(
    members,
    version: int = 0x102,
    count: int | None = None,
    index_offset: int | None = None,
    info_length: int = INFO_SIZE,
    archive_id: int = ARCHIVE_ID,
) -> bytes:
    """Assemble a Jet Archive out of :class:`Member` rows.

    A wrong ``count`` or ``index_offset`` can be forced on purpose to see how a
    reader reacts, and the INFO chunk can be given another length or id.
    """
    prefix = 4 + 4 + 4 + info_length  # ARCH + INFO tag + length + data
    chunks = bytearray()
    index = bytearray()
    for item in members:
        header = fil_header(item)
        data_offset = prefix + len(chunks) + 8 + FIL_HEADER_SIZE
        chunks += FIL_TAG + struct.pack("<I", FIL_HEADER_SIZE + len(item.stored))
        chunks += header + item.stored
        index += struct.pack("<II", data_offset, len(item.stored)) + header
    body = bytearray(MAGIC + INFO_TAG + struct.pack("<I", info_length))
    body += _info(version, len(members) if count is None else count, index_offset or 0, archive_id)
    body += chunks
    body += IDX_TAG + struct.pack("<I", len(index)) + index
    if index_offset is None:
        struct.pack_into("<I", body, 12 + 12, prefix + len(chunks))  # where IDX starts
    return bytes(body)


def _info(version: int, count: int, index_offset: int, archive_id: int) -> bytes:
    """The 32 data bytes of the INFO chunk, the last eight of them reserved."""
    fields = struct.pack("<6I", archive_id, version, count, index_offset, 43208, 2)
    return fields + b"\0" * (INFO_SIZE - len(fields))


def index_at(data: bytes) -> int:
    """Offset of the IDX chunk tag, for tests that damage a finished archive."""
    return data.rfind(IDX_TAG)


def expected_contents(members) -> dict:
    """Name to expanded contents, so extraction can be checked against input."""
    return {item.name: item.contents for item in members}


def sample_members() -> list:
    """A stored file, a byte pair encoded one, a copied-block one and a tiny one."""
    return [
        member("config.chump", SMALL),
        member("sounds/beep.wav", BIG, "bpe"),
        member("sounds/loop/beep2.wav", BIG, "copy"),
        member("license.txt", b"read me\n"),
    ]


#: a plain member and one big enough to need two compressed blocks
SMALL = b"a small file, stored as is\n" * 3
BIG = bytes(range(256)) * 90
