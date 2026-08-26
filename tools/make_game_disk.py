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
            "v1.2.1/cpm_boot.d88")
BOOT_SHA256 = "c1b95faaa77377ff60ccffc6dae5f78e49b706a90342c6a6a6a8b7d89fa2acc9"

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



# ---- games built ON the MZ-2500 with the bundled Pascal/MT+ -------------
# The fetched TP3 source is rewritten for Pascal/MT+ (our shim below) and
# shipped on a disk together with the compiler: boot it, SUBMIT MAKE, and
# the machine compiles its own game.

SHIM_PROCS = """\
EXTERNAL FUNCTION @BDOS(FUNC: INTEGER; PARM: INTEGER): INTEGER;

PROCEDURE GOTOXY(X, Y: INTEGER);
BEGIN
  WRITE(CHR(27), '[', Y:1, ';', X:1, 'H');
END;

PROCEDURE CLRSCR;
BEGIN
  WRITE(CHR(27), '[2J', CHR(27), '[H');
END;

PROCEDURE CURSOFF;
BEGIN
  WRITE(CHR(27), '[?25l');
END;

PROCEDURE CURSON;
BEGIN
  WRITE(CHR(27), '[?25h');
END;

PROCEDURE COLORFG(C: BYTE);
BEGIN
  WRITE(CHR(27), '[3', CHR(48 + C), 'm');
END;

PROCEDURE COLORBG(C: BYTE);
BEGIN
  WRITE(CHR(27), '[4', CHR(48 + C), 'm');
END;

FUNCTION KEYPRESSED: BOOLEAN;
BEGIN
  RNDSEED := RNDSEED + 1;
  KEYPRESSED := @BDOS(11, 0) <> 0;
END;

FUNCTION READKEY: CHAR;
VAR K: INTEGER;
BEGIN
  REPEAT
    RNDSEED := RNDSEED + 1;
    K := @BDOS(6, 255);
  UNTIL K <> 0;
  READKEY := CHR(K);
END;

PROCEDURE RANDOMIZE;
BEGIN
  IF RNDSEED = 0 THEN RNDSEED := 12345;
END;

FUNCTION RANDOM(N: INTEGER): INTEGER;
VAR R: INTEGER;
BEGIN
  RNDSEED := RNDSEED * 25173 + 13849;
  R := RNDSEED MOD N;
  IF R < 0 THEN R := R + N;
  RANDOM := R;
END;

FUNCTION UPCASE(C: CHAR): CHAR;
BEGIN
  IF (C >= 'a') AND (C <= 'z') THEN
    UPCASE := CHR(ORD(C) - 32)
  ELSE
    UPCASE := C;
END;

PROCEDURE DELAY(MS: INTEGER);
VAR I, J: INTEGER;
BEGIN
  FOR I := 1 TO MS DO
    FOR J := 1 TO 60 DO ;
END;
"""


SHIM_CONSTS = """\
  _BLACK = 0; _RED = 1; _GREEN = 2; _YELLOW = 3;
  _BLUE = 4; _MAGENTA = 5; _CYAN = 6; _WHITE = 7;
"""



def convert_2048(text: str) -> str:
    # rebuild the declaration head in ISO order (label, const, var,
    # routines) - MT+ does not allow TP3's reopened sections
    head = """program g2048;
label 99;
const
""" + SHIM_CONSTS + """var
  RNDSEED: integer;
  terminal: byte;
  d,x,y,i,j,a,z: byte;
  f: array[0..16,0..16] of integer;
  c: char;
  score, bestscore: integer;

""" + SHIM_PROCS
    body = text[text.index("{$I CPM.INC}") + len("{$I CPM.INC}\n"):]
    text = head + body
    # ISO: for-control variables must be local to the routine
    text = text.replace(
        "procedure print;\nbegin",
        "procedure print;\nvar x,y,z: byte;\nbegin")
    text = text.replace(
        "procedure shft(dx,dy:integer);\nvar n:integer;\nbegin",
        "procedure shft(dx,dy:integer);\nvar n:integer; x,y: byte;\nbegin")
    # shim routine names are 7-char unique for LINKMT
    text = text.replace("SetTextColor(", "COLORFG(")
    text = text.replace("SetTextBg(", "COLORBG(")
    text = text.replace("CursorOff", "CURSOFF")
    text = text.replace("CursorOn", "CURSON")
    # TP3 #NN char literals
    text = text.replace("write(#7)", "write(chr(7))")
    text = text.replace("until c=#27", "until c=chr(27)")
    text = text.replace("goto L1", "goto 99")
    text = text.replace("L1:", "99:")
    # case-label #27 plus case-else: restructure as if/else
    text = text.replace(
        """    case c of
      'A':shft(-1,0);
      'W':shft(0,-1);
      'S':shft(0,1);
      'D':shft(1,0);
      'R':goto 99;
      #27:begin end;
      else write(chr(7));
    end;""",
        """    if c = 'A' then shft(-1,0)
    else if c = 'W' then shft(0,-1)
    else if c = 'S' then shft(0,1)
    else if c = 'D' then shft(1,0)
    else if c = 'R' then goto 99
    else if c <> chr(27) then write(chr(7));""")
    # fillchar/sizeof -> explicit loops (x,y are in scope)
    text = text.replace(
        "fillchar(f,sizeof(f),0);a:=2;",
        "for x:=0 to 16 do for y:=0 to 16 do f[x,y]:=0;\n  a:=2;")
    # 'exit' leaves dshf early: MT+ needs a label
    text = text.replace(
        "procedure dshf(x0,y0,dx,dy:integer);\nvar x,y,n:integer;\nbegin",
        "procedure dshf(x0,y0,dx,dy:integer);\nlabel 88;\nvar x,y,n:integer;\nbegin")
    text = text.replace("if n=0 then exit;", "if n=0 then goto 88;")
    text = text.replace(
        "  until false;\nend;\n\nprocedure shft",
        "  until false;\n88:\nend;\n\nprocedure shft")
    return text



MTBUILD_GAMES = {
    "2048": {
        "title": "2048 (CRISS CP/M version - built on your MZ)",
        "unit": "G2048",
        "source": {
            "url": CPM_GAMES + "2048.PAS",
            "sha256": "cdf2472a3db9c4af7b752e3d79ba0651dbbb8c837001d703567df3c56ea56209",
        },
        "convert": convert_2048,
    },
}


def build_mtbuild(name: str, output: pathlib.Path) -> None:
    game = MTBUILD_GAMES[name]
    import fetch_tools
    fetch_tools.main()                     # ensure the Pascal/MT+ suite
    files = {}
    for path in fetch_tools.group_files("PASCAL"):
        if not path.is_file():
            raise SystemExit(f"{path} missing - fetch_tools could not get it")
        files[path.name] = path.read_bytes()
    spec = game["source"]
    src = fetch_pinned(spec["url"], spec["sha256"]).decode("ascii", "replace")
    src = src.replace("\r\n", "\n")   # converter patterns expect LF
    unit = game["unit"]
    files[unit + ".PAS"] = game["convert"](src).replace("\n", "\r\n").encode("ascii")
    files["MAKE.SUB"] = ("MTPLUS " + unit + "\r\nLINKMT " + unit
                         + ",PASLIB/S\r\n").encode("ascii")
    build_disk(files, output)
    print(f"wrote {output} (bootable; run SUBMIT MAKE once - the MZ-2500")
    print(f"compiles the game itself (a few minutes) - then type {unit})")


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
    parser.add_argument("game", nargs="?",
                        choices=sorted(GAMES) + sorted(MTBUILD_GAMES),
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
        for name, game in sorted(MTBUILD_GAMES.items()):
            print(f"{name:10s} {game['title']}  ->  SUBMIT MAKE")
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
    if args.game in MTBUILD_GAMES:
        output = pathlib.Path(args.output
                              or PROJECT / "build" / f"{args.game}.d88")
        build_mtbuild(args.game, output)
        return 0
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
