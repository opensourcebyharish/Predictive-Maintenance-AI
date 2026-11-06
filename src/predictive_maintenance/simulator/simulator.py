"""Simulator orchestrator: manages multiple simulated machines and submits
their readings to the FastAPI backend.

The orchestrator:

* Creates ``N`` independent machines, each with its own cycle counter
* Collects readings in batches and submits them via ``POST /readings/batch``
* Enforces chronological ordering (each machine only sends increasing cycles)
* Handles API errors gracefully without aborting the whole simulation
* Supports start/stop and scenario selection
"""

from __future__ import annotations

import signal
import threading
import time
from typing import Any

from predictive_maintenance.api.schemas import ReadingIngest
from predictive_maintenance.simulator.client import SimulatorClient, SimulatorClientError
from predictive_maintenance.simulator.config import SimulatorConfig, get_simulator_config
from predictive_maintenance.simulator.machine import SimulatedMachine, create_machines


class SimulatorOrchestrator:
    """Orchestrates multiple simulated machines submitting readings to the API."""

    def __init__(self, config: SimulatorConfig | None = None) -> None:
        self.config = config or get_simulator_config()
        self.client = SimulatorClient(self.config.api_url)
        self.machines: list[SimulatedMachine] = create_machines(
            count=self.config.machine_count,
            dataset_id=self.config.dataset_id,
            scenario=self.config.scenario,
            seed=self.config.seed,
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.running: bool = False
        self.rounds_completed: int = 0

    # ------------------------------------------------------------------ lifecycle

    def start(self, blocking: bool = False) -> None:
        """Start the simulation loop.

        When ``blocking`` is False (default) the loop runs in a background
        thread; call :meth:`stop` to end it. When True this method blocks
        until the duration elapses or :meth:`stop` is called.
        """
        with self._lock:
            if self.running:
                return
            self._stop_event.clear()
            self.running = True
            self.rounds_completed = 0
        if blocking:
            self._run_loop()
        else:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Request the simulation loop to stop."""
        with self._lock:
            if not self.running:
                return
            self._stop_event.set()
            self.running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run_loop(self) -> None:
        """Main simulation loop: collect readings and submit in batches."""
        start_time = time.monotonic()
        try:
            while not self._stop_event.is_set():
                # Check duration limit
                if (
                    self.config.duration_seconds > 0
                    and time.monotonic() - start_time >= self.config.duration_seconds
                ):
                    break

                batch: list[ReadingIngest] = []
                for machine in self.machines:
                    batch.append(machine.next_reading())

                try:
                    self.client.submit_batch(batch)
                    with self._lock:
                        self.rounds_completed += 1
                except SimulatorClientError as exc:
                    # Record the error on every machine in this batch but
                    # continue the simulation rather than aborting.
                    for machine in self.machines:
                        machine.record_error(str(exc))
                    self.client.errors += 1

                # Sleep for the interval, but wake early if stop is requested.
                self._stop_event.wait(self.config.interval_seconds)
        finally:
            with self._lock:
                self.running = False

    # ------------------------------------------------------------------ scenario / status

    def set_scenario(self, scenario: str) -> None:
        """Change the scenario for all machines."""
        from predictive_maintenance.simulator.scenarios import get_scenario

        get_scenario(scenario)  # validate
        self.config.scenario = scenario
        for machine in self.machines:
            machine.set_scenario(scenario)

    def set_machine_count(self, count: int) -> None:
        """Change the number of machines, creating new ones as needed."""
        from predictive_maintenance.simulator.machine import create_machines

        self.config.machine_count = count
        self.machines = create_machines(
            count=count,
            dataset_id=self.config.dataset_id,
            scenario=self.config.scenario,
            seed=self.config.seed,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self.running
        return {
            "running": running,
            "config": {
                "api_url": self.config.api_url,
                "machine_count": self.config.machine_count,
                "interval_seconds": self.config.interval_seconds,
                "duration_seconds": self.config.duration_seconds,
                "seed": self.config.seed,
                "scenario": self.config.scenario,
                "batch_size": self.config.batch_size,
                "dataset_id": self.config.dataset_id,
            },
            "client_stats": self.client.stats(),
            "rounds_completed": self.rounds_completed,
            "machines": [m.status() for m in self.machines],
        }

    def health(self) -> dict[str, Any]:
        """Check backend health."""
        return self.client.health()

    def __enter__(self) -> "SimulatorOrchestrator":
        self.start(blocking=False)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_orchestrator: SimulatorOrchestrator | None = None


def get_orchestrator() -> SimulatorOrchestrator:
    """Return the module-level orchestrator (creates it on first call)."""
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = SimulatorOrchestrator()
    return _default_orchestrator


def start_simulation(blocking: bool = False) -> SimulatorOrchestrator:
    """Start the default orchestrator."""
    orch = get_orchestrator()
    orch.start(blocking=blocking)
    return orch


def stop_simulation() -> None:
    """Stop the default orchestrator."""
    orch = get_orchestrator()
    if orch is not None:
        orch.stop()
