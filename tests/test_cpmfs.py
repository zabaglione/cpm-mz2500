"""Round-trip tests for the CP/M filesystem writer/reader."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import disk_geometry as dg  # noqa: E402
import cpmfs  # noqa: E402
from d88 import make_blank_d88  # noqa: E402


def fd_fs():
    image = make_blank_d88("CPMTEST")
    fs = cpmfs.CpmFilesystem(cpmfs.D88CpmAdapter(image, dg.FD))
    fs.format()
    return fs


class CpmFsRoundTripTest(unittest.TestCase):
    def test_small_file(self):
        fs = fd_fs()
        payload = b"HELLO CP/M\r\n"
        fs.add_file("HELLO.TXT", payload)
        back = fs.read_file("HELLO.TXT")
        self.assertTrue(back.startswith(payload))
        self.assertEqual(len(back), 128)          # record granularity
        self.assertEqual(set(back[len(payload):]), {0x1A})

    def test_multi_extent_file(self):
        fs = fd_fs()
        payload = bytes(range(256)) * 100         # 25,600B > 16KB extent
        fs.add_file("BIG.BIN", payload)
        back = fs.read_file("BIG.BIN")
        self.assertEqual(back[:len(payload)], payload)
        self.assertEqual(fs.ls()["BIG.BIN"], 200)  # records

    def test_exact_block_multiple(self):
        fs = fd_fs()
        payload = b"\xAA" * dg.FD.bls * 3          # exactly 3 blocks
        fs.add_file("BLOCKS.BIN", payload)
        self.assertEqual(fs.read_file("BLOCKS.BIN"), payload)

    def test_many_files_and_ls(self):
        fs = fd_fs()
        for i in range(10):
            fs.add_file(f"F{i}.DAT", bytes([i]) * 300)
        listing = fs.ls()
        self.assertEqual(len(listing), 10)
        self.assertEqual(listing["F3.DAT"], 3)     # 300B -> 3 records
        self.assertEqual(fs.read_file("F7.DAT")[:300], bytes([7]) * 300)

    def test_duplicate_rejected(self):
        fs = fd_fs()
        fs.add_file("A.TXT", b"x")
        with self.assertRaises(ValueError):
            fs.add_file("A.TXT", b"y")

    def test_sasi_wide_entries(self):
        # SASI geometry: DSM>=256 (16-bit pointers), EXM=1 (2 logical
        # extents per entry), flat adapter
        buffer = bytearray(dg.SASI.total_tracks * dg.SASI.spt * 128)
        fs = cpmfs.CpmFilesystem(cpmfs.FlatCpmAdapter(buffer, dg.SASI))
        fs.format()
        payload = bytes((i * 7) & 0xFF for i in range(40000))  # >32KB entry
        fs.add_file("WIDE.BIN", payload)
        back = fs.read_file("WIDE.BIN")
        self.assertEqual(back[:len(payload)], payload)


if __name__ == "__main__":
    unittest.main()
