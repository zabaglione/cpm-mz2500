#!/usr/bin/env python3
"""Build the SASI hard-disk image: EH-SASI partition table + CP/M drives.

Canonical geometry: 87,648 x 256-byte blocks (22,437,888 bytes - the
MZ-1E30/MZ-1F23 image size; pass --hdf-block 256 when mounting, the
emulator's auto heuristic reads this size as a 1024-byte RaSCSI image).

Partition table (ID0/LUN0/LAD 0x000003, verified against the EH-SASI
sources and the ROM's own default table):
  +000..00F  signature "EHSASI 20220510"+00h (the ROM compares it against
             its MISC overlay bytes at ROM offset 0x0B01)
  +010+16*n  entry: CTRL(bit7=priority boot, bits2..0=drive number),
             CAPACITY hi,lo (blocks), SASI-ID,
             TOP-LUN(<<5),TOP-LAD hi,mid,lo, SAFE-LUN,SAFE-LAD hi,mid,lo
             (all zero = no retract), 4 reserved

Layout here: HD1 = CP/M C: at LBA 32, HD2 = CP/M D: at LBA 32+32768,
both 32768 blocks (8MB), no priority boot yet (that is the M4 milestone).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import disk_geometry as dg  # noqa: E402
import cpmfs  # noqa: E402

TOTAL_BLOCKS = 87648
BLOCK = 256
SIGNATURE = b"EHSASI 20220510\x00"
TABLE_LBA = 3


def partition_entry(ctrl: int, capacity: int, sasi_id: int, lun: int,
                    top_lad: int, safe_lad: int | None) -> bytes:
    entry = bytearray(16)
    entry[0] = ctrl
    entry[1] = (capacity >> 8) & 0xFF
    entry[2] = capacity & 0xFF
    # The ID field is a BIT MASK (0x01 << id), not the id number - a zero
    # here reads as "no target" and the entry is treated as inactive.
    entry[3] = 1 << sasi_id
    entry[4] = (lun & 7) << 5
    entry[5] = (top_lad >> 16) & 0xFF
    entry[6] = (top_lad >> 8) & 0xFF
    entry[7] = top_lad & 0xFF
    if safe_lad is not None:
        entry[8] = (lun & 7) << 5
        entry[9] = (safe_lad >> 16) & 0xFF
        entry[10] = (safe_lad >> 8) & 0xFF
        entry[11] = safe_lad & 0xFF
    return bytes(entry)


def write_boot_area(image: bytearray) -> bool:
    """Make HD1 bootable through the device-boot contract (measured):
    the IPL reads the IPLPRO record at partition record 0, then one
    contiguous READ of banks*32 records starting at the record named by
    header offset +1E (16): bank06 image at records 16..47, bank07 at
    48..79. The bank07 copy gets boot_drive_default patched to 2 so the
    booted system lands on C: instead of an empty floppy."""
    import json
    import make_boot_d88
    build_dir = PROJECT / "build"
    b06 = build_dir / "cpm_bank06.bin"
    b07 = build_dir / "cpm_bank07.bin"
    layout_file = build_dir / "cpm_layout.json"
    if not (b06.is_file() and b07.is_file() and layout_file.is_file()):
        print("note: bank images missing (run make_boot_d88.py first) - "
              "building a data-only image")
        return False
    layout = json.loads(layout_file.read_text())
    bank06 = b06.read_bytes()
    bank07 = bytearray(b07.read_bytes())
    bank07[layout["boot_drive_default"] - 0xE000] = 2  # boot to C:

    base = dg.SASI_BASE_C * BLOCK
    image[base:base + BLOCK] = make_boot_d88.make_ipl_header()
    image[base + 16 * BLOCK:base + 48 * BLOCK] = bank06
    image[base + 48 * BLOCK:base + 80 * BLOCK] = bank07
    return True


def build(output: pathlib.Path, with_files: bool, bootable: bool) -> None:
    image = bytearray(TOTAL_BLOCKS * BLOCK)

    boot_ok = bootable and write_boot_area(image)

    table = bytearray(BLOCK)
    table[0:16] = SIGNATURE
    hd1_ctrl = 0x81 if boot_ok else 0x01   # priority boot only when bootable
    table[0x10:0x20] = partition_entry(hd1_ctrl, dg.SASI_PARTITION_BLOCKS, 0, 0,
                                       dg.SASI_BASE_C, None)
    table[0x20:0x30] = partition_entry(0x02, dg.SASI_PARTITION_BLOCKS, 0, 0,
                                       dg.SASI_BASE_D, None)
    image[TABLE_LBA * BLOCK:(TABLE_LBA + 1) * BLOCK] = table

    for base, inject in ((dg.SASI_BASE_C, with_files), (dg.SASI_BASE_D, False)):
        fs = cpmfs.CpmFilesystem(
            cpmfs.FlatCpmAdapter(image, dg.SASI, base=base * BLOCK))
        fs.format()
        if inject:
            vendor = PROJECT / "vendor" / "cpm22" / "bin"
            for name in ("PIP.COM", "STAT.COM", "ED.COM", "ASM.COM",
                         "DDT.COM", "SUBMIT.COM", "DUMP.COM", "LOAD.COM",
                         "XSUB.COM"):
                path = vendor / name
                if path.is_file():
                    fs.add_file(name, path.read_bytes())
            putsys = PROJECT / "build" / "putsys.com"
            if putsys.is_file():
                fs.add_file("PUTSYS.COM", putsys.read_bytes())

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    print(f"wrote {output} ({len(image)} bytes, HD1 ctrl={hd1_ctrl:#04x}, "
          f"bootable={boot_ok})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(PROJECT / "build" / "cpm.hdd"))
    parser.add_argument("--no-files", action="store_true",
                        help="leave C: empty instead of injecting DRI tools")
    parser.add_argument("--no-boot", action="store_true",
                        help="data-only image (no boot area, no priority)")
    args = parser.parse_args()
    build(pathlib.Path(args.output), not args.no_files, not args.no_boot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
