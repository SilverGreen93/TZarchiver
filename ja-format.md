# Jet Archive file specification (\*.ja)

Used by older Trainz versions (TRS2004, TS2010) for built-in content, e.g. `TS2010SP3/Builtin/1.ja`..`8.ja`. Written by Auran's "Jet Archiver" (`bin/JAConverter.exe`, "Jet Archiver v1.9 - Copyright 2001 Auran Pty Ltd"). Read by third-party tools such as JAX (`jax.exe`).

All integers are **little endian**, unless noted otherwise.

## Overall layout

The file is a 4-byte magic followed by a sequence of chunks. Each chunk is:

* 4 bytes: Chunk tag (ASCII) => e.g. `FIL ` (note the trailing space)
* 4 bytes: Chunk data length, not including these 8 bytes => e.g. AC 84 00 00 (33964 bytes)
* Chunk data

The order is:

* 4 bytes: File ID => `ARCH`
* `INFO` chunk (archive header), length always 32
* For Each file contained in the archive:
  * `FIL ` chunk
* End For
* `IDX ` chunk (index), always the last chunk

## INFO chunk (archive header)

The 32 data bytes:

* 4 bytes: Archive ID => 30 43 52 41 (the four-character constant `'ARC0'` stored as a little endian integer, so it reads `0CRA` in a hex editor)
* 4 bytes: Version => 02 01 00 00 (0x102). The reader accepts 0x101 to 0x102
* 4 bytes: How many files it contains => e.g. 15 6A 00 00 (27157 files)
* 4 bytes: Absolute file offset of the `IDX ` chunk tag => e.g. 7A 59 51 38
* 4 bytes: Build version => C8 A8 00 00 (43208, from the `-sbuildversion=` switch)
* 4 bytes: Product code => 02 00 00 00 (2, from the `-sproductcode=` switch)
* 8 bytes: Reserved => 00 00 00 00 00 00 00 00

## FIL chunk (one per file)

* 260 bytes: File name, null terminated (a `MAX_PATH` buffer). The bytes after the terminator are **not** zeroed: the writer leaves uninitialized memory there, so ignore everything after the first `00`
* 4 bytes: File size (uncompressed length)
* 4 bytes: Stored size (length of the data that follows)
* 4 bytes: Checksum of the uncompressed file contents (see [Checksum](#checksum))
* 12 bytes: Reserved => all 00
* 4 bytes: Flags => 80 00 00 00 = stored as a `CFIL` stream (compressed), 00 00 00 00 = stored as is
* Stored size bytes: File data. If the flags are 0, this is the file contents byte by byte, and stored size = file size. If the flags are 0x80, this is a `CFIL` stream (see below)

So the FIL header is 288 bytes, and the chunk length is 288 + stored size.

File names in the TS2010 archives are relative paths with `/` as the separator, all lowercase, ASCII, e.g. `hash-c1/kuid 191576 2430/config.chump` (the same `hash-XX/kuid ...` layout as the local content folders). The entries are **not** sorted alphabetically.

## IDX chunk (index)

The data is an array of 296-byte entries, one per file, in the same order as the `FIL ` chunks. Data length = file count × 296.

* For Each file:
  * 4 bytes: Absolute file offset of the file data (the first byte after the 288-byte FIL header)
  * 4 bytes: Stored size
  * 288 bytes: Exact copy of the FIL header (name, sizes, checksum, reserved, flags)
* End For

A reader can find a file without scanning the chunks: seek to the IDX offset from `INFO`, read the index, then seek to the data offset. When the archiver adds files, it overwrites the old index with the new `FIL ` chunks and writes a new index at the end.

## Checksum

**CRC-32/BZIP2** of the uncompressed file contents: polynomial 0x04C11DB7, not reflected (MSB first), initial value 0xFFFFFFFF, final XOR 0xFFFFFFFF. This is *not* the same as the usual zlib CRC-32 (which is the reflected variant).

```text
crc = 0xFFFFFFFF
For Each byte b:
  crc = ((crc << 8) & 0xFFFFFFFF) XOR table[(crc >> 24) XOR b]
crc = crc XOR 0xFFFFFFFF
```

(table[i] = CRC of the single byte i, shifted left 24 bits, using the polynomial above; table[1] = 0x04C11DB7.)

Note: the JAConverter.exe in TS2010SP3 only updates the CRC on the compression path, so uncompressed files it adds get a checksum of 0. The shipped archives have correct CRCs for both stored and compressed files, so write the real CRC in both cases.

## CFIL stream (compressed file data)

The same container is used by Trainz for stand-alone compressed files (JAX calls them `*.cfil`).

* 4 bytes: ID => `CFIL`
* 4 bytes: Version => 01 01 00 00 (0x101)
* 4 bytes: Uncompressed size (same as the FIL file size)
* For Each block, until the uncompressed size is reached:
  * 2 bytes: Block header (unsigned 16 bit)
    * If bit 15 is set (0x8000): stored block. The next (header AND 0x7FFF) bytes are copied as is
    * Otherwise: compressed block. The next (header) bytes are byte pair encoded data
  * Block data
* End For

The writer reads the input in pieces of 16384 (0x4000) bytes and makes one block from each piece, so every block except the last one expands to exactly 16384 bytes. If compression does not make a piece smaller, it is written as a stored block instead (e.g. JPEG files: `00 C0` = stored, 16384 bytes).

### Byte pair encoding (BPE)

The compression is Philip Gage's Byte Pair Encoding ("A New Algorithm for Data Compression", C Users Journal, 1994), with one change in the pair table (see below). A compressed block holds one or more BPE packets back to back; decode packets until the block's data is used up. The writer puts at most 2048 (0x800) bytes of input into one packet, so a 16 KiB block usually holds 8 packets.

Each packet is a pair table, a length, and the packed bytes:

**Pair table.** Start with `left[c] = c` for c = 0..255 (each byte stands for itself), and `c = 0`. While `c < 256`:

* 1 byte: count
* If count > 127: skip, `c = c + (count - 127)`. Go back to reading a count byte.
* Else: the next (count + 1) entries follow. For each one:
  * 1 byte: `left[c]`
  * If `left[c] != c`: 1 byte: `right[c]` (byte c stands for the pair `left[c] right[c]`)
  * `c = c + 1`

Difference from Gage's original: in the original, after a skip, one entry is read right away (the skip is followed by an implied count of 0). In the Jet Archiver version (and JAX), a skip is always followed by a new count byte. Using the original decoder on these files gives wrong output.

**Length.** 2 bytes: number of packed bytes, **big endian**.

**Packed bytes.** Expand each packed byte with a stack:

```text
For Each packed byte b:
  push b
  While the stack is not empty:
    c = pop
    If left[c] == c: output c
    Else: push right[c], then push left[c]
```

Then the next packet starts (with a fresh pair table) if the block has bytes left.

## Differences from TZarc

|   | `.tzarc` | `.ja` |
| - | - | - |
| Magic | `TZac` | `ARCH` + `INFO` chunk (`ARC0`) |
| Byte order | Big endian (v2 compression header is little endian) | Little endian (BPE packet length is big endian) |
| Structure | Header, name table, then contents | Chunks (`FIL ` per file, `IDX ` at the end) |
| File name | 1-byte length + name (up to 255 bytes) | Fixed 260-byte, null terminated buffer |
| File size | 8 bytes (64 bit) | 4 bytes (32 bit) |
| Order | Alphabetical | Not sorted |
| Per-file checksum | None | CRC-32/BZIP2 of contents |
| Random value | 4 bytes, per archive | None (build version and product code instead) |
| Compression | Whole body, zlib, 65000-byte chunks | Per file, Byte Pair Encoding, 16 KiB blocks, optional per file and per block |
| Random access | No (must read the name table and add up sizes) | Yes, through the `IDX ` chunk offsets |
| Content | Paths as on the filesystem | Many assets, under `hash-XX/kuid ...` folders |
