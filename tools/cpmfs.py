#!/usr/bin/env python3
"""Minimal CP/M 2.2 filesystem reader/writer.

Driven by the same disk_geometry.Geometry the BIOS uses, so directory
layout, block size and reserved tracks can never drift from the Z80 side.
Supports the three shapes this project needs:

- D88CpmAdapter: an FD drive inside a d88 image (256B sectors, one CP/M
  track per physical (cylinder, side)).
- FlatCpmAdapter: a byte-addressable area (EMM image, SASI partition).

Only the features the project needs: format, add_file, read_file, ls.
User areas other than 0 and timestamps are out of scope (CP/M 2.2 has no
timestamps anyway).
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from disk_geometry import Geometry  # noqa: E402

RECORD = 128
ENTRY_SIZE = 32
EMPTY = 0xE5
LOGICAL_EXTENT_RECORDS = 128  # 16KB


class D88CpmAdapter:
    """CP/M track/record access onto a d88 FD image (16 x 256B per track)."""

    def __init__(self, image, geometry: Geometry):
        self.image = image
        self.geometry = geometry

    def read_record(self, track: int, rec: int) -> bytes:
        lba = track * 16 + rec // 2
        sector = self.image.read_sector(lba)
        offset = (rec % 2) * RECORD
        return sector[offset:offset + RECORD]

    def write_record(self, track: int, rec: int, data: bytes) -> None:
        lba = track * 16 + rec // 2
        sector = bytearray(self.image.read_sector(lba))
        offset = (rec % 2) * RECORD
        sector[offset:offset + RECORD] = data
        self.image.write_sector(lba, bytes(sector))


class FlatCpmAdapter:
    """CP/M track/record access onto a flat byte array (EMM/SASI)."""

    def __init__(self, buffer: bytearray, geometry: Geometry, base: int = 0):
        self.buffer = buffer
        self.geometry = geometry
        self.base = base

    def _offset(self, track: int, rec: int) -> int:
        return self.base + (track * self.geometry.spt + rec) * RECORD

    def read_record(self, track: int, rec: int) -> bytes:
        o = self._offset(track, rec)
        return bytes(self.buffer[o:o + RECORD])

    def write_record(self, track: int, rec: int, data: bytes) -> None:
        o = self._offset(track, rec)
        self.buffer[o:o + RECORD] = data


@dataclasses.dataclass
class DirEntry:
    user: int
    name: str          # "NAME.EXT"
    extent: int        # logical extent index of this entry's base
    records: int       # records in this entry
    blocks: list[int]


def _pack_name(name: str) -> bytes:
    stem, _, ext = name.upper().partition(".")
    if len(stem) > 8 or len(ext) > 3 or not stem:
        raise ValueError(f"not a valid 8.3 name: {name!r}")
    return stem.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")


class CpmFilesystem:
    def __init__(self, adapter):
        self.adapter = adapter
        self.g: Geometry = adapter.geometry
        self.records_per_block = self.g.bls // RECORD
        self.wide = self.g.dsm >= 256      # 16-bit allocation entries
        self.pointers = 8 if self.wide else 16
        self.entry_records = (self.g.exm + 1) * LOGICAL_EXTENT_RECORDS
        self.dir_entries = self.g.drm + 1
        self.dir_records = (self.dir_entries * ENTRY_SIZE + RECORD - 1) // RECORD

    # --- raw record helpers inside the data area ---------------------
    def _rw_abs(self, record: int, data: bytes | None):
        track = self.g.off + record // self.g.spt
        rec = record % self.g.spt
        if data is None:
            return self.adapter.read_record(track, rec)
        self.adapter.write_record(track, rec, data)
        return None

    def _block_record(self, block: int, index: int, data: bytes | None):
        return self._rw_abs(block * self.records_per_block + index, data)

    # --- directory ----------------------------------------------------
    def _read_dir_raw(self) -> bytearray:
        raw = bytearray()
        for r in range(self.dir_records):
            raw += self._rw_abs(r, None)
        return raw

    def _write_dir_raw(self, raw: bytes) -> None:
        for r in range(self.dir_records):
            self._rw_abs(r, raw[r * RECORD:(r + 1) * RECORD])

    def format(self) -> None:
        empty = bytes([EMPTY]) * RECORD
        for r in range(self.dir_records):
            self._rw_abs(r, empty)

    def _parse_entry(self, raw: bytes) -> DirEntry | None:
        user = raw[0]
        if user == EMPTY or user > 15:
            return None
        stem = bytes(b & 0x7F for b in raw[1:9]).decode("ascii", "replace").rstrip()
        ext = bytes(b & 0x7F for b in raw[9:12]).decode("ascii", "replace").rstrip()
        name = f"{stem}.{ext}" if ext else stem
        ex, s2, rc = raw[12], raw[14], raw[15]
        extent_index = ((s2 & 0x3F) << 5) | (ex & 0x1F)
        if self.wide:
            blocks = [int.from_bytes(raw[16 + i * 2:18 + i * 2], "little")
                      for i in range(8)]
        else:
            blocks = list(raw[16:32])
        blocks = [b for b in blocks if b != 0]
        base_extent = (extent_index // (self.g.exm + 1)) * (self.g.exm + 1)
        records = (extent_index - base_extent) * LOGICAL_EXTENT_RECORDS + rc
        return DirEntry(user, name, base_extent, records, blocks)

    def ls(self) -> dict[str, int]:
        """name -> total records (user 0 only)."""
        raw = self._read_dir_raw()
        totals: dict[str, int] = {}
        for i in range(self.dir_entries):
            entry = self._parse_entry(raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
            if entry is None or entry.user != 0:
                continue
            totals[entry.name] = totals.get(entry.name, 0) + entry.records
        return totals

    def _used_blocks(self) -> set[int]:
        used = set(range((self.dir_records + self.records_per_block - 1)
                         // self.records_per_block))
        raw = self._read_dir_raw()
        for i in range(self.dir_entries):
            entry = self._parse_entry(raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
            if entry:
                used.update(entry.blocks)
        return used

    def add_file(self, name: str, data: bytes, user: int = 0) -> None:
        packed = _pack_name(name)
        raw = self._read_dir_raw()
        # refuse duplicates: CP/M would show both
        for i in range(self.dir_entries):
            e = raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
            if e[0] == user and e[1:12] == packed:
                raise ValueError(f"{name} already present")

        padded = data + b"\x1a" * ((-len(data)) % RECORD) if data else b""
        records = [padded[i:i + RECORD] for i in range(0, len(padded), RECORD)]
        total_records = len(records)

        used = self._used_blocks()
        free = [b for b in range(self.g.dsm + 1) if b not in used]
        blocks_needed = (total_records + self.records_per_block - 1) \
            // self.records_per_block
        if blocks_needed > len(free):
            raise ValueError(f"disk full adding {name}")
        allocation = free[:blocks_needed]

        # write data records
        for idx, rec in enumerate(records):
            block = allocation[idx // self.records_per_block]
            self._block_record(block, idx % self.records_per_block, rec)

        # build directory entries
        free_slots = [i for i in range(self.dir_entries)
                      if raw[i * ENTRY_SIZE] == EMPTY]
        entry_index = 0
        rec_done = 0
        while rec_done < max(total_records, 1):
            recs_here = min(self.entry_records, total_records - rec_done)
            if total_records == 0:
                recs_here = 0
            if not free_slots:
                raise ValueError(f"directory full adding {name}")
            slot = free_slots.pop(0)
            entry = bytearray([EMPTY]) * ENTRY_SIZE
            entry = bytearray(ENTRY_SIZE)
            entry[0] = user
            entry[1:12] = packed
            base_extent = entry_index * (self.g.exm + 1)
            last_extent_offset = 0 if recs_here == 0 \
                else (recs_here - 1) // LOGICAL_EXTENT_RECORDS
            extent_index = base_extent + last_extent_offset
            entry[12] = extent_index & 0x1F
            entry[13] = 0
            entry[14] = (extent_index >> 5) & 0x3F
            rc = recs_here - last_extent_offset * LOGICAL_EXTENT_RECORDS
            entry[15] = rc
            first_block = (rec_done // self.records_per_block)
            blocks_here = allocation[
                first_block:first_block
                + (recs_here + self.records_per_block - 1) // self.records_per_block]
            if self.wide:
                for i, b in enumerate(blocks_here[:8]):
                    entry[16 + i * 2:18 + i * 2] = b.to_bytes(2, "little")
            else:
                for i, b in enumerate(blocks_here[:16]):
                    entry[16 + i] = b
            raw[slot * ENTRY_SIZE:(slot + 1) * ENTRY_SIZE] = entry
            rec_done += max(recs_here, 1)
            entry_index += 1
        self._write_dir_raw(raw)

    def read_file(self, name: str, user: int = 0) -> bytes:
        packed = _pack_name(name)
        raw = self._read_dir_raw()
        pieces: list[tuple[int, int, list[int]]] = []
        for i in range(self.dir_entries):
            e = raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
            if e[0] != user or e[1:12] != packed:
                continue
            parsed = self._parse_entry(e)
            pieces.append((parsed.extent, parsed.records, parsed.blocks))
        if not pieces:
            raise FileNotFoundError(name)
        pieces.sort()
        data = b""
        for _, records, blocks in pieces:
            chunk = b""
            for r in range(records):
                block = blocks[r // self.records_per_block]
                chunk += self._block_record(block, r % self.records_per_block, None)
            data += chunk
        return data


def _cli() -> int:
    """cpmfs.py ls <image.d88>  - list drive A: of a CP/M boot floppy."""
    import argparse
    import disk_geometry as dg
    from d88 import D88Image

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["ls"])
    parser.add_argument("image")
    args = parser.parse_args()
    image = D88Image(pathlib.Path(args.image).read_bytes())
    fs = CpmFilesystem(D88CpmAdapter(image, dg.FD))
    for name, records in sorted(fs.ls().items()):
        print(f"{name:<12} {records * RECORD:>7} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
