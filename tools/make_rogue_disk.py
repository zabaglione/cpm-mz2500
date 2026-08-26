#!/usr/bin/env python3
"""Compatibility wrapper: `make_game_disk.py rogue` under the old name."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import make_game_disk  # noqa: E402

if __name__ == "__main__":
    sys.argv.insert(1, "rogue")
    raise SystemExit(make_game_disk.main())
