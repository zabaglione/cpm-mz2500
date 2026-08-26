#!/usr/bin/env python3
"""Build a personal Rogue boot floppy for the MZ-2500 CP/M port.

Rogue 1.7 (David Goodenough, 1985) carries no license statement, so the
binary is never bundled with a release. This script downloads the archive
preserved at The Rogue Archive onto YOUR machine and builds a bootable
disk for YOUR own use - nothing is redistributed by this project.

Steps:
1. fetch rogue17cpm.zip (SHA256-pinned) into vendor/rogue/
2. take ROGUE.CPM - installed for a Televideo TS803, whose escape codes
   (ADM-3A cursor addressing, ^Z clear, ESC T/Y/(/) extras) the MZ-2500
   BIOS console speaks natively
3. trim the terminal capability bitmap (addr 022Fh) to the codes the
   BIOS implements: dim/bright/clear-EOL/clear-EOS
4. add it to a copy of the CP/M boot floppy as ROGUE.COM, docs included

Boot the result - in the web emulator just drop it on the screen - and
type ROGUE at the A> prompt. Saves (ROGUE.SAV) land on the same disk.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import sys
import urllib.request
import zipfile

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import cpmfs  # noqa: E402
import disk_geometry as dg  # noqa: E402
from d88 import D88Image  # noqa: E402

VENDOR = PROJECT / "vendor" / "rogue"
URL = "https://britzl.github.io/roguearchive/files/rogue17cpm.zip"
SHA256 = "4249c0b771d0a9caa1ea9210ebef7e7a200c1b060a13199679cef8a7c62d9da5"
# rogue17cpm.zip nests rogue17.zip; these members go onto the disk
MEMBERS = ["ROGUE.CPM", "ROGUE.DOC", "ROGUE.NOT"]
CAP_BITMAP_OFFSET = 0x22F - 0x100   # terminal capability bitmap (addr 022Fh)
CAP_BITMAP_VALUE = 0xC3             # dim+bright+clear-EOL+clear-EOS only


def fetch() -> None:
    if all((VENDOR / m).is_file() for m in MEMBERS):
        return
    blob = urllib.request.urlopen(URL, timeout=120).read()
    if hashlib.sha256(blob).hexdigest() != SHA256:
        raise SystemExit(f"SHA256 mismatch for {URL}")
    outer = zipfile.ZipFile(io.BytesIO(blob))
    inner = zipfile.ZipFile(io.BytesIO(outer.read("rogue17.zip")))
    VENDOR.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        (VENDOR / member).write_bytes(inner.read(member))
    print(f"fetched Rogue 1.7 into {VENDOR}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(PROJECT / "build" / "rogue.d88"))
    args = parser.parse_args()

    boot = PROJECT / "build" / "cpm_boot.d88"
    if not boot.is_file():
        raise SystemExit(f"{boot} missing - build the CP/M boot disk first")
    fetch()

    rogue = bytearray((VENDOR / "ROGUE.CPM").read_bytes())
    rogue[CAP_BITMAP_OFFSET] = CAP_BITMAP_VALUE

    image = D88Image(bytearray(boot.read_bytes()))
    fs = cpmfs.CpmFilesystem(cpmfs.D88CpmAdapter(image, dg.FD))
    fs.add_file("ROGUE.COM", bytes(rogue))
    for name in ("ROGUE.DOC", "ROGUE.NOT"):
        fs.add_file(name, (VENDOR / name).read_bytes())

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image.data)
    print(f"wrote {output} (bootable; type ROGUE at the A> prompt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
