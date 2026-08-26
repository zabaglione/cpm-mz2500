#!/usr/bin/env python3
"""Build a personal "In The Dark" boot floppy for the MZ-2500 CP/M port.

In The Dark (Kian Ryan, 2022, MIT license) is a generative dungeon
crawler for CP/M with an ANSI terminal - exactly what the BIOS console's
VT100 subset provides. The author's released binary is fetched onto YOUR
machine (SHA256-pinned) and combined with the CP/M boot floppy; nothing
is redistributed by this project.

Needs only Python 3: without a local CP/M build the released boot disk
is downloaded instead, so no assembler is required.

Boot the result and type ITDARK80 at the A> prompt. Move with w/a/s/d,
quit with q. Upstream: https://github.com/kianryan/InTheDark
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.request

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import cpmfs  # noqa: E402
import disk_geometry as dg  # noqa: E402
from d88 import D88Image  # noqa: E402

VENDOR = PROJECT / "vendor" / "inthedark"
URL = ("https://github.com/kianryan/InTheDark/releases/download/"
       "0.1/itdark80.com")
SHA256 = "52798190a58b1975b8883991b59cdbad46ca246e8782c2be23b4887993dc85f3"
# without a local build (no z80asm needed), the released boot disk is used
BOOT_URL = ("https://github.com/zabaglione/cpm-mz2500/releases/download/"
            "v1.2.0/cpm_boot.d88")
BOOT_SHA256 = "682a2c02868964f464d84d69a702d2c384cbc656403f86fe178723f075fdf59a"


def fetch_pinned(url: str, digest: str) -> bytes:
    blob = urllib.request.urlopen(url, timeout=120).read()
    if hashlib.sha256(blob).hexdigest() != digest:
        raise SystemExit(f"SHA256 mismatch for {url}")
    return blob


def boot_disk() -> pathlib.Path:
    boot = PROJECT / "build" / "cpm_boot.d88"
    if boot.is_file():
        return boot
    print("no local CP/M build - downloading the released boot disk...")
    boot.parent.mkdir(parents=True, exist_ok=True)
    boot.write_bytes(fetch_pinned(BOOT_URL, BOOT_SHA256))
    return boot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",
                        default=str(PROJECT / "build" / "inthedark.d88"))
    args = parser.parse_args()

    boot = boot_disk()
    game = VENDOR / "ITDARK80.COM"
    if not game.is_file():
        VENDOR.mkdir(parents=True, exist_ok=True)
        game.write_bytes(fetch_pinned(URL, SHA256))
        print(f"fetched In The Dark 0.1 into {VENDOR}")

    image = D88Image(bytearray(boot.read_bytes()))
    fs = cpmfs.CpmFilesystem(cpmfs.D88CpmAdapter(image, dg.FD))
    fs.add_file("ITDARK80.COM", game.read_bytes())

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image.data)
    print(f"wrote {output} (bootable; type ITDARK80 at the A> prompt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
