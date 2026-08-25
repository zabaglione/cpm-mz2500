"""Byte-exactness gate for the CP/M 2.2 conversion chain.

Converts the vendored AS-syntax 8080 sources with convert_cpm22.py,
assembles them with z80asm at the reference origins (CCP=DC00h, BDOS=E400h,
BIOS=F200h - the Xerox 1800 layout of vendor/cpm22/bin/CPM.SYS), and
byte-compares against that CPM.SYS. Only the DRI serial-number bytes may
differ (CCP +328/+329/+32C/+32D, BDOS +0/+1/+4/+5; the serial's two zero
bytes match anyway).

Skips cleanly when vendor files or z80asm are missing (run
tools/fetch_cpm22.py first).
"""

import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
VENDOR = REPO / "vendor" / "cpm22"

CCP_SERIAL_OFFSETS = {0x328, 0x329, 0x32A, 0x32B, 0x32C, 0x32D}
BDOS_SERIAL_OFFSETS = {0, 1, 2, 3, 4, 5}


def build(tmp: pathlib.Path, source: str, origin: int, defines: list[str]) -> bytes:
    asm = tmp / (source + ".z80.asm")
    binary = tmp / (source + ".bin")
    convert = [
        "python3", str(TOOLS / "convert_cpm22.py"),
        "--input", str(VENDOR / "src" / source),
        "--output", str(asm),
        "--origin", hex(origin),
    ]
    for item in defines:
        convert += ["--define", item]
    subprocess.run(convert, check=True)
    subprocess.run(["z80asm", "-o", str(binary), str(asm)],
                   check=True, capture_output=True)
    return binary.read_bytes()


@unittest.skipUnless((VENDOR / "bin" / "CPM.SYS").is_file(),
                     "vendor/cpm22 not fetched (run tools/fetch_cpm22.py)")
@unittest.skipUnless(shutil.which("z80asm"), "z80asm not installed")
class VendorMatchTest(unittest.TestCase):
    def setUp(self):
        self.reference = (VENDOR / "bin" / "CPM.SYS").read_bytes()
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cpm22match_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assert_matches(self, ours: bytes, ref: bytes, allowed: set, name: str):
        diffs = [i for i in range(len(ref)) if ours[i] != ref[i]]
        unexpected = [hex(i) for i in diffs if i not in allowed]
        self.assertEqual(unexpected, [],
                         f"{name} differs from CPM.SYS outside the serial bytes")

    def test_ccp_matches_reference(self):
        ours = build(self.tmp, "ccp.asm", 0xDC00, []).ljust(0x800, b"\0")
        self.assert_matches(ours, self.reference[0x000:0x800],
                            CCP_SERIAL_OFFSETS, "CCP")

    def test_bdos_matches_reference(self):
        ours = build(self.tmp, "bdos.asm", 0xE400,
                     ["bios=0xF200"]).ljust(0xE00, b"\0")
        self.assert_matches(ours, self.reference[0x800:0x1600],
                            BDOS_SERIAL_OFFSETS, "BDOS")


if __name__ == "__main__":
    unittest.main()
