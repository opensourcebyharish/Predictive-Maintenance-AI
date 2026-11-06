"""Entry point for the Phase 4 IoT simulator.

Usage::

    python scripts/run_simulator.py start
    python scripts/run_simulator.py status
    python scripts/run_simulator.py scenario abnormal_vibration
"""

from __future__ import annotations

import sys

from predictive_maintenance.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main())
