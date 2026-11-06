"""Phase 3.4: machine monitoring service.

Read-only queries over persisted machines, readings and predictions:

* ``GET /machines`` - list all machines with latest health
* ``GET /machines/{machine_id}`` - detail incl. latest reading + prediction
* ``GET /machines/{machine_id}/readings`` - paginated reading history
* ``GET /machines/{machine_id}/predictions`` - paginated prediction history
* ``GET /machines/{machine_id}/health`` - latest health snapshot

All responses are built from persisted data (no transient in-memory state).
"""

from __future__ import annotations

from typing import Any

from predictive_maintenance import config
from predictive_maintenance.api import db
from predictive_maintenance.api.db.models import Machine, Prediction, Reading
from predictive_maintenance.api.schemas import (
    MachineDetail,
    MachineHealth,
    MachineSummary,
    PaginatedPredictions,
    PaginatedReadings,
    PredictionRecord,
    ReadingRecord,
)


def _health_from_prediction(prediction: Any) -> MachineHealth:
    if prediction is None:
        return MachineHealth.unknown
    prob = prediction.failure_probability or 0.0
    if prob >= 0.8:
        return MachineHealth.critical_risk
    if prob >= 0.5:
        return MachineHealth.elevated_risk
    if bool(prediction.anomaly_status):
        return MachineHealth.anomalous
    return MachineHealth.healthy


class MachineMonitoringService:
    """Read-only monitoring queries over the SQLite store."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------- public API

    def list_machines(self, session: Any) -> list[MachineSummary]:
        machines = session.query(db.Machine).order_by(db.Machine.last_seen_at.desc()).all()
        summaries: list[MachineSummary] = []
        for machine in machines:
            latest_prediction = self._latest_prediction(session, machine.machine_id)
            summaries.append(
                MachineSummary(
                    machine_id=machine.machine_id,
                    dataset_id=machine.dataset_id,
                    reading_count=self._reading_count(session, machine.machine_id),
                    first_cycle=self._first_cycle(session, machine.machine_id),
                    last_cycle=self._last_cycle(session, machine.machine_id),
                    latest_reading_at=machine.last_seen_at,
                    health=_health_from_prediction(latest_prediction),
                )
            )
        return summaries

    def get_machine(self, session: Any, machine_id: str) -> MachineDetail | None:
        machine = session.query(db.Machine).filter_by(machine_id=machine_id).first()
        if machine is None:
            return None
        latest_reading = self._latest_reading(session, machine_id)
        latest_prediction = self._latest_prediction(session, machine_id)
        active_alerts = (
            session.query(db.Alert)
            .filter_by(machine_id=machine_id, status="active")
            .count()
        )
        return MachineDetail(
            machine_id=machine.machine_id,
            dataset_id=machine.dataset_id,
            reading_count=self._reading_count(session, machine_id),
            first_cycle=self._first_cycle(session, machine_id),
            last_cycle=self._last_cycle(session, machine_id),
            latest_reading_at=machine.last_seen_at,
            health=_health_from_prediction(latest_prediction),
            latest_sensor_values=_sensor_values(latest_reading) if latest_reading else None,
            latest_prediction=_prediction_record(latest_prediction) if latest_prediction else None,
            active_alerts=active_alerts,
        )

    def get_readings(
        self, session: Any, machine_id: str, limit: int = 50, offset: int = 0
    ) -> PaginatedReadings:
        query = session.query(Reading).filter_by(machine_id=machine_id).order_by(Reading.cycle.asc())
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return PaginatedReadings(
            machine_id=machine_id,
            readings=[_reading_record(r) for r in rows],
            limit=limit,
            offset=offset,
            total=total,
        )

    def get_predictions(
        self, session: Any, machine_id: str, limit: int = 50, offset: int = 0
    ) -> PaginatedPredictions:
        query = (
            session.query(Prediction)
            .filter_by(machine_id=machine_id)
            .order_by(Prediction.predicted_at.desc())
        )
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return PaginatedPredictions(
            machine_id=machine_id,
            predictions=[_prediction_record(p) for p in rows],
            limit=limit,
            offset=offset,
            total=total,
        )

    def get_health(self, session: Any, machine_id: str) -> dict[str, Any] | None:
        machine = session.query(db.Machine).filter_by(machine_id=machine_id).first()
        if machine is None:
            return None
        latest_prediction = self._latest_prediction(session, machine_id)
        latest_reading = self._latest_reading(session, machine_id)
        return {
            "machine_id": machine_id,
            "dataset_id": machine.dataset_id,
            "health": _health_from_prediction(latest_prediction),
            "last_cycle": self._last_cycle(session, machine_id),
            "last_reading_at": machine.last_seen_at,
            "latest_prediction": _prediction_record(latest_prediction) if latest_prediction else None,
            "active_alerts": session.query(db.Alert)
            .filter_by(machine_id=machine_id, status="active")
            .count(),
        }

    # ------------------------------------------------------------- internals

    @staticmethod
    def _reading_count(session: Any, machine_id: str) -> int:
        return session.query(Reading).filter_by(machine_id=machine_id).count()

    @staticmethod
    def _first_cycle(session: Any, machine_id: str) -> int | None:
        row = (
            session.query(Reading.cycle)
            .filter_by(machine_id=machine_id)
            .order_by(Reading.cycle.asc())
            .first()
        )
        return None if row is None else row[0]

    @staticmethod
    def _last_cycle(session: Any, machine_id: str) -> int | None:
        row = (
            session.query(Reading.cycle)
            .filter_by(machine_id=machine_id)
            .order_by(Reading.cycle.desc())
            .first()
        )
        return None if row is None else row[0]

    @staticmethod
    def _latest_reading(session: Any, machine_id: str) -> Any:
        return (
            session.query(Reading)
            .filter_by(machine_id=machine_id)
            .order_by(Reading.cycle.desc())
            .first()
        )

    @staticmethod
    def _latest_prediction(session: Any, machine_id: str) -> Any:
        return (
            session.query(Prediction)
            .filter_by(machine_id=machine_id)
            .order_by(Prediction.predicted_at.desc())
            .first()
        )


def _reading_record(reading: Reading) -> ReadingRecord:
    import json

    return ReadingRecord(
        id=reading.id,
        machine_id=reading.machine_id,
        cycle=reading.cycle,
        timestamp=reading.timestamp,
        setting_1=float(reading.setting_1),
        setting_2=float(reading.setting_2),
        setting_3=float(reading.setting_3),
        sensor_values=json.loads(reading.s_values) if reading.s_values else {},
        is_simulated=reading.is_simulated,
        stored_at=reading.stored_at,
    )


def _prediction_record(prediction: Prediction) -> PredictionRecord:
    return PredictionRecord(
        id=prediction.id,
        reading_id=prediction.reading_id,
        machine_id=prediction.machine_id,
        model=prediction.model,
        model_version=prediction.model_version,
        predicted_at=prediction.predicted_at,
        anomaly_score=prediction.anomaly_score,
        anomaly_status=prediction.anomaly_status,
        failure_probability=prediction.failure_probability,
        failure_status=prediction.failure_status,
    )


def _sensor_values(reading: Reading) -> dict[str, float]:
    import json

    return json.loads(reading.s_values) if reading.s_values else {}
