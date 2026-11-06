"""Command-line interface for the Phase 4 IoT simulator.

Usage::

    python -m predictive_maintenance.simulator.cli start
    python -m predictive_maintenance.simulator.cli stop
    python -m predictive_maintenance.simulator.cli scenario developing_degradation
    python -m predictive_maintenance.simulator.cli status
    python -m predictive_maintenance.simulator.cli health
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from predictive_maintenance.simulator.config import VALID_SCENARIOS, get_simulator_config
from predictive_maintenance.simulator.simulator import (
    SimulatorOrchestrator,
    get_orchestrator,
    start_simulation,
    stop_simulation,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IoT sensor simulator for the Predictive Maintenance AI project",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    start_p = subparsers.add_parser("start", help="Start the simulation")
    start_p.add_argument(
        "--blocking",
        action="store_true",
        help="Run in the foreground instead of a background thread",
    )
    start_p.add_argument(
        "--machines",
        type=int,
        default=None,
        help="Number of machines (overrides env/config)",
    )
    start_p.add_argument(
        "--scenario",
        choices=list(VALID_SCENARIOS),
        default=None,
        help="Scenario name (overrides env/config)",
    )
    start_p.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between sampling rounds",
    )
    start_p.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Total run time in seconds (0 = run until stopped)",
    )

    # stop
    subparsers.add_parser("stop", help="Stop the running simulation")

    # scenario
    scenario_p = subparsers.add_parser("scenario", help="Set or show the scenario")
    scenario_p.add_argument(
        "name",
        nargs="?",
        choices=list(VALID_SCENARIOS),
        help="Scenario to switch to (shows current if omitted)",
    )

    # status
    subparsers.add_parser("status", help="Show simulation status")

    # health
    subparsers.add_parser("health", help="Check backend health")

    return parser


def _apply_overrides(orch: SimulatorOrchestrator, args: argparse.Namespace) -> None:
    if args.machines is not None:
        orch.set_machine_count(args.machines)
    if args.scenario is not None:
        orch.set_scenario(args.scenario)
    if args.interval is not None:
        orch.config.interval_seconds = args.interval
    if args.duration is not None:
        orch.config.duration_seconds = args.duration


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        orch = SimulatorOrchestrator()
        _apply_overrides(orch, args)
        orch.start(blocking=args.blocking)
        if args.blocking:
            return 0
        print(
            f"Simulation started: {orch.config.machine_count} machines, "
            f"scenario={orch.config.scenario}, interval={orch.config.interval_seconds}s"
        )
        print("Press Ctrl-C or run 'python -m predictive_maintenance.simulator.cli stop' to stop.")
        try:
            while orch.running:
                orch._stop_event.wait(1.0)
        except KeyboardInterrupt:
            pass
        orch.stop()
        print("Simulation stopped.")
        return 0

    if args.command == "stop":
        stop_simulation()
        print("Simulation stop requested.")
        return 0

    if args.command == "scenario":
        orch = get_orchestrator()
        if args.name is None:
            print(f"Current scenario: {orch.config.scenario}")
            return 0
        orch.set_scenario(args.name)
        print(f"Scenario changed to: {args.name}")
        return 0

    if args.command == "status":
        orch = get_orchestrator()
        st = orch.status()
        print(f"Running: {st['running']}")
        print(f"Rounds completed: {st['rounds_completed']}")
        print(f"Client stats: {st['client_stats']}")
        print(f"Scenario: {st['config']['scenario']}")
        for m in st["machines"]:
            print(
                f"  {m['machine_id']}: cycle={m['next_cycle'] - 1}, "
                f"sent={m['readings_sent']}, errors={m['errors']}"
            )
        return 0

    if args.command == "health":
        orch = get_orchestrator()
        try:
            h = orch.health()
            print(f"Backend healthy: {h}")
        except Exception as exc:  # noqa: BLE001
            print(f"Backend unreachable: {exc}")
            return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
