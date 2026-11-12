# Trainz Archive file specification (\*.tzarc)

## File header

* 4 bytes: File ID => TZac
* 4 bytes: version => 00 00 00 01 (version 1 - uncompressed, version 2 - compressed)
* 4 bytes: How many files it contains => 00 00 00 02 (2 files)

## File contents

* For Each file contained in the archive (listed alphabetically):
  * 1 byte: Filename length => e.g. 0C (12 characters)
  * max 255 bytes: File name => e.g. config.chump (name from the filesystem, including subfolder if any)
  * 8 bytes: File size (length) => e.g. 00 00 00 00 00 00 00 23 (35 bytes)
* End For
* 4 bytes: random value (unique per archive, not derived from contents, time or KUID hash)
* For Each file:
  * max 2^64-1 bytes: File contents as it is, byte by byte.
* End For

## Version 2 (compressed)

The header starts the same way (`TZac`, then the version `00 00 00 02`). Everything after that is a version 1 body, beginning at the file count field, split into chunks of 65000 bytes (the last one may be shorter). Each chunk is compressed separately with **zlib** (RFC 1950: 2-byte header such as `78 9C`, deflate data, Adler-32).

Unlike the rest of the format, these fields are **little endian**:

* 8 bytes: Total uncompressed size of the v1 body => e.g. 2E 01 1F 00 00 00 00 00 (2031918 bytes)
* 4 bytes: Number of compressed blocks => e.g. 20 00 00 00 (32 blocks)
* For Each block:
  * 2 bytes: Compressed block size minus 1 => e.g. 85 03 (902 bytes)
* End For
* For Each block:
  * zlib stream of the given compressed size
* End For

Decompress all the blocks, join them, and parse the result as a version 1 file from the "How many files" field onward.
