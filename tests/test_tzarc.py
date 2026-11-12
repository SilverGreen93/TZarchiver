"""Tests for the tzarc read/write logic (no Qt involved).

Run against the fixtures in ``tests/test_files``: v1 and v2 archives, the
folders they were extracted to, and a folder (with a subfolder) plus an
archive made from it.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from tzarchiver.tzarc import (
    CHUNK_SIZE,
    MAGIC,
    TRAILER,
    V1,
    V2,
    Archive,
    Entry,
    TzarcError,
    create_archive,
    default_extract_dir,
    pack_v1,
    read_archive,
    unpack_v2,
)

FIXTURES = Path(__file__).parent / "test_files"

V1_ARCHIVE = FIXTURES / "kuid 474195 20651 v1.tzarc"
V1_EXTRACTED = FIXTURES / "kuid 474195 20651"
V2_ARCHIVE = FIXTURES / "kuid 474195 20651 v2.tzarc"
SMALL_V2_ARCHIVE = FIXTURES / "kuid 173000 100413 v2.tzarc"
FOLDER = FIXTURES / "folder"
FOLDER_ARCHIVE = FIXTURES / "folder v1.tzarc"

V1_NAMES = [
    "1.bmp",
    "1.texture",
    "1.texture.txt",
    "1.tga",
    "config.chump",
    "macaz.im",
    "sunet.wav",
    "thumbnail.jpg",
]
V2_NAMES = [
    "config.chump",
    "summer/1.bmp",
    "summer/1.texture",
    "summer/1.texture.txt",
    "summer/1.tga",
    "summer/macaz.im",
    "sunet.wav",
    "thumbnail.jpg",
    "winter/1.bmp",
    "winter/1.texture",
    "winter/1.texture.txt",
    "winter/1.tga",
    "winter/macaz.im",
]


# -- reading ---------------------------------------------------------------
def test_v1_lists_entries_in_archive_order():
    archive = read_archive(V1_ARCHIVE)
    assert archive.version == 1
    assert archive.names() == V1_NAMES
    assert len(archive) == 8


def test_v2_lists_entries_in_archive_order():
    archive = read_archive(V2_ARCHIVE)
    assert archive.version == 2
    assert archive.names() == V2_NAMES
    assert len(archive) == 13


@pytest.mark.parametrize(
    "path,extracted",
    [(V1_ARCHIVE, V1_EXTRACTED), (FIXTURES / "kuid -25 168 v1.tzarc", FIXTURES / "kuid -25 168"),
     (FIXTURES / "kuid -25 242 v1.tzarc", FIXTURES / "kuid -25 242")],
    ids=["kuid 474195 20651", "kuid -25 168", "kuid -25 242"],
)
def test_archive_contents_match_the_extracted_folder(path, extracted):
    """The folders next to the fixtures are what the app unpacked from them."""
    archive = read_archive(path)
    for entry in archive.entries:
        assert entry.size == (extracted / entry.name).stat().st_size
        assert archive.read(entry.name) == (extracted / entry.name).read_bytes()
    assert archive.names() == sorted(f.relative_to(extracted).as_posix() for f in extracted.rglob("*") if f.is_file())


def test_entries_report_the_size_stored_in_the_directory():
    for path in (V1_ARCHIVE, V2_ARCHIVE):
        archive = read_archive(path)
        for entry in archive.entries:
            assert len(archive.read(entry.name)) == entry.size


def test_read_is_by_name_and_rejects_unknown_names():
    archive = read_archive(V1_ARCHIVE)
    assert archive.read("config.chump").startswith(b"ACS$")
    assert "1.bmp" in archive
    assert "nope.bin" not in archive
    with pytest.raises(TzarcError, match="not in this archive"):
        archive.read("nope.bin")


def test_extract_writes_files_next_to_the_archive(tmp_path):
    archive = read_archive(V1_ARCHIVE)
    dest = tmp_path / V1_ARCHIVE.stem
    archive.extract(dest)
    for name in archive.names():
        assert (dest / name).read_bytes() == (V1_EXTRACTED / name).read_bytes()


def test_extract_creates_subfolders(tmp_path):
    archive = read_archive(FOLDER_ARCHIVE)
    assert "folder/fisier.txt" in archive.names()
    archive.extract(tmp_path / "out")
    assert (tmp_path / "out" / "folder" / "fisier.txt").read_bytes() == (FOLDER / "folder" / "fisier.txt").read_bytes()


def test_default_extract_dir_is_the_archive_name_beside_it():
    assert default_extract_dir(Path("C:/trainz/content/kuid 474195 20651 v1.tzarc")) == Path("C:/trainz/content/kuid 474195 20651 v1")


def test_reject_names_escaping_the_destination(tmp_path):
    for name in ("../evil.txt", "..\\evil.txt", "/evil.txt", "C:/evil.txt"):
        rogue = Archive(V1, [Entry(name, 1)], [b"x"])
        with pytest.raises(TzarcError, match="unsafe"):
            rogue.extract(tmp_path / "out")
    assert not (tmp_path.parent / "evil.txt").exists()


# -- version 2 layout ------------------------------------------------------
@pytest.mark.parametrize("path", [V2_ARCHIVE, SMALL_V2_ARCHIVE], ids=["32 blocks", "2 blocks"])
def test_v2_header_is_little_endian_block_bookkeeping(path):
    raw = path.read_bytes()
    assert raw[:4] == MAGIC
    assert raw[4:8] == b"\x00\x00\x00\x02"

    payload = raw[8:]
    total, count = struct.unpack_from("<QI", payload, 0)
    archive = read_archive(path)
    expected_body = pack_v1(archive.entries, (archive.read(n) for n in archive.names()))
    assert total == len(expected_body)
    assert count == -(-total // CHUNK_SIZE)

    sizes = [struct.unpack_from("<H", payload, 12 + 2 * i)[0] + 1 for i in range(count)]
    offset = 12 + 2 * count
    for size in sizes:
        assert size >= 6
        assert (payload[offset] & 0xF) == 8
        assert ((payload[offset] << 8) | payload[offset + 1]) % 31 == 0
        offset += size
    assert offset == len(payload)


def test_the_big_v2_fixture_really_is_multi_block():
    _, count = struct.unpack_from("<QI", V2_ARCHIVE.read_bytes()[8:], 0)
    archive = read_archive(V2_ARCHIVE)
    body = pack_v1(archive.entries, (archive.read(n) for n in archive.names()))
    assert count > 1
    assert len(body) > CHUNK_SIZE


def test_v2_blocks_hold_65000_byte_chunks_except_the_last():
    payload = V2_ARCHIVE.read_bytes()[8:]
    body = unpack_v2(payload)
    total, count = struct.unpack_from("<QI", payload, 0)
    sizes = [struct.unpack_from("<H", payload, 12 + 2 * i)[0] + 1 for i in range(count)]
    assert total == len(body)

    chunks = [body[i : i + CHUNK_SIZE] for i in range(0, len(body), CHUNK_SIZE)]
    assert len(chunks) == count
    assert all(len(c) == CHUNK_SIZE for c in chunks[:-1])
    assert 0 < len(chunks[-1]) <= CHUNK_SIZE

    offset = 12 + 2 * count
    for chunk, size in zip(chunks, sizes):
        assert zlib.decompress(payload[offset : offset + size]) == chunk
        offset += size


def test_unpack_v2_rejects_a_bad_zlib_header():
    payload = V2_ARCHIVE.read_bytes()[8:]
    broken = bytearray(payload)
    broken[12 + 2 * struct.unpack_from("<I", payload, 8)[0]] = 0x00  # first block's CMF
    with pytest.raises(TzarcError, match="invalid zlib header"):
        unpack_v2(bytes(broken))


def test_unpack_v2_rejects_truncated_blocks():
    payload = V2_ARCHIVE.read_bytes()[8:]
    with pytest.raises(TzarcError, match="unexpected end"):
        unpack_v2(payload[: len(payload) // 2])


def test_a_single_block_v2_payload_reads_back():
    body = pack_v1([Entry("x", 3)], [b"abc"])
    block = zlib.compress(body)
    payload = struct.pack("<QI", len(body), 1) + struct.pack("<H", len(block) - 1) + block
    assert unpack_v2(payload) == body


# -- writing ---------------------------------------------------------------
def test_created_v1_archive_matches_the_fixture_except_the_random_field(tmp_path):
    """The VB app's output is reproducible; only the 4 free bytes differ.

    The value between the directory and the file data is a per-archive
    marker (the VB source calls it "random time data"), the fixtures made by
    Trainz leave it zeroed while the app always writes 7D 2F 0D 63.
    """
    target = create_archive(FOLDER).write(tmp_path / "created.tzarc")
    produced = target.read_bytes()
    original = FOLDER_ARCHIVE.read_bytes()
    assert len(produced) == len(original)

    marker = 12 + sum(1 + len(n.encode("utf-8")) + 8 for n in create_archive(FOLDER).names())
    assert produced[marker : marker + 4] == TRAILER
    assert original[marker : marker + 4] == b"\x00\x00\x00\x00"
    assert produced[:marker] == original[:marker]
    assert produced[marker + 4 :] == original[marker + 4 :]


def test_round_trip_v1_and_v2(tmp_path):
    source = create_archive(FOLDER)
    for version in (V1, V2):
        target = tmp_path / f"round{version}.tzarc"
        source.write(target, version=version)
        back = read_archive(target)
        assert back.version == version
        assert back.names() == source.names()
        for name in back.names():
            assert back.read(name) == source.read(name)
        if version == V2:
            assert target.stat().st_size < (tmp_path / "round1.tzarc").stat().st_size


def test_a_whole_asset_survives_a_v1_to_v2_conversion(tmp_path):
    """Repack the extracted v1 asset as v2 and read every byte back."""
    archive = read_archive(V1_ARCHIVE)
    target = tmp_path / "converted.tzarc"
    Archive(V2, archive.entries, (archive.read(n) for n in archive.names())).write(target, version=V2)

    back = read_archive(target)
    assert back.names() == V1_NAMES
    for name in V1_NAMES:
        assert back.read(name) == (V1_EXTRACTED / name).read_bytes()


def test_created_archive_keeps_subfolders_with_forward_slashes(tmp_path):
    folder = tmp_path / "asset"
    (folder / "sub" / "deep").mkdir(parents=True)
    (folder / "config.chump").write_bytes(b"config")
    (folder / "sub" / "deep" / "nested.txt").write_text("nested")

    archive = create_archive(folder)
    assert archive.names() == ["config.chump", "sub/deep/nested.txt"]
    assert archive.entries[1].size == 6

    target = tmp_path / "asset.tzarc"
    archive.write(target)
    assert read_archive(target).read("sub/deep/nested.txt") == b"nested"


def test_name_longer_than_one_byte_is_rejected():
    with pytest.raises(TzarcError, match="too long"):
        pack_v1([Entry("x" * 256, 1)], [b"x"])


def test_v1_directory_layout(tmp_path):
    """Header and directory match the spec byte for byte."""
    folder = tmp_path / "one file"
    folder.mkdir()
    (folder / "a.txt").write_bytes(b"abc")

    target = create_archive(folder).write(tmp_path / "one file.tzarc")
    data = target.read_bytes()
    assert data[:4] == MAGIC
    assert data[4:8] == b"\x00\x00\x00\x01"
    assert data[8:12] == b"\x00\x00\x00\x01"  # one file
    assert data[12] == 5  # name length
    assert data[13:18] == b"a.txt"
    assert data[18:26] == struct.pack(">Q", 3)
    assert data[26:30] == TRAILER
    assert data[30:] == b"abc"


# -- error handling --------------------------------------------------------
def test_rejects_a_non_archive(tmp_path):
    bogus = tmp_path / "bogus.tzarc"
    bogus.write_bytes(b"PK\x03\x04 not a tzarc")
    with pytest.raises(TzarcError, match="not supported"):
        read_archive(bogus)


def test_rejects_unknown_versions(tmp_path):
    archive = tmp_path / "v3.tzarc"
    archive.write_bytes(MAGIC + (3).to_bytes(4, "big") + b"\x00" * 32)
    with pytest.raises(TzarcError, match="version 3 is not supported"):
        read_archive(archive)


def test_rejects_truncated_directory(tmp_path):
    archive = tmp_path / "cut.tzarc"
    archive.write_bytes(MAGIC + b"\x00\x00\x00\x01" + b"\xff\xff\xff\xff")
    with pytest.raises(TzarcError, match="truncated"):
        read_archive(archive)


def test_rejects_missing_file_contents(tmp_path):
    archive = tmp_path / "short.tzarc"
    body = struct.pack(">I", 1) + bytes([5]) + b"a.txt" + struct.pack(">Q", 500) + TRAILER + b"abc"
    archive.write_bytes(MAGIC + b"\x00\x00\x00\x01" + body)
    with pytest.raises(TzarcError, match="contents of a.txt"):
        read_archive(archive)


def test_rejects_a_size_mismatch_between_entries_and_data():
    with pytest.raises(TzarcError, match="different number of entries"):
        Archive(V1, [Entry("a.txt", 1), Entry("b.txt", 1)], [b"x"])
