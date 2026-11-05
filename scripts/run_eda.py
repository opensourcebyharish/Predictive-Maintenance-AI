"""Run the Phase 1 EDA pass and write reports/figures + reports/eda_summary.md.

Run from the repository root (venv active)::

    python scripts/run_eda.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from predictive_maintenance.eda.report import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
