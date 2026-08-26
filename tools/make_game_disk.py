#!/usr/bin/env python3
"""Build personal game boot floppies for the MZ-2500 CP/M port.

No game is bundled with any release: this script downloads each title
onto YOUR machine (every fetch is SHA256-pinned) and combines it with
the CP/M boot floppy - nothing is redistributed by this project. Treat
disks built from titles without a clear license as private copies.

Needs only Python 3: without a local CP/M build the released boot disk
is downloaded instead, so no assembler is required.

  make_game_disk.py --list             show the catalogue
  make_game_disk.py ladder             build build/ladder.d88
  make_game_disk.py --local Z.COM ...  boot disk + your own files

Boot the result - in the web emulator just drop it on the screen - and
type the command the build prints. The verified terminal settings are
pre-applied (the BIOS console speaks ADM-3A, TeleVideo extras and an
ANSI/VT100 subset).
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

VENDOR = PROJECT / "vendor" / "games"
# without a local build (no z80asm needed), the released boot disk is used
BOOT_URL = ("https://github.com/zabaglione/cpm-mz2500/releases/download/"
            "v1.2.0/cpm_boot.d88")
BOOT_SHA256 = "682a2c02868964f464d84d69a702d2c384cbc656403f86fe178723f075fdf59a"

DERAMP = ("https://deramp.com/downloads/mfe_archive/040-Software/"
          "Digital%20Research/CPM%20Implementations/COMPUPRO/GAMES/")
CPM_GAMES = ("https://raw.githubusercontent.com/ivang78/cpm-games/"
             "6a279b149873201dc2604b751c88b21e009dbb86/")

# Yahoo Software's Ladder/CatChum keep their settings in the .DAT file.
# These bytes reproduce a LADCONF/CATCONF run measured on this port:
# terminal = ADM 3A, sound/wisecracks on, keys = WASD (stored as
# down/left/right/up at 0E0h). Re-run LADCONF/CATCONF to change them.
YAHOO_DAT_PATCH = [
    (0x000, b"\x06ADM 3A       "),
    (0x0C0, b"YY"),
    (0x0E0, b"SADW"),
]

# One entry per game: archives fetched (SHA256-pinned), the CP/M files
# taken out of them, optional byte patches, and how to start the game.
# source kinds: {"url", "sha256", "member": "inner.zip!MEMBER" | "MEMBER"}
# for zip archives, or a bare file when "member" is absent.
GAMES = {
    "rogue": {
        "title": "Rogue 1.7 (David Goodenough, 1985)",
        "command": "ROGUE",
        "files": [
            {"url": "https://britzl.github.io/roguearchive/files/rogue17cpm.zip",
             "sha256": "4249c0b771d0a9caa1ea9210ebef7e7a200c1b060a13199679cef8a7c62d9da5",
             "member": "rogue17.zip!ROGUE.CPM", "name": "ROGUE.COM",
             # advertise only the escape codes the BIOS implements
             # (dim/bright/clear-EOL/clear-EOS) in the capability bitmap
             "patch": [(0x12F, b"\xC3")]},
            {"url": "https://britzl.github.io/roguearchive/files/rogue17cpm.zip",
             "sha256": "4249c0b771d0a9caa1ea9210ebef7e7a200c1b060a13199679cef8a7c62d9da5",
             "member": "rogue17.zip!ROGUE.DOC", "name": "ROGUE.DOC"},
            {"url": "https://britzl.github.io/roguearchive/files/rogue17cpm.zip",
             "sha256": "4249c0b771d0a9caa1ea9210ebef7e7a200c1b060a13199679cef8a7c62d9da5",
             "member": "rogue17.zip!ROGUE.NOT", "name": "ROGUE.NOT"},
        ],
    },
    "inthedark": {
        "title": "In The Dark (Kian Ryan, 2022, MIT)",
        "command": "ITDARK80",
        "files": [
            {"url": "https://github.com/kianryan/InTheDark/releases/download/0.1/itdark80.com",
             "sha256": "52798190a58b1975b8883991b59cdbad46ca246e8782c2be23b4887993dc85f3",
             "name": "ITDARK80.COM"},
        ],
    },
    "advent": {
        "title": "Colossal Cave Adventure (Crowther/Woods, Z80 port)",
        "command": "ADVENTUR",
        "files": [
            {"url": "https://www.ifarchive.org/if-archive/games/cpm/Advent_CPM.zip",
             "sha256": "9a9feb501c15c728f1e4e88eda6de325f1270052a205c6f27dc86f3c8d4d492a",
             "member": "Adventur.com", "name": "ADVENTUR.COM"},
            {"url": "https://www.ifarchive.org/if-archive/games/cpm/Advent_CPM.zip",
             "sha256": "9a9feb501c15c728f1e4e88eda6de325f1270052a205c6f27dc86f3c8d4d492a",
             "member": "Phrogz.din", "name": "PHROGZ.DIN"},
        ],
    },
    "ladder": {
        "title": "Ladder (Yahoo Software, 1982)",
        "command": "LADDER",
        "files": [
            {"url": DERAMP + "LADDER.COM",
             "sha256": "583399fa98acbe725d15a91f5a3028b195fbe0b28b09d93e26199a90d72d0e67",
             "name": "LADDER.COM"},
            {"url": DERAMP + "LADDER.DAT",
             "sha256": "9d4c46c47e04b25153424f0416d8670e51150a5c4f3e56ac1d7a0a6ec4e969a9",
             "name": "LADDER.DAT", "patch": YAHOO_DAT_PATCH},
            {"url": DERAMP + "LADCONF.COM",
             "sha256": "7198470b1d0bd59b5129d60144dc3faf0ad7af96009242a8762d36c33f1d14ec",
             "name": "LADCONF.COM"},
        ],
    },
    "catchum": {
        "title": "CatChum (Yahoo Software, 1982)",
        "command": "CATCHUM",
        "files": [
            {"url": DERAMP + "CATCHUM.COM",
             "sha256": "290be6961c0ce655ed63f36005a020f30da38a0726add10dc04fee4c4e95b1dc",
             "name": "CATCHUM.COM"},
            {"url": DERAMP + "CATCHUM.DAT",
             "sha256": "89fed74e6ca8709ad88569ab1c83dc8ea506aeaa271bc5763e15974cbf0f87a9",
             "name": "CATCHUM.DAT", "patch": YAHOO_DAT_PATCH},
            {"url": DERAMP + "CATCONF.COM",
             "sha256": "5a9549ce701ad3b9f74902ef5429c66f1a5063e9aa94444b22fc85785d5f7aaf",
             "name": "CATCONF.COM"},
        ],
    },
    "flap": {
        "title": "FLAP CP/M (ivang78)",
        "command": "FLAPCPM",
        "files": [
            {"url": CPM_GAMES + "FLAPCPM.COM",
             "sha256": "afbbcdabb797360a60132e5311f4137e62bdbcf1b05f8bae104054dfd93259f3",
             "name": "FLAPCPM.COM"},
        ],
    },
}


def fetch_pinned(url: str, digest: str) -> bytes:
    # some archives (the IF Archive included) reject urllib's default UA
    request = urllib.request.Request(
        url, headers={"User-Agent": "cpm-mz2500-game-disk/1.0"})
    blob = urllib.request.urlopen(request, timeout=120).read()
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


def game_file(game: str, spec: dict) -> bytes:
    """The prepared bytes of one file, cached under vendor/games/<game>/."""
    cache = VENDOR / game / spec["name"]
    if not cache.is_file():
        blob = fetch_pinned(spec["url"], spec["sha256"])
        member = spec.get("member")
        if member:
            archive = zipfile.ZipFile(io.BytesIO(blob))
            if "!" in member:
                inner, member = member.split("!", 1)
                archive = zipfile.ZipFile(io.BytesIO(archive.read(inner)))
            blob = archive.read(member)
        data = bytearray(blob)
        for offset, patch in spec.get("patch", ()):
            data[offset:offset + len(patch)] = patch
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(bytes(data))
    return cache.read_bytes()


def build_disk(files: dict[str, bytes], output: pathlib.Path) -> None:
    image = D88Image(bytearray(boot_disk().read_bytes()))
    fs = cpmfs.CpmFilesystem(cpmfs.D88CpmAdapter(image, dg.FD))
    for name, data in files.items():
        fs.add_file(name, data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image.data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", nargs="?", choices=sorted(GAMES),
                        help="game to build (see --list)")
    parser.add_argument("--list", action="store_true",
                        help="show the catalogue and exit")
    parser.add_argument("--local", nargs="+", metavar="FILE",
                        help="build a boot disk carrying these local files "
                             "instead of a catalogue game")
    parser.add_argument("--output", help="output path "
                        "(default: build/<game>.d88)")
    args = parser.parse_args()

    if args.list:
        for name, game in sorted(GAMES.items()):
            print(f"{name:10s} {game['title']}  ->  {game['command']}")
        return 0

    if args.local:
        files = {pathlib.Path(f).name.upper(): pathlib.Path(f).read_bytes()
                 for f in args.local}
        output = pathlib.Path(args.output or PROJECT / "build" / "local.d88")
        build_disk(files, output)
        print(f"wrote {output} (bootable; carries {', '.join(files)})")
        return 0

    if not args.game:
        parser.error("give a game name, --local files, or --list")
    game = GAMES[args.game]
    files = {spec["name"]: game_file(args.game, spec)
             for spec in game["files"]}
    output = pathlib.Path(args.output
                          or PROJECT / "build" / f"{args.game}.d88")
    build_disk(files, output)
    print(f"wrote {output} (bootable; type {game['command']} "
          "at the A> prompt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
