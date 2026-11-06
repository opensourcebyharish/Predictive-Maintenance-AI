"""Simulator configuration sourced from environment variables.

All variables are prefixed with ``SIMULATOR_``. Missing variables fall back to
documented defaults, keeping behaviour predictable on developer machines as
well as in containers.

Environment variables::

  SIMULATOR_API_URL         base URL of the FastAPI backend
                            (default: http://127.0.0.1:8000)
  SIMULATOR_MACHINE_COUNT   number of independent machines to simulate
                            (default: 3)
  SIMULATOR_INTERVAL_SECONDS seconds between sampling rounds
                            (default: 1.0)
  SIMULATOR_DURATION_SECONDS total simulation run time in seconds
                            (0 = run until stopped; default: 60)
  SIMULATOR_SEED            random seed for reproducible scenarios
                            (default: 42)
  SIMULATOR_SCENARIO        scenario name: normal, developing_degradation,
                            abnormal_vibration, abnormal_temperature,
                            sensor_failure, sudden_anomaly, recovery
                            (default: normal)
  SIMULATOR_BATCH_SIZE      readings per batch request to the API
                            (default: 10)
  SIMULATOR_DATASET_ID      C-MAPSS subset whose models/features are used
                            (default: FD001)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

VALID_SCENARIOS: tuple[str, ...] = (
    "normal",
    "developing_degradation",
    "abnormal_vibration",
    "abnormal_temperature",
    "sensor_failure",
    "sudden_anomaly",
    "recovery",
)


@dataclass
class SimulatorConfig:
    """All simulator runtime configuration."""

    api_url: str = "http://127.0.0.1:8000"
    machine_count: int = 3
    interval_seconds: float = 1.0
    duration_seconds: float = 60.0
    seed: int = 42
    scenario: str = "normal"
    batch_size: int = 10
    dataset_id: str = "FD001"

    @classmethod
    def from_env(cls) -> "SimulatorConfig":
        """Build settings from environment variables (missing -> defaults)."""

        def _float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            return float(raw)

        def _int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            return int(raw)

        scenario = os.getenv("SIMULATOR_SCENARIO", cls.scenario)
        if scenario not in VALID_SCENARIOS:
            raise ValueError(
                f"unknown scenario {scenario!r}; expected one of {list(VALID_SCENARIOS)}"
            )

        return cls(
            api_url=os.getenv("SIMULATOR_API_URL", cls.api_url),
            machine_count=_int("SIMULATOR_MACHINE_COUNT", cls.machine_count),
            interval_seconds=_float("SIMULATOR_INTERVAL_SECONDS", cls.interval_seconds),
            duration_seconds=_float("SIMULATOR_DURATION_SECONDS", cls.duration_seconds),
            seed=_int("SIMULATOR_SEED", cls.seed),
            scenario=scenario,
            batch_size=_int("SIMULATOR_BATCH_SIZE", cls.batch_size),
            dataset_id=os.getenv("SIMULATOR_DATASET_ID", cls.dataset_id),
        )


def get_simulator_config() -> SimulatorConfig:
    """Read simulator settings from the environment."""
    return SimulatorConfig.from_env()
