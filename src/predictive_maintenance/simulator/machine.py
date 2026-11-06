"""Per-machine simulation state and reading generation.

Each :class:`SimulatedMachine` tracks its own cycle counter and scenario, and
produces chronological readings that can be submitted to the ingestion API.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from predictive_maintenance.api.schemas import ReadingIngest
from predictive_maintenance.simulator.config import SimulatorConfig
from predictive_maintenance.simulator.scenarios import SENSOR_NAMES, get_scenario


class SimulatedMachine:
    """One simulated machine with independent cycle numbering."""

    def __init__(
        self,
        machine_id: str,
        dataset_id: str,
        scenario: str,
        seed: int,
        start_cycle: int = 1,
    ) -> None:
        self.machine_id = machine_id
        self.dataset_id = dataset_id
        self.scenario = scenario
        self.cycle = start_cycle
        self._rng = random.Random(seed)
        self._scenario_fn = get_scenario(scenario)
        self.readings_sent: int = 0
        self.errors: int = 0
        self.last_error: str | None = None
        self.last_reading_at: datetime | None = None

    def next_reading(self) -> ReadingIngest:
        """Generate the next chronological reading for this machine."""
        sensor_values = self._scenario_fn(self.cycle, self._rng)
        reading = ReadingIngest(
            machine_id=self.machine_id,
            dataset_id=self.dataset_id,
            cycle=self.cycle,
            timestamp=datetime.now(timezone.utc),
            setting_1=sensor_values["setting_1"],
            setting_2=sensor_values["setting_2"],
            setting_3=sensor_values["setting_3"],
            is_simulated=True,
            **{name: float(sensor_values[name]) for name in SENSOR_NAMES},
        )
        self.cycle += 1
        return reading

    def set_scenario(self, scenario: str) -> None:
        """Change the scenario mid-simulation."""
        self.scenario = scenario
        self._scenario_fn = get_scenario(scenario)

    def record_success(self) -> None:
        self.readings_sent += 1
        self.last_reading_at = datetime.now(timezone.utc)

    def record_error(self, message: str) -> None:
        self.errors += 1
        self.last_error = message

    def status(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "dataset_id": self.dataset_id,
            "scenario": self.scenario,
            "next_cycle": self.cycle,
            "readings_sent": self.readings_sent,
            "errors": self.errors,
            "last_error": self.last_error,
            "last_reading_at": self.last_reading_at.isoformat()
            if self.last_reading_at
            else None,
        }


def create_machines(
    count: int,
    dataset_id: str,
    scenario: str,
    seed: int,
    id_prefix: str = "SIM",
) -> list[SimulatedMachine]:
    """Create ``count`` machines with independent seeds and sequential ids."""
    machines: list[SimulatedMachine] = []
    for i in range(count):
        machine_id = f"{id_prefix}-{i + 1:03d}"
        machine_seed = seed + i  # each machine gets a deterministic but different seed
        machines.append(
            SimulatedMachine(
                machine_id=machine_id,
                dataset_id=dataset_id,
                scenario=scenario,
                seed=machine_seed,
                start_cycle=1,
            )
        )
    return machines
