"""Unit tests for Phase 4 IoT simulator.

Tests scenarios, machine state, config, and client without requiring a
running API server.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from predictive_maintenance.simulator.config import (
    SimulatorConfig,
    VALID_SCENARIOS,
    get_simulator_config,
)
from predictive_maintenance.simulator.machine import SimulatedMachine, create_machines
from predictive_maintenance.simulator.scenarios import (
    SENSOR_NAMES,
    SETTING_NAMES,
    get_scenario,
)


class TestConfig:
    def test_defaults(self) -> None:
        cfg = SimulatorConfig()
        assert cfg.api_url == "http://127.0.0.1:8000"
        assert cfg.machine_count == 3
        assert cfg.interval_seconds == 1.0
        assert cfg.duration_seconds == 60.0
        assert cfg.seed == 42
        assert cfg.scenario == "normal"
        assert cfg.batch_size == 10
        assert cfg.dataset_id == "FD001"

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIMULATOR_MACHINE_COUNT", "5")
        monkeypatch.setenv("SIMULATOR_SCENARIO", "abnormal_temperature")
        monkeypatch.setenv("SIMULATOR_SEED", "123")
        cfg = get_simulator_config()
        assert cfg.machine_count == 5
        assert cfg.scenario == "abnormal_temperature"
        assert cfg.seed == 123

    def test_invalid_scenario_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIMULATOR_SCENARIO", "not_a_scenario")
        with pytest.raises(ValueError, match="unknown scenario"):
            get_simulator_config()


class TestScenarios:
    def test_all_scenarios_return_complete_reading(self) -> None:
        rng = random.Random(42)
        for name in VALID_SCENARIOS:
            fn = get_scenario(name)
            result = fn(cycle=10, rng=rng)
            # 3 settings + 21 sensors
            assert len(result) == 24, f"{name}: expected 24 fields, got {len(result)}"
            for name_ in SETTING_NAMES:
                assert name_ in result, f"{name}: missing {name_}"
            for name_ in SENSOR_NAMES:
                assert name_ in result, f"{name}: missing {name_}"
                assert isinstance(result[name_], float), f"{name}: {name_} not float"

    def test_normal_stays_near_baseline(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("normal")
        for cycle in range(1, 11):
            result = fn(cycle, rng)
            # All sensors should be within ~10% of baseline
            for name in SENSOR_NAMES:
                base = {"s1": 500.0, "s2": 650.0, "s3": 1600.0, "s4": 1400.0,
                        "s5": 15.0, "s6": 22.0, "s7": 550.0, "s8": 2400.0,
                        "s9": 9100.0, "s10": 1.3, "s11": 48.0, "s12": 520.0,
                        "s13": 2400.0, "s14": 8100.0, "s15": 8.5, "s16": 0.03,
                        "s17": 390.0, "s18": 2400.0, "s19": 100.0,
                        "s20": 39.0, "s21": 23.5}[name]
                assert 0.8 * base <= result[name] <= 1.2 * base, (
                    f"normal: {name}={result[name]} outside baseline range at cycle {cycle}"
                )

    def test_developing_degradation_drifts_over_cycles(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("developing_degradation")
        early = fn(cycle=1, rng=rng)
        late = fn(cycle=100, rng=rng)
        # Temperature sensors should be higher at cycle 100 than cycle 1
        for name in ("s2", "s3", "s4", "s7"):
            assert late[name] > early[name], (
                f"degradation: {name} did not drift (early={early[name]}, late={late[name]})"
            )

    def test_abnormal_vibration_has_spikes(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("abnormal_vibration")
        # Check multiple cycles for spikes
        max_s8 = max(fn(c, rng)["s8"] for c in range(1, 50))
        baseline_s8 = {"s8": 2400.0}["s8"]
        assert max_s8 > baseline_s8 * 1.3, (
            f"abnormal_vibration: no spikes detected (max s8={max_s8})"
        )

    def test_abnormal_temperature_is_elevated(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("abnormal_temperature")
        result = fn(cycle=10, rng=rng)
        for name in ("s2", "s3", "s4", "s7"):
            base = {"s2": 650.0, "s3": 1600.0, "s4": 1400.0, "s7": 550.0}[name]
            assert result[name] > base * 1.1, (
                f"abnormal_temperature: {name}={result[name]} not elevated (base={base})"
            )

    def test_sensor_failure_has_extreme_s15(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("sensor_failure")
        result_even = fn(cycle=2, rng=rng)
        result_odd = fn(cycle=3, rng=rng)
        assert result_even["s15"] == 0.0 or result_even["s15"] == 9999.0
        assert result_odd["s15"] == 0.0 or result_odd["s15"] == 9999.0

    def test_sudden_anomaly_has_mid_life_spike(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("sudden_anomaly")
        baseline = fn(cycle=5, rng=rng)
        anomaly = fn(cycle=35, rng=rng)
        # At least one sensor should be significantly higher during anomaly
        max_ratio = max(
            anomaly[name] / baseline[name] for name in SENSOR_NAMES
        )
        assert max_ratio > 1.5, (
            f"sudden_anomaly: no significant spike (max ratio={max_ratio})"
        )

    def test_recovery_returns_to_baseline(self) -> None:
        rng = random.Random(42)
        fn = get_scenario("recovery")
        early = fn(cycle=5, rng=rng)
        late = fn(cycle=50, rng=rng)
        # Early should be anomalous, late should be near baseline
        for name in ("s1", "s2", "s3"):
            base = {"s1": 500.0, "s2": 650.0, "s3": 1600.0}[name]
            assert late[name] < early[name] * 0.7, (
                f"recovery: {name} did not recover (early={early[name]}, late={late[name]})"
            )

    def test_invalid_scenario_name(self) -> None:
        with pytest.raises(ValueError, match="unknown scenario"):
            get_scenario("not_a_scenario")


class TestMachine:
    def test_machine_generates_chronological_readings(self) -> None:
        m = SimulatedMachine("M1", "FD001", "normal", 42)
        r1 = m.next_reading()
        r2 = m.next_reading()
        assert r1.cycle == 1
        assert r2.cycle == 2
        assert r1.machine_id == "M1"
        assert r2.machine_id == "M1"
        assert r1.is_simulated is True
        assert r2.is_simulated is True

    def test_machine_reading_has_all_fields(self) -> None:
        m = SimulatedMachine("M2", "FD003", "abnormal_temperature", 99)
        r = m.next_reading()
        assert r.dataset_id == "FD003"
        assert r.cycle == 1
        assert isinstance(r.timestamp, str) or r.timestamp is not None
        for name in ("setting_1", "setting_2", "setting_3"):
            assert hasattr(r, name)
        for name in SENSOR_NAMES:
            assert hasattr(r, name)

    def test_create_machines_independent_seeds(self) -> None:
        machines = create_machines(count=3, dataset_id="FD001", scenario="normal", seed=42)
        assert len(machines) == 3
        assert machines[0].machine_id == "SIM-001"
        assert machines[1].machine_id == "SIM-002"
        assert machines[2].machine_id == "SIM-003"
        # Different seeds -> different RNG streams -> different readings
        r1 = machines[0].next_reading()
        r2 = machines[1].next_reading()
        assert r1.cycle == r2.cycle == 1
        # At least some sensor values should differ due to different seeds
        different = any(
            getattr(r1, name) != getattr(r2, name) for name in SENSOR_NAMES
        )
        assert different, "machines with different seeds produced identical readings"

    def test_machine_status(self) -> None:
        m = SimulatedMachine("M1", "FD001", "normal", 42)
        m.next_reading()
        m.record_success()
        status = m.status()
        assert status["machine_id"] == "M1"
        assert status["dataset_id"] == "FD001"
        assert status["scenario"] == "normal"
        assert status["readings_sent"] == 1
        assert status["errors"] == 0

    def test_set_scenario(self) -> None:
        m = SimulatedMachine("M1", "FD001", "normal", 42)
        m.set_scenario("abnormal_vibration")
        assert m.scenario == "abnormal_vibration"
