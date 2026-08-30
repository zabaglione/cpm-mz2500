#!/usr/bin/env python3
"""Fetch the CP/M 2.2 sources and DRI utility binaries into vendor/cpm22/.

Everything is pinned by SHA256. CP/M and its derivatives are freely
distributable per the 2022-07-07 grant by Bryan Sparks (DRDOS, Inc.);
see LICENSES.md and vendor/cpm22/LICENSE.txt after fetching.

vendor/ is gitignored: this script is the reproducible way to populate it.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import sys
import urllib.request
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = REPO_ROOT / "vendor" / "cpm22"

# brouhaha/cpm22: CP/M 2.2 CCP+BDOS reformatted for cross-assembly by
# Eric Smith, verified byte-exact against real CP/M 2.2 disks (minus the
# 6-byte serials). Pinned to a specific commit.
GITHUB_COMMIT = "01018abbccce0bdf4874b0b2ed1a048c5fcc2987"
GITHUB_RAW = f"https://raw.githubusercontent.com/brouhaha/cpm22/{GITHUB_COMMIT}"

SOURCES = {
    "src/ccp.asm": (
        f"{GITHUB_RAW}/ccp.asm",
        "015dc575a8e4d8d54057a7d014b90cf17df490c0e356346cc740cb0d3a73d262",
    ),
    "src/bdos.asm": (
        f"{GITHUB_RAW}/bdos.asm",
        "2f715ad338278d5b7c63546492ae1b25b2871ab7d42a70cc2b90ff8aa0f52930",
    ),
    "LICENSE.txt": (
        f"{GITHUB_RAW}/LICENSE.txt",
        "a9bcdbc66bb31b86882e84469f133b3bd5598f46423b4c6bbb6bedb9f2eac754",
    ),
    "README.md": (
        f"{GITHUB_RAW}/README.md",
        "939f663683adbf98567fd6caa95c3688c19e0ac40cc48eac730353605a927d51",
    ),
    # Public-domain 8x8 console font (dhepper/font8x8, IBM PD VGA lineage);
    # gen_font.py turns it into the PCG glyph include.
    "../font8x8/font8x8_basic.h": (
        "https://raw.githubusercontent.com/dhepper/font8x8/"
        "8e279d2d864e79128e96188a6b9526cfa3fbfef9/font8x8_basic.h",
        "49d8df366296b203ca3211bc0672cf2a762135bf12710735b6292756b19dffd5",
    ),
}

# The Unofficial CP/M Web Site binary distribution of CP/M 2.2 (a Xerox 1800
# system disk): DRI utilities plus CPM.SYS, our byte-diff reference.
BIN_ZIP_URL = "http://cpm.z80.de/download/cpm22-b.zip"
BIN_ZIP_SHA256 = "88735cca77e786505f53a63746ddbc5ca221eda79fd822fde5dc9f00a5bfba6f"
BIN_FILES = {
    "ASM.COM": "ef403388a04f18d735984fe497f9fa5dbb48f114b52dab323e33e82073133c2c",
    "DDT.COM": "bc4b0f085f8d1e37caf2a13850c70afa07acb626b22b1a7cb63368b3334dd448",
    "DUMP.COM": "9a99911c0fe0aaec22fdec61b1b2b03dd012ea12d20cc17f21c6f6d9c5399fe3",
    "ED.COM": "0397b96b6d48ba92a0b41cdf974bf8ad31e4d49783f1ff7eed9e701b6a8870db",
    "LOAD.COM": "c885d061a5dcb3830ab1c29a13e34d3c0560cc3faf569bc55b195c0330a9cbd6",
    "PIP.COM": "7f9e12a92e2bcfd814b5b680a2f7d5c2a2c50c9a5ef94a6891dcaa3527f08ec2",
    "STAT.COM": "614d0b1d66466177e5b2bf585251d53d1e24eda34ada136b4ae178ab5944dc73",
    "SUBMIT.COM": "4c3fec22ebca595b03c279eb21b19aa4b2dab139741ed29172ca6fa4c43e7066",
    "XSUB.COM": "817a16b595ea6de8df0dd5e808f89a49e85dea546673283d759d01e960598bed",
    "CPM.SYS": "d057e40d5d7f919f52a1c27a40175d6d66f5fd5fba4be00dd2fef6daa71d1892",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def have(path: pathlib.Path, digest: str) -> bool:
    return path.is_file() and sha256(path.read_bytes()) == digest


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main() -> int:
    fetched = 0
    for rel, (url, digest) in SOURCES.items():
        target = VENDOR / rel
        if have(target, digest):
            continue
        data = download(url)
        if sha256(data) != digest:
            print(f"SHA256 mismatch for {url}", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        fetched += 1

    bin_dir = VENDOR / "bin"
    if not all(have(bin_dir / name, digest) for name, digest in BIN_FILES.items()):
        blob = download(BIN_ZIP_URL)
        if sha256(blob) != BIN_ZIP_SHA256:
            print(f"SHA256 mismatch for {BIN_ZIP_URL}", file=sys.stderr)
            return 1
        bin_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for name, digest in BIN_FILES.items():
                data = archive.read(name)
                if sha256(data) != digest:
                    print(f"SHA256 mismatch for {name} in {BIN_ZIP_URL}", file=sys.stderr)
                    return 1
                (bin_dir / name).write_bytes(data)
                fetched += 1

    print(f"vendor/cpm22 ready ({fetched} files fetched, rest already present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
