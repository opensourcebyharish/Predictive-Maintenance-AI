"""Unit tests for the synthetic IoT machine simulator."""

from __future__ import annotations

import pytest

from predictive_maintenance.data.simulator import (
    MACHINES,
    STATES,
    MachineProfile,
    MachineSimulator,
    STATE_DEGRADED,
    STATE_FAILURE_RISK,
    STATE_NORMAL,
    readings_to_dataframe,
    run_to_failure,
    state_for_health,
)


def test_same_seed_produces_identical_streams() -> None:
    stream_a = MachineSimulator(MACHINES[0], seed=11).stream(50)
    stream_b = MachineSimulator(MACHINES[0], seed=11).stream(50)
    assert stream_a == stream_b  # frozen dataclasses compare by value


def test_health_is_monotone_and_fleet_reaches_end_of_life() -> None:
    sim = MachineSimulator(MACHINES[0], seed=1)
    readings = []
    while len(readings) < 20_000 and sim.health > 0.0:
        readings.append(sim.step())

    healths = [reading.health_score for reading in readings]
    assert all(earlier >= later for earlier, later in zip(healths, healths[1:]))
    assert {reading.state for reading in readings} == set(STATES)
    assert readings[0].state == STATE_NORMAL
    assert healths[-1] == 0.0


def test_first_reading_lies_around_baseline() -> None:
    reading = MachineSimulator(MACHINES[1], seed=0).step()
    assert reading.state == STATE_NORMAL
    assert reading.machine_id == "MOTOR_02"
    assert 50.0 < reading.temperature_c < 75.0
    assert 2.0 < reading.vibration_mm_s < 6.0
    assert 0.0 < reading.pressure_bar < 8.0
    assert 1000.0 < reading.rpm < 2500.0


def test_near_end_of_life_the_machine_is_in_failure_risk_state() -> None:
    sim = MachineSimulator(MACHINES[2], seed=9)
    sim.stream(800)
    assert sim.health <= 25.0
    assert sim.step().state == STATE_FAILURE_RISK


def test_state_thresholds() -> None:
    assert state_for_health(100.0) == STATE_NORMAL
    assert state_for_health(60.0) == STATE_NORMAL
    assert state_for_health(59.9) == STATE_DEGRADED
    assert state_for_health(25.0) == STATE_DEGRADED
    assert state_for_health(24.9) == STATE_FAILURE_RISK


def test_invalid_simulator_configuration() -> None:
    with pytest.raises(ValueError, match="start_health"):
        MachineSimulator(MACHINES[0], start_health=150.0)
    with pytest.raises(ValueError, match="noise_scale"):
        MachineSimulator(MACHINES[0], noise_scale=-1.0)
    with pytest.raises(ValueError, match="n_steps"):
        MachineSimulator(MACHINES[0]).stream(-1)


def test_zero_wear_profile_never_degrades() -> None:
    healthy = MachineProfile(machine_id="TEST", wear_rate_per_step=0.0)
    readings = MachineSimulator(healthy, seed=2).stream(25)
    assert all(reading.health_score == 100.0 for reading in readings)
    assert all(reading.state == STATE_NORMAL for reading in readings)


def test_run_to_failure_terminates_at_zero() -> None:
    fast = MachineProfile(machine_id="FAST", wear_rate_per_step=0.5)
    readings = run_to_failure(fast, seed=5)
    assert readings[-1].health_score == 0.0
    assert readings[-1].state == STATE_FAILURE_RISK


def test_dataframe_conversion_preserves_step_order() -> None:
    frame = readings_to_dataframe(MachineSimulator(MACHINES[2], seed=3).stream(20))
    expected_columns = {
        "machine_id",
        "step",
        "temperature_c",
        "vibration_mm_s",
        "pressure_bar",
        "rpm",
        "health_score",
        "state",
    }
    assert set(frame.columns) == expected_columns
    assert len(frame) == 20
    assert frame["step"].tolist() == list(range(20))
    assert frame["machine_id"].nunique() == 1
