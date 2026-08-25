"""Consistency checks for the DPB single source of truth."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import disk_geometry as dg


class DpbTest(unittest.TestCase):
    def test_all_geometries_internally_consistent(self):
        for g in dg.GEOMETRIES:
            g.check()

    def test_fd_capacity(self):
        # 154 data tracks x 4KB = 616KB -> 308 x 2KB blocks
        self.assertEqual(dg.FD.data_records, 4928)
        self.assertEqual(dg.FD.bls, 2048)
        self.assertEqual(dg.FD.dsm, 307)
        self.assertEqual(dg.FD.exm, 0)

    def test_emm_capacity(self):
        # 78 data tracks x 8KB = 624KB -> 312 x 2KB blocks
        self.assertEqual(dg.EMM.data_records, 4992)
        self.assertEqual(dg.EMM.dsm, 311)
        self.assertEqual(dg.EMM.cks, 0)

    def test_sasi_capacity(self):
        # 1021 data tracks x 8KB -> 2042 x 4KB blocks, 1024 dir entries
        self.assertEqual(dg.SASI.data_records, 65344)
        self.assertEqual(dg.SASI.bls, 4096)
        self.assertEqual(dg.SASI.dsm, 2041)
        self.assertEqual(dg.SASI.exm, 1)
        self.assertEqual(dg.SASI.drm, 1023)

    def test_partition_bases_do_not_overlap(self):
        c_end = dg.SASI_BASE_C + dg.SASI_PARTITION_BLOCKS
        self.assertLessEqual(c_end, dg.SASI_BASE_D)
        # both partitions fit in the canonical 87,648-block image
        self.assertLessEqual(dg.SASI_BASE_D + dg.SASI_PARTITION_BLOCKS, 87648)

    def test_generated_include_is_current(self):
        src = pathlib.Path(__file__).resolve().parents[1] / "src" / "generated_dpb.inc"
        self.assertTrue(src.is_file(), "run disk_geometry.py to generate it")
        self.assertEqual(src.read_text(), dg.generate_include(),
                         "generated_dpb.inc is stale: rerun disk_geometry.py")


if __name__ == "__main__":
    unittest.main()
