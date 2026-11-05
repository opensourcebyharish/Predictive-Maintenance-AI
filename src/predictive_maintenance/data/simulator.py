"""Synthetic industrial-machine sensor simulator.

This is the Phase 1 cut of the IoT layer (Phases 4+ stream it through the
FastAPI backend). It generates the four sensor channels named in the project
roadmap — temperature (°C), vibration (mm/s), pressure (bar) and RPM — while a
latent health index decays from 100 (fully healthy) to 0 (failure):

* a **healthy** phase: readings hover around baseline with sensor noise plus a
  slow sinusoidal duty cycle,
* a **degradation** phase: wear accumulates faster as health falls and the
  dominant failure mode emerges in the channels,
* a **failure-risk** phase near end of life: readings are strongly abnormal.

Health decay is deterministic; sensor values are noisy observations. Streams
are therefore reproducible given a seed, which makes the simulator usable for
tests, thresholds and model training augmentation.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

STATE_NORMAL = "normal"
STATE_DEGRADED = "degraded"
STATE_FAILURE_RISK = "failure_risk"
STATES: tuple[str, ...] = (STATE_NORMAL, STATE_DEGRADED, STATE_FAILURE_RISK)

# Health-score boundaries for the discrete condition states.
THRESHOLD_DEGRADED = 60.0
THRESHOLD_FAILURE_RISK = 25.0


@dataclass(frozen=True)
class MachineProfile:
    """Baseline behaviour and wear characteristics of one machine."""

    machine_id: str
    temperature_base_c: float = 70.0
    vibration_base_mm_s: float = 3.0
    pressure_base_bar: float = 8.0
    rpm_base: float = 1500.0
    # Health points lost per step at full health; decay accelerates as health
    # falls (times ``degradation_gain`` at health 0).
    wear_rate_per_step: float = 0.02
    degradation_gain: float = 2.5


@dataclass(frozen=True)
class SensorReading:
    """One timestamped sensor sample plus derived condition labels."""

    machine_id: str
    step: int
    temperature_c: float
    vibration_mm_s: float
    pressure_bar: float
    rpm: float
    health_score: float
    state: str


def state_for_health(health: float) -> str:
    """Map the continuous health index to its discrete condition state."""
    if health >= THRESHOLD_DEGRADED:
        return STATE_NORMAL
    if health >= THRESHOLD_FAILURE_RISK:
        return STATE_DEGRADED
    return STATE_FAILURE_RISK


class MachineSimulator:
    """Step-streaming simulator for a single machine.

    Usage::

        sim = MachineSimulator(MACHINES[1], seed=7)
        reading = sim.step()        # one sample per call
        stream = sim.stream(500)    # five hundred consecutive samples
    """

    def __init__(
        self,
        profile: MachineProfile,
        seed: int = 42,
        start_health: float = 100.0,
        noise_scale: float = 1.0,
    ) -> None:
        if not 0.0 <= start_health <= 100.0:
            raise ValueError("start_health must be within [0, 100].")
        if noise_scale < 0.0:
            raise ValueError("noise_scale must be non-negative.")
        self._profile = profile
        self._rng = np.random.default_rng(seed)
        self._step = 0
        self._health = float(start_health)
        self._noise_scale = float(noise_scale)

    @property
    def profile(self) -> MachineProfile:
        return self._profile

    @property
    def health(self) -> float:
        """Current latent health index (0..100, monotonically decreasing)."""
        return self._health

    @property
    def step(self) -> int:
        """Number of samples generated so far."""
        return self._step

    def step(self) -> SensorReading:
        """Advance one time step and return the observed sensor reading."""
        profile = self._profile
        # Health decay accelerates as the machine degrades.
        acceleration = 1.0 + profile.degradation_gain * (1.0 - self._health / 100.0)
        self._health = max(0.0, self._health - profile.wear_rate_per_step * acceleration)
        wear_fraction = (100.0 - self._health) / 100.0

        # Slow duty-cycle variation (e.g. day/night load cycles, 720-step period).
        load = 1.0 + 0.05 * math.sin(2.0 * math.pi * self._step / 720.0)
        rng = self._rng
        noise = self._noise_scale

        temperature = (
            profile.temperature_base_c * load * (1.0 + 0.45 * wear_fraction) + rng.normal(0.0, 0.8 * noise)
        )
        vibration = (
            profile.vibration_base_mm_s * (1.0 + 1.1 * wear_fraction) + rng.normal(0.0, 0.15 * noise)
        )
        pressure = (
            profile.pressure_base_bar * (1.0 - 0.15 * wear_fraction) + rng.normal(0.0, 0.12 * noise)
        )
        rpm = profile.rpm_base * (1.0 - 0.05 * wear_fraction) + rng.normal(0.0, 12.0 * noise)

        reading = SensorReading(
            machine_id=profile.machine_id,
            step=self._step,
            temperature_c=round(float(temperature), 3),
            vibration_mm_s=round(float(vibration), 3),
            pressure_bar=round(float(pressure), 3),
            rpm=round(float(rpm), 0),
            health_score=round(float(self._health), 3),
            state=state_for_health(self._health),
        )
        self._step += 1
        return reading

    def stream(self, n_steps: int) -> list[SensorReading]:
        """Generate ``n_steps`` consecutive readings."""
        if n_steps < 0:
            raise ValueError("n_steps must be non-negative.")
        if n_steps == 0:
            return []
        return [self.step() for _ in range(n_steps)]

    def __iter__(self):
        """Infinite stream of readings."""
        while True:
            yield self.step()


def run_to_failure(
    profile: MachineProfile,
    seed: int = 42,
    max_steps: int = 100_000,
) -> list[SensorReading]:
    """Generate a full run-to-failure history for one machine.

    The loop terminates because health decays strictly monotonically to 0;
    ``max_steps`` guards against pathological profiles.
    """
    sim = MachineSimulator(profile, seed=seed)
    readings: list[SensorReading] = []
    while round(sim.health, 3) > 0.0:
        readings.append(sim.step())
        if len(readings) > max_steps:
            raise RuntimeError("run_to_failure exceeded max_steps; profile never reaches health 0.")
    return readings


def readings_to_dataframe(readings: list[SensorReading]) -> pd.DataFrame:
    """Flatten readings into a DataFrame (one row per step)."""
    return pd.DataFrame([asdict(reading) for reading in readings])


# The default fleet used in examples, tests and the later API demo: three
# machines with distinct baselines and failure speeds.
MACHINES: tuple[MachineProfile, ...] = (
    MachineProfile(
        machine_id="PUMP_01",
        temperature_base_c=70.0,
        vibration_base_mm_s=3.0,
        pressure_base_bar=8.0,
        rpm_base=1500.0,
        wear_rate_per_step=0.02,
    ),
    MachineProfile(
        machine_id="MOTOR_02",
        temperature_base_c=60.0,
        vibration_base_mm_s=4.0,
        pressure_base_bar=5.0,
        rpm_base=1800.0,
        wear_rate_per_step=0.035,
    ),
    MachineProfile(
        machine_id="COMPRESSOR_03",
        temperature_base_c=85.0,
        vibration_base_mm_s=2.5,
        pressure_base_bar=10.0,
        rpm_base=3000.0,
        # Fastest degrader of the fleet: lifespan ~ 100*ln(1+g)/(w*g) ~= 716 steps,
        # so it reaches the failure-risk state within a 800-step demo window.
        wear_rate_per_step=0.07,
    ),
)


def simulate_fleet(
    profiles: tuple[MachineProfile, ...] = MACHINES,
    seed: int = 42,
    n_steps: int = 500,
    noise_scale: float = 1.0,
) -> pd.DataFrame:
    """Simulate every machine of a fleet for ``n_steps`` and concatenate rows."""
    frames = [
        readings_to_dataframe(
            MachineSimulator(profile, seed=seed + index, noise_scale=noise_scale).stream(n_steps)
        )
        for index, profile in enumerate(profiles)
    ]
    return pd.concat(frames, ignore_index=True)
