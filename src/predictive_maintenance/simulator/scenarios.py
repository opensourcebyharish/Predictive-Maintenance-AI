"""Scenario generators for the Phase 4 IoT simulator.

Each scenario is a callable ``(cycle: int, rng: random.Random) -> dict[str, float]``
that returns values for sensors ``s1``-``s21`` plus the three operating
settings. The returned values are *synthetic* and are clearly marked
``is_simulated=true`` when submitted to the API.

Sensor groupings used by the scenarios are *conceptual only* - they are not
scientifically validated mappings to physical quantities. They exist purely to
produce visually distinct behaviours for testing and demonstration:

* "temperature-related": s2, s3, s4, s7
* "vibration-related":   s8, s9
* "pressure-related":    s6, s11
* "rpm-related":         s8, s9
"""

from __future__ import annotations

import math
import random
from typing import Callable

SENSOR_NAMES: tuple[str, ...] = tuple(f"s{i}" for i in range(1, 22))
SETTING_NAMES: tuple[str, ...] = ("setting_1", "setting_2", "setting_3")

# Conceptual sensor groupings (not scientifically validated).
TEMPERATURE_SENSORS: tuple[str, ...] = ("s2", "s3", "s4", "s7")
VIBRATION_SENSORS: tuple[str, ...] = ("s8", "s9")
PRESSURE_SENSORS: tuple[str, ...] = ("s6", "s11")
RPM_SENSORS: tuple[str, ...] = ("s8", "s9")

BASE_VALUES: dict[str, float] = {
    # Baselines chosen so all sensors are positive and distinct.
    "s1": 500.0,
    "s2": 650.0,
    "s3": 1600.0,
    "s4": 1400.0,
    "s5": 15.0,
    "s6": 22.0,
    "s7": 550.0,
    "s8": 2400.0,
    "s9": 9100.0,
    "s10": 1.3,
    "s11": 48.0,
    "s12": 520.0,
    "s13": 2400.0,
    "s14": 8100.0,
    "s15": 8.5,
    "s16": 0.03,
    "s17": 390.0,
    "s18": 2400.0,
    "s19": 100.0,
    "s20": 39.0,
    "s21": 23.5,
}

BASE_SETTINGS: dict[str, float] = {
    "setting_1": 10.0,
    "setting_2": 0.25,
    "setting_3": 100.0,
}


def _base_reading(cycle: int, rng: random.Random) -> dict[str, float]:
    """Baseline reading: all sensors at nominal values with small Gaussian noise."""
    reading: dict[str, float] = dict(BASE_SETTINGS)
    for name in SENSOR_NAMES:
        noise = rng.gauss(0.0, 0.02)  # ~2% relative noise
        reading[name] = BASE_VALUES[name] * (1.0 + noise)
    return reading


def scenario_normal(cycle: int, rng: random.Random) -> dict[str, float]:
    """Steady-state operation: all sensors near baseline with small noise."""
    return _base_reading(cycle, rng)


def scenario_developing_degradation(cycle: int, rng: random.Random) -> dict[str, float]:
    """Gradual degradation: temperature and vibration sensors drift upward over cycles."""
    reading = _base_reading(cycle, rng)
    drift = 1.0 + 0.003 * cycle  # up to ~+30% by cycle 100
    for name in TEMPERATURE_SENSORS + VIBRATION_SENSORS:
        reading[name] *= drift
    # RPM sensors decline slightly as degradation progresses
    for name in RPM_SENSORS:
        reading[name] *= max(0.85, 1.0 - 0.0015 * cycle)
    return reading


def scenario_abnormal_vibration(cycle: int, rng: random.Random) -> dict[str, float]:
    """Intermittent vibration spikes on fan/core speed sensors."""
    reading = _base_reading(cycle, rng)
    if cycle % 7 == 0:  # spike every 7 cycles
        for name in VIBRATION_SENSORS:
            reading[name] *= rng.uniform(1.5, 2.5)
    return reading


def scenario_abnormal_temperature(cycle: int, rng: random.Random) -> dict[str, float]:
    """Sustained elevated temperature readings."""
    reading = _base_reading(cycle, rng)
    for name in TEMPERATURE_SENSORS:
        reading[name] *= rng.uniform(1.15, 1.35)
    return reading


def scenario_sensor_failure(cycle: int, rng: random.Random) -> dict[str, float]:
    """One sensor (s15) stuck at an extreme value, simulating a failed sensor."""
    reading = _base_reading(cycle, rng)
    reading["s15"] = 0.0 if cycle % 2 == 0 else 9999.0
    return reading


def scenario_sudden_anomaly(cycle: int, rng: random.Random) -> dict[str, float]:
    """Sudden multi-sensor anomaly at mid-life, then return toward baseline."""
    reading = _base_reading(cycle, rng)
    if 30 <= cycle <= 45:
        anomaly_factor = rng.uniform(2.0, 4.0)
        for name in SENSOR_NAMES:
            reading[name] *= anomaly_factor
    return reading


def scenario_recovery(cycle: int, rng: random.Random) -> dict[str, float]:
    """Readings recovering from an anomalous state back to baseline."""
    reading = _base_reading(cycle, rng)
    if cycle <= 20:
        # Start anomalous
        for name in SENSOR_NAMES:
            reading[name] *= rng.uniform(2.0, 4.0)
    elif cycle <= 40:
        # Gradually recover
        recovery = (cycle - 20) / 20.0
        for name in SENSOR_NAMES:
            reading[name] = BASE_VALUES[name] + (
                reading[name] - BASE_VALUES[name]
            ) * (1.0 - recovery)
    # After cycle 40, back to baseline (handled by _base_reading)
    return reading


SCENARIOS: dict[str, Callable[[int, random.Random], dict[str, float]]] = {
    "normal": scenario_normal,
    "developing_degradation": scenario_developing_degradation,
    "abnormal_vibration": scenario_abnormal_vibration,
    "abnormal_temperature": scenario_abnormal_temperature,
    "sensor_failure": scenario_sensor_failure,
    "sudden_anomaly": scenario_sudden_anomaly,
    "recovery": scenario_recovery,
}


def get_scenario(name: str) -> Callable[[int, random.Random], dict[str, float]]:
    """Return the scenario generator for ``name``."""
    if name not in SCENARIOS:
        raise ValueError(
            f"unknown scenario {name!r}; expected one of {sorted(SCENARIOS)}"
        )
    return SCENARIOS[name]
