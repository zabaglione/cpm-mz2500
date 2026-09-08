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

    def test_game_builder_uses_current_system(self):
        game_builder = (REPO / "tools" / "make_game_disk.py").read_text()
        self.assertIn("make_boot_d88.build_disk(boot, True)", game_builder)
        self.assertNotIn("BOOT_URL", game_builder)


if __name__ == "__main__":
    unittest.main()
