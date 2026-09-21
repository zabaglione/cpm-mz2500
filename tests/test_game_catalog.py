"""Game catalogue behavior that must stay aligned with CP/M Plus support."""

import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
BUILDER = REPO / "tools" / "make_game_disk.py"


class GameCatalogTest(unittest.TestCase):
    def run_builder(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUILDER), *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_list_marks_catchum_as_cpm_22_only(self):
        result = self.run_builder("--list")

        self.assertEqual(result.returncode, 0, result.stderr)
        catchum = next(line for line in result.stdout.splitlines()
                       if line.startswith("catchum"))
        self.assertIn("[CP/M 2.2 only]", catchum)

    def test_current_builder_rejects_catchum_before_writing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "catchum.d88"
            result = self.run_builder(
                "catchum", "--output", str(output),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not supported by the current CP/M Plus disk",
                          result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
