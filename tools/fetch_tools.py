#!/usr/bin/env python3
"""Fetch the optional language/tool packages into vendor/cpmtools/.

Everything is SHA256-pinned. Two license umbrellas:
- DRI products (MAC, RMAC/LINK/LIB/XREF, ZSID, Pascal/MT+, PL/I-80,
  CBASIC) as distributed by The Unofficial CP/M Web Site under the
  2022-07-07 DRDOS, Inc. grant - the same basis as CP/M itself.
- BDS C, released into the Public Domain by its author (2002-09-20,
  statement on bdsoft.com).

Groups (consumed by the image builders):
  DEV    - assemblers, linker, librarian, debugger  -> hard disk C:
  PASCAL - Pascal/MT+ 5.6.1                          -> hard disk D:
  PLI    - PL/I-80 1.4                               -> hard disk D:
  BASIC  - CBASIC                                    -> hard disk D:
  BDSC   - BDS C 1.60                                -> hard disk D:
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import urllib.request
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
VENDOR = REPO_ROOT / "vendor" / "cpmtools"

DOWNLOADS = {
    "mac-b.zip": (
        "http://cpm.z80.de/download/mac-b.zip",
        "1318a9a18edef63467ceb1dfa61d4fe3a2d9d308d16f5e8bf53d29ed0668ff0e"),
    "zsid14.zip": (
        "http://cpm.z80.de/download/zsid14.zip",
        "518757bd51faac030891a6ee4de7e7ddde9b562f4f26a9de794f334c29c2896a"),
    "mtp561.zip": (
        "http://cpm.z80.de/download/mtp561.zip",
        "51bc26fe1eb0108f5074a12ce69cf3a6c7e6accf4e01bd4bad08a2da09ce450b"),
    "pli80_14.zip": (
        "http://cpm.z80.de/download/pli80_14.zip",
        "4724c6b4b72f35af963b8bb0ebf743398a242cdbdebd36070d2c42956b4f8d64"),
    "cbasic80.zip": (
        "http://cpm.z80.de/download/cbasic80.zip",
        "67eb9ffbf5c746580c3d6b8edfe3a579dfa1e683aa0d4352806acd173d0bd3ca"),
    "bdsc-all.zip": (
        "https://www.bdsoft.com/dist/bdsc-all.zip",
        "bf5ab207081acb50729471fd29bf40ee63b3800e7617144e358e7533da558c0c"),
}

# (zip, member-inside-zip, CP/M filename, group). A member of the form
# "inner.zip!member" is taken from a zip nested inside the download.
MEMBERS = [
    # --- DEV: the DRI development chain -------------------------------
    ("mac-b.zip", "MAC.COM", "MAC.COM", "DEV"),
    ("pli80_14.zip", "DISK1/RMAC.COM", "RMAC.COM", "DEV"),
    ("pli80_14.zip", "DISK1/LINK.COM", "LINK.COM", "DEV"),
    ("pli80_14.zip", "DISK1/LIB.COM", "LIB.COM", "DEV"),
    ("pli80_14.zip", "DISK1/XREF.COM", "XREF.COM", "DEV"),
    ("pli80_14.zip", "DISK1/Z80.LIB", "Z80.LIB", "DEV"),
    ("zsid14.zip", "ZSID.COM", "ZSID.COM", "DEV"),
    # --- Pascal/MT+ 5.6.1 ---------------------------------------------
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.COM", "MTPLUS.COM", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.000", "MTPLUS.000", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.001", "MTPLUS.001", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.002", "MTPLUS.002", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.003", "MTPLUS.003", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.004", "MTPLUS.004", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.005", "MTPLUS.005", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!MTPLUS.006", "MTPLUS.006", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!LINKMT.COM", "LINKMT.COM", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!PASLIB.ERL", "PASLIB.ERL", "PASCAL"),
    ("mtp561.zip", "PAS1.ZIP!PROG.SRC", "PROG.SRC", "PASCAL"),
    ("mtp561.zip", "PAS2.ZIP!MTERRS.TXT", "MTERRS.TXT", "PASCAL"),
    # --- PL/I-80 1.4 ---------------------------------------------------
    ("pli80_14.zip", "DISK1/PLI.COM", "PLI.COM", "PLI"),
    ("pli80_14.zip", "DISK1/PLI0.OVL", "PLI0.OVL", "PLI"),
    ("pli80_14.zip", "DISK1/PLI1.OVL", "PLI1.OVL", "PLI"),
    ("pli80_14.zip", "DISK1/PLI2.OVL", "PLI2.OVL", "PLI"),
    ("pli80_14.zip", "DISK1/PLILIB.IRL", "PLILIB.IRL", "PLI"),
    ("pli80_14.zip", "DISK2/DEMO.PLI", "DEMO.PLI", "PLI"),
    # --- CBASIC --------------------------------------------------------
    ("cbasic80.zip", "./cbasic.com", "CBASIC.COM", "BASIC"),
    ("cbasic80.zip", "./crun.com", "CRUN.COM", "BASIC"),
    ("cbasic80.zip", "./cbasxref.com", "CBASXREF.COM", "BASIC"),
    # --- BDS C 1.60 (Public Domain) ------------------------------------
    ("bdsc-all.zip", "bdsc160/CC.COM", "CC.COM", "BDSC"),
    ("bdsc-all.zip", "bdsc160/CC2.COM", "CC2.COM", "BDSC"),
    ("bdsc-all.zip", "bdsc160/CLINK.COM", "CLINK.COM", "BDSC"),
    ("bdsc-all.zip", "bdsc160/CLIB.COM", "CLIB.COM", "BDSC"),
    ("bdsc-all.zip", "bdsc160/CCONFIG.COM", "CCONFIG.COM", "BDSC"),
    ("bdsc-all.zip", "bdsc160/C.CCC", "C.CCC", "BDSC"),
    ("bdsc-all.zip", "bdsc160/DEFF.CRL", "DEFF.CRL", "BDSC"),
    ("bdsc-all.zip", "bdsc160/DEFF2.CRL", "DEFF2.CRL", "BDSC"),
    ("bdsc-all.zip", "bdsc160/work/STDIO.H", "STDIO.H", "BDSC"),
    ("bdsc-all.zip", "bdsc160/CHARIO.C", "CHARIO.C", "BDSC"),
]

GROUPS = sorted({group for _, _, _, group in MEMBERS})


def group_files(group: str) -> list[pathlib.Path]:
    """Paths of a group's fetched files (for the image builders)."""
    return [VENDOR / group / name
            for _, _, name, g in MEMBERS if g == group]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    archives: dict[str, zipfile.ZipFile] = {}
    fetched = 0
    missing = [
        (z, m, n, g) for z, m, n, g in MEMBERS
        if not (VENDOR / g / n).is_file()
    ]
    if not missing:
        print("vendor/cpmtools ready (all files present)")
        return 0
    for zip_name in sorted({z for z, _, _, _ in missing}):
        url, digest = DOWNLOADS[zip_name]
        blob = urllib.request.urlopen(url, timeout=120).read()
        if sha256(blob) != digest:
            print(f"SHA256 mismatch for {url}", file=sys.stderr)
            return 1
        archives[zip_name] = zipfile.ZipFile(io.BytesIO(blob))
    nested: dict[tuple[str, str], zipfile.ZipFile] = {}
    for zip_name, member, cpm_name, group in missing:
        archive = archives[zip_name]
        if "!" in member:
            inner_name, inner_member = member.split("!", 1)
            key = (zip_name, inner_name)
            if key not in nested:
                nested[key] = zipfile.ZipFile(
                    io.BytesIO(archive.read(inner_name)))
            data = nested[key].read(inner_member)
        else:
            data = archive.read(member)
        target = VENDOR / group / cpm_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        fetched += 1
    print(f"vendor/cpmtools ready ({fetched} files fetched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
