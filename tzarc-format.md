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
* 4 bytes: Random time data (?)
* For Each file:
  * max 2^64-1 bytes: File contents as it is, byte by byte.
* End For
