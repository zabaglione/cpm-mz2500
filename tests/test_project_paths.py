"""Standalone repository path invariants."""

import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import fetch_tools  # noqa: E402


class ProjectPathsTest(unittest.TestCase):
    def test_cpmtools_stays_inside_repository(self):
        self.assertEqual(fetch_tools.VENDOR, REPO / "vendor" / "cpmtools")

    def test_boot_banner_matches_download_release(self):
        boot_source = (REPO / "src" / "boot.asm").read_text()
        game_builder = (REPO / "tools" / "make_game_disk.py").read_text()
        match = re.search(r"EMM/SASI port (v\d+\.\d+\.\d+)", boot_source)
        self.assertIsNotNone(match)
        self.assertIn(f'"{match.group(1)}/cpm_boot.d88"', game_builder)


if __name__ == "__main__":
    unittest.main()
