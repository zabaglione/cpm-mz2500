"""Minimal D88 sector and standalone IPL helpers for MZ-2500 tools."""

from __future__ import annotations


SECTOR_SIZE = 256
TRACK_COUNT = 160
SECTORS_PER_TRACK = 16
D88_TRACK_TABLE_ENTRIES = 164
D88_HEADER_SIZE = 0x2B0
D88_TRACK_SIZE = SECTORS_PER_TRACK * (16 + SECTOR_SIZE)
IPL_PAYLOAD_SIZE = 8192


class D88Image:
    """Read and update decoded 256-byte sectors in an MZ-2500 D88 image."""

    def __init__(self, data: bytearray) -> None:
        self.data = data
        self.track_offsets = [
            int.from_bytes(data[0x20 + index * 4 : 0x24 + index * 4], "little")
            for index in range(D88_TRACK_TABLE_ENTRIES)
        ]
        self.sector_positions: list[int] = []
        for track in range(TRACK_COUNT):
            offset = self.track_offsets[track]
            if offset == 0:
                raise ValueError(f"missing track {track}")
            position = offset
            for sector in range(SECTORS_PER_TRACK):
                size = int.from_bytes(self.data[position + 14 : position + 16], "little")
                if size != SECTOR_SIZE:
                    raise ValueError(
                        f"unexpected sector size at track {track} sector {sector + 1}: {size}"
                    )
                self.sector_positions.append(position)
                position += 16 + size

    def read_sector(self, lba: int) -> bytes:
        position = self.sector_positions[lba]
        return bytes(
            byte ^ 0xFF
            for byte in self.data[position + 16 : position + 16 + SECTOR_SIZE]
        )

    def write_sector(self, lba: int, decoded: bytes) -> None:
        if len(decoded) != SECTOR_SIZE:
            raise ValueError("decoded sector must be exactly 256 bytes")
        position = self.sector_positions[lba]
        self.data[position + 16 : position + 16 + SECTOR_SIZE] = bytes(
            byte ^ 0xFF for byte in decoded
        )

    def read_directory(self, entries: int = 64, entry_size: int = 32) -> bytearray:
        raw = bytearray()
        sector_count = (entries * entry_size) // SECTOR_SIZE
        for lba in range(sector_count):
            raw.extend(self.read_sector(lba))
        return raw

    def write_directory(self, raw: bytes) -> None:
        if len(raw) % SECTOR_SIZE:
            raise ValueError("directory data must be sector aligned")
        for lba, start in enumerate(range(0, len(raw), SECTOR_SIZE)):
            self.write_sector(lba, raw[start : start + SECTOR_SIZE])


def make_blank_d88(disk_name: str) -> D88Image:
    """Create a decoded, writable 2D MZ-2500 D88 image."""
    encoded_name = disk_name.encode("ascii")
    if len(encoded_name) > 16:
        raise ValueError("D88 disk name exceeds 16 ASCII bytes")

    data = bytearray(D88_HEADER_SIZE)
    data[0:17] = encoded_name + bytes(17 - len(encoded_name))
    data[0x1A] = 0
    data[0x1B] = 0x10
    for track in range(TRACK_COUNT):
        track_offset = D88_HEADER_SIZE + track * D88_TRACK_SIZE
        table_offset = 0x20 + track * 4
        data[table_offset : table_offset + 4] = track_offset.to_bytes(4, "little")
        cylinder = track // 2
        side = track & 1
        for sector in range(SECTORS_PER_TRACK):
            sector_header = bytearray(16)
            sector_header[0] = cylinder
            sector_header[1] = side
            sector_header[2] = sector + 1
            sector_header[3] = 1
            sector_header[4:6] = SECTORS_PER_TRACK.to_bytes(2, "little")
            sector_header[14:16] = SECTOR_SIZE.to_bytes(2, "little")
            data.extend(sector_header)
            data.extend(bytes([0xFF]) * SECTOR_SIZE)
    data[0x1C:0x20] = len(data).to_bytes(4, "little")
    return D88Image(data)


def write_raw_payload(image: D88Image, start_lba: int, payload: bytes) -> int:
    """Write a decoded payload and return its padded sector count."""
    sector_count = (len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE
    padded = payload + bytes(sector_count * SECTOR_SIZE - len(payload))
    for sector_index in range(sector_count):
        start = sector_index * SECTOR_SIZE
        image.write_sector(start_lba + sector_index, padded[start : start + SECTOR_SIZE])
    return sector_count


def write_ipl_payload(image: D88Image, payload: bytes) -> None:
    """Write the physical 8K IPL bank using the MZ-2500 sector ordering."""
    if len(payload) != IPL_PAYLOAD_SIZE:
        raise ValueError("IPL payload must fill exactly one 8K physical bank")
    for sector_index in range(16):
        start = sector_index * SECTOR_SIZE
        image.write_sector(sector_index, payload[start : start + SECTOR_SIZE])
    for sector_index in range(16):
        start = (16 + sector_index) * SECTOR_SIZE
        image.write_sector(32 + sector_index, payload[start : start + SECTOR_SIZE])
