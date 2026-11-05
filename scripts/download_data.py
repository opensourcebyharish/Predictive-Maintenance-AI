"""Download the NASA C-MAPSS dataset files into ``data/raw/CMAPSSData``.

Run from the repository root (venv active)::

    python scripts/download_data.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from predictive_maintenance.data.download import download_cmapss  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the C-MAPSS dataset files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even if the files already exist locally",
    )
    args = parser.parse_args()

    paths = download_cmapss(force=args.force)
    print(f"Saved {len(paths)} C-MAPSS files:")
    for path in paths:
        print(f"  {path.name:<18} {path.stat().st_size:>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
