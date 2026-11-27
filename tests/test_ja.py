"""Tests for tzarchiver.ja: the Jet Archive reader, its index and its decoder.

The archive bytes themselves come from ``ja_builder``, which assembles them
from the layout in ``ja-format.md``; the archives Trainz ships are far too big
(and too copyrighted) to commit.
"""

from __future__ import annotations

import os
import struct
import zlib

import pytest

from ja_builder import (
    BIG,
    SMALL,
    Member,
    bpe_packet,
    build_ja,
    cfil_bpe,
    cfil_copy,
    expected_contents,
    identity_table,
    index_at,
    member,
    plain,
    sample_members,
)
from tzarchiver.archive import ArchiveError, open_archive
from tzarchiver.ja import (
    CFIL_MAGIC,
    CFIL_VERSION,
    FLAG_COMPRESSED,
    FLAG_STORED,
    IDX_ENTRY_SIZE,
    JaArchive,
    JaEntry,
    JaError,
    _expand_bpe_block,
    crc_bzip2,
    expand_cfil,
    read_ja,
)


@pytest.fixture
def members():
    return sample_members()


@pytest.fixture
def ja_file(tmp_path, members):
    """A four member archive: stored, byte pair encoded, copied blocks, tiny."""
    path = tmp_path / "Data.ja"
    path.write_bytes(build_ja(members))
    return path


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------

def test_crc_matches_the_bzip2_check_value():
    """The standard CRC-32/BZIP2 check string, not the reflected zlib one."""
    assert crc_bzip2(b"123456789") == 0xFC891918
    assert crc_bzip2(b"") == 0


def test_crc_is_not_the_zlib_one():
    assert crc_bzip2(b"trainz") != zlib.crc32(b"trainz")


# ---------------------------------------------------------------------------
# byte pair encoding packets
# ---------------------------------------------------------------------------

def test_expands_a_packet_whose_codes_are_plain_bytes():
    block = identity_table() + struct.pack(">H", 3) + bytes((65, 66, 67))
    assert bytes(_expand_bpe_block(block)) == b"ABC"


def test_expands_a_pair_into_two_bytes():
    """Code 0 stands for 'h' + 'i'; the other codes keep the meaning they have."""
    table = bytes((1, ord("h"), ord("i"), 1)) + bytes((255, 253))
    block = table + struct.pack(">H", 2) + bytes((0, 129))
    assert bytes(_expand_bpe_block(block)) == b"hi\x81"


def test_expands_pairs_of_pairs_depth_first():
    """Code 1 is 'ab', code 0 is code 1 twice, so one code becomes four bytes."""
    table = bytes((1, 1, 1, ord("a"), ord("b"), 127)) + bytes(range(2, 130))
    table += bytes((125,)) + bytes(range(130, 256))
    block = table + struct.pack(">H", 1) + bytes((0,))
    assert bytes(_expand_bpe_block(block)) == b"abab"


def test_a_skipped_run_is_followed_by_a_fresh_count_byte():
    """128 codes keep their meaning, then the table carries on describing them."""
    table = bytes((1, 0, 90, 0, 255, 125)) + bytes(range(130, 256))
    block = table + struct.pack(">H", 2) + bytes((1, 200))
    assert bytes(_expand_bpe_block(block)) == b"Z\x00\xc8"


def test_a_packet_can_be_followed_by_another():
    """The framing repeats until the block is used up, table included."""
    one = identity_table() + struct.pack(">H", 2) + b"AB"
    two = identity_table() + struct.pack(">H", 1) + b"C"
    assert bytes(_expand_bpe_block(one + two)) == b"ABC"


def test_a_truncated_packet_is_reported():
    block = identity_table() + struct.pack(">H", 8) + b"ab"
    with pytest.raises(JaError, match="ends in the middle of a block"):
        _expand_bpe_block(block)


# ---------------------------------------------------------------------------
# CFIL streams
# ---------------------------------------------------------------------------

def test_expands_byte_pair_encoded_blocks():
    assert expand_cfil(cfil_bpe(BIG)) == BIG


def test_expands_copied_blocks():
    assert expand_cfil(cfil_copy(BIG)) == BIG


def test_mixes_block_kinds():
    stream = (
        CFIL_MAGIC
        + struct.pack("<II", CFIL_VERSION, 4)
        + bpe_packet(identity_table(), b"ab")
        + struct.pack("<H", 0x8000 | 2)
        + b"cd"
    )
    assert expand_cfil(stream) == b"abcd"


def test_a_stream_without_its_header_is_refused():
    with pytest.raises(JaError, match="no CFIL header"):
        expand_cfil(b"NOPE" + b"\0" * 8)


def test_a_stream_of_another_version_is_refused():
    stream = CFIL_MAGIC + struct.pack("<II", 0x102, 2) + struct.pack("<H", 0x8002) + b"hi"
    with pytest.raises(JaError, match="CFIL version 0x102 is not supported"):
        expand_cfil(stream)


def test_a_stream_ending_inside_a_block_is_refused():
    with pytest.raises(JaError, match="ends inside a block"):
        expand_cfil(cfil_copy(BIG)[:-10])


def test_a_stream_ending_inside_its_header_is_refused():
    with pytest.raises(JaError, match="ends inside its CFIL header"):
        expand_cfil(CFIL_MAGIC)


def test_a_stream_with_an_empty_block_is_refused():
    stream = CFIL_MAGIC + struct.pack("<II", CFIL_VERSION, 4) + struct.pack("<H", 0)
    with pytest.raises(JaError, match="empty block"):
        expand_cfil(stream)


# ---------------------------------------------------------------------------
# reading an archive
# ---------------------------------------------------------------------------

def test_lists_every_member_in_index_order(ja_file):
    archive = read_ja(ja_file)
    assert len(archive) == 4
    assert archive.names() == [
        "config.chump",
        "sounds/beep.wav",
        "sounds/loop/beep2.wav",
        "license.txt",
    ]
    assert "sounds/beep.wav" in archive
    assert "nope.txt" not in archive


def test_reports_its_format_as_the_archiver_version(ja_file):
    archive = read_ja(ja_file)
    assert archive.version == 0x102
    assert archive.format_label == "ja 1.2"
    assert archive.build_version == 43208
    assert archive.product_code == 2


def test_an_older_archive_is_labelled_as_such(tmp_path):
    path = tmp_path / "old.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], version=0x101))
    assert read_ja(path).format_label == "ja 1.1"


def test_index_rows_carry_sizes_offsets_and_flags(ja_file):
    archive = read_ja(ja_file)
    stored, packed, copied, tiny = archive.entries
    assert (stored.name, stored.size, stored.compressed) == ("config.chump", len(SMALL), False)
    assert stored.flags == FLAG_STORED
    assert packed.size == len(BIG) and packed.compressed and packed.flags == FLAG_COMPRESSED
    assert packed.stored_size == len(cfil_bpe(BIG))
    assert copied.size == len(BIG) and copied.compressed
    assert tiny.size == len(b"read me\n")
    # the stored offset really does point at the file's own bytes
    with ja_file.open("rb") as handle:
        handle.seek(stored.offset)
        assert handle.read(len(SMALL)) == SMALL


def test_read_returns_the_expanded_file(ja_file, members):
    archive = read_ja(ja_file)
    for name, contents in expected_contents(members).items():
        assert archive.read(name) == contents


def test_extract_writes_the_whole_tree(ja_file, tmp_path):
    dest = tmp_path / "out"
    read_ja(ja_file).extract(dest)
    written = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert written == {"config.chump", "sounds/beep.wav", "sounds/loop/beep2.wav", "license.txt"}
    assert (dest / "sounds" / "beep.wav").read_bytes() == BIG


def test_extract_one_file_without_its_folders(ja_file, tmp_path):
    target = read_ja(ja_file).extract_entry("sounds/loop/beep2.wav", tmp_path / "one")
    assert target.name == "beep2.wav"
    assert target.read_bytes() == BIG


def test_extract_a_folder_keeps_its_name_and_structure(ja_file, tmp_path):
    dest = read_ja(ja_file).extract_folder("sounds", tmp_path / "some")
    assert dest == tmp_path / "some" / "sounds"
    assert (dest / "beep.wav").read_bytes() == BIG
    assert (dest / "loop" / "beep2.wav").read_bytes() == BIG


def test_missing_members_are_reported(ja_file):
    archive = read_ja(ja_file)
    with pytest.raises(JaError, match="nope.txt is not in this archive"):
        archive.read("nope.txt")
    with pytest.raises(JaError, match="nope.txt is not in this archive"):
        archive.extract_entry("nope.txt", ja_file.parent)
    with pytest.raises(JaError, match="folder nope is not in this archive"):
        archive.extract_folder("nope", ja_file.parent)


def test_names_climbing_out_of_the_folder_are_refused(tmp_path):
    path = tmp_path / "evil.ja"
    path.write_bytes(build_ja([member("../evil.txt", SMALL)]))
    with pytest.raises(JaError, match="unsafe file name in archive"):
        read_ja(path).extract(tmp_path / "out")


def test_checksums_match_the_contents(ja_file):
    archive = read_ja(ja_file)
    assert archive.verify("config.chump")
    assert archive.verify("sounds/beep.wav")


# ---------------------------------------------------------------------------
# damaged and unsupported files
# ---------------------------------------------------------------------------

def test_another_format_is_named_by_its_path(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"just a text file")
    with pytest.raises(JaError) as caught:
        read_ja(path)
    assert str(caught.value) == f"File format not supported for {path}"


def test_a_wrong_archive_id_is_refused(tmp_path):
    path = tmp_path / "other.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], archive_id=0x41524331))
    with pytest.raises(JaError, match="is not a Jet Archive"):
        read_ja(path)


@pytest.mark.parametrize("version", [0x100, 0x103, 0x200])
def test_an_unknown_archive_version_is_refused(tmp_path, version):
    path = tmp_path / "new.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], version=version))
    with pytest.raises(JaError, match=f"Jet Archive version {version:#x} is not supported"):
        read_ja(path)


def test_a_short_info_chunk_is_refused(tmp_path):
    path = tmp_path / "short.ja"
    path.write_bytes(b"ARCHINFO" + struct.pack("<I", 8) + b"\0" * 8)
    with pytest.raises(JaError, match="short INFO chunk"):
        read_ja(path)


def test_a_missing_info_chunk_is_refused(tmp_path):
    path = tmp_path / "noinfo.ja"
    path.write_bytes(b"ARCHFIL " + struct.pack("<I", 288) + b"\0" * 288)
    with pytest.raises(JaError, match="has no INFO chunk"):
        read_ja(path)


def test_an_index_outside_the_file_is_refused(tmp_path):
    good = build_ja([member("a.txt", SMALL)])
    path = tmp_path / "badindex.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], index_offset=len(good) + 999))
    with pytest.raises(JaError, match="points its index outside the file"):
        read_ja(path)


def test_an_index_in_the_wrong_place_is_refused(tmp_path):
    path = tmp_path / "shifted.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], index_offset=12))
    with pytest.raises(JaError, match="has no IDX chunk where its header says"):
        read_ja(path)


def test_a_file_count_that_does_not_match_the_index_is_refused(tmp_path):
    path = tmp_path / "miscounted.ja"
    path.write_bytes(build_ja([member("a.txt", SMALL)], count=7))
    with pytest.raises(JaError, match="counts 7 files but indexes 1"):
        read_ja(path)


def test_a_part_index_row_is_refused(tmp_path):
    data = bytearray(build_ja([member("a.txt", SMALL)]))
    struct.pack_into("<I", data, index_at(data) + 4, IDX_ENTRY_SIZE - 3)
    path = tmp_path / "part.ja"
    path.write_bytes(data)
    with pytest.raises(JaError, match="not a whole number of entries"):
        read_ja(path)


def test_an_empty_file_name_is_refused(tmp_path):
    path = tmp_path / "noname.ja"
    path.write_bytes(build_ja([member("", SMALL)]))
    with pytest.raises(JaError, match="empty file name"):
        read_ja(path)


def test_data_pointing_past_the_file_end_is_refused(tmp_path):
    data = bytearray(build_ja([member("a.txt", SMALL)]))
    struct.pack_into("<I", data, index_at(data) + 8 + 4, 10**6)
    path = tmp_path / "beyond.ja"
    path.write_bytes(data)
    with pytest.raises(JaError, match="a.txt points outside the file"):
        read_ja(path)


def test_a_stored_member_that_stops_mid_copy_is_reported(ja_file):
    """An index row promising more bytes than the archive holds."""
    entry = JaEntry("gone.bin", 10, 10**9, 0, FLAG_STORED, 0)
    with pytest.raises(JaError, match="gone.bin is truncated in the archive"):
        JaArchive(ja_file, entries=[entry]).read("gone.bin")


def test_a_compressed_member_that_stops_mid_stream_is_reported(tmp_path):
    """The CFIL header promises far more than the stored bytes can expand to."""
    stream = cfil_bpe(BIG)
    stream = CFIL_MAGIC + struct.pack("<II", CFIL_VERSION, 5 * len(BIG)) + stream[12:]
    broken = Member("big.bin", stream, FLAG_COMPRESSED, plain(stream))
    path = tmp_path / "half.ja"
    path.write_bytes(build_ja([broken]))
    with pytest.raises(JaError, match="ends inside"):
        read_ja(path).read("big.bin")


# ---------------------------------------------------------------------------
# format picking
# ---------------------------------------------------------------------------

def test_open_archive_picks_the_jet_reader(ja_file):
    archive = open_archive(ja_file)
    assert isinstance(archive, JaArchive)
    assert archive.format_label == "ja 1.2"


def test_open_archive_still_reads_tzarc_files(tmp_path):
    from tzarchiver.tzarc import Archive, Entry

    path = tmp_path / "plain.tzarc"
    Archive(version=1, entries=[Entry("a.txt", 2)], contents=[b"hi"]).write(path)
    assert open_archive(path).read("a.txt") == b"hi"


def test_open_archive_refuses_anything_else(tmp_path):
    path = tmp_path / "mystery.bin"
    path.write_bytes(b"\0" * 64)
    with pytest.raises(ArchiveError) as caught:
        open_archive(path)
    assert str(caught.value) == f"File format not supported for {path}"


def test_an_archive_named_tzarc_is_still_read_as_a_jet_archive(tmp_path):
    """The magic bytes decide, so a renamed archive keeps working."""
    path = tmp_path / "Data.tzarc"
    path.write_bytes(build_ja([member("a.txt", SMALL)]))
    assert open_archive(path).format_label == "ja 1.2"


# ---------------------------------------------------------------------------
# against a real archive, when one is at hand
# ---------------------------------------------------------------------------

#: point this at a built-in archive (e.g. ``D:\\Games\\TS12\\Base.ja``) to run
#  the checks that need the real thing; they are skipped otherwise
SAMPLE = os.environ.get("TZARCHIVER_JA_SAMPLE", "")


@pytest.mark.skipif(not SAMPLE, reason="needs TZARCHIVER_JA_SAMPLE=<a real .ja>")
def test_a_real_archive_is_listed_extracted_and_checksummed(tmp_path):
    archive = read_ja(SAMPLE)
    assert archive.format_label in {"ja 1.1", "ja 1.2"}
    assert len(archive) > 0
    assert all(entry.name and entry.size for entry in archive.entries)

    by_size = sorted(archive.entries, key=lambda entry: entry.size)
    for entry in by_size[:5]:
        assert archive.verify(entry.name), entry.name
    for entry in by_size[-3:]:  # the big ones: only the length, the CRC is slow
        assert len(archive.read(entry.name)) == entry.size, entry.name
    for entry in by_size[:3] + by_size[-3:]:
        target = archive.extract_entry(entry.name, tmp_path)
        assert target.stat().st_size == entry.size
