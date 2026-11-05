"""Phase 3.3: sensor ingestion service.

Responsibilities:

* Accept and validate individual / batch sensor readings for FD001–FD004.
* Persist readings + predictions transactionally in SQLite.
* Deduplicate readings by ``(machine_id, cycle)`` (idempotent re-ingest).
* Enforce chronological ordering per machine (out-of-order cycles rejected).
* Reconstruct per-machine historical context so the Phase 2.1 rolling /
  time-series features are computed over the full trajectory up to the new
  reading - then score only the newest row.
* Run inference through the existing :class:`ModelService` (no refitting).
* Generate alerts through :class:`AlertService` based on thresholds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from predictive_maintenance import config
from predictive_maintenance.api import db
from predictive_maintenance.api.alerts import AlertService
from predictive_maintenance.api.db.models import Machine, Prediction, Reading
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.schemas import (
    BatchReadingIngestResponse,
    IngestionStatus,
    PredictionResponse,
    ReadingIngest,
    ReadingIngestResult,
)
from predictive_maintenance.api.service import ModelService, PredictionServiceError, _utc_now
from predictive_maintenance.data.cmapss import SENSOR_COLUMNS

__all__ = ["ReadingIngestionService", "ReadingIngestionError"]


class ReadingIngestionError(PredictionServiceError):
    """Raised when a reading cannot be ingested (validation / ordering)."""


class ModelServiceNotLoadedError(ReadingIngestionError):
    """The model service has no artefacts loaded for the requested subset."""


class ReadingIngestionService:
    """Ingest sensor readings, persist them, run inference, store predictions."""

    def __init__(
        self,
        service: ModelService | None = None,
        alert_service: AlertService | None = None,
    ) -> None:
        self.service = service or get_model_service()
        self.alert_service = alert_service or AlertService()

    # ------------------------------------------------------------- public API

    def ingest(self, reading: ReadingIngest) -> ReadingIngestResult:
        """Validate, store (if new), predict and alert for one reading."""
        if not self.service.is_loaded:
            self.service.load()
        if reading.dataset_id not in config.DATASET_IDS:
            raise ReadingIngestionError(
                f"unknown dataset id {reading.dataset_id!r}; expected one of {list(config.DATASET_IDS)}"
            )

        session = db.get_session()
        try:
            return self._ingest_in_transaction(session, reading)
        finally:
            session.close()

    def ingest_batch(self, readings: list[ReadingIngest]) -> BatchReadingIngestResponse:
        """Ingest several readings; each is validated/stored independently.

        One transaction per reading keeps a single malformed reading from
        aborting the whole batch.
        """
        results: list[ReadingIngestResult] = []
        stored = duplicates = rejected = 0
        for reading in readings:
            try:
                result = self.ingest(reading)
            except ReadingIngestionError as exc:  # validation / ordering -> rejected
                result = ReadingIngestResult(
                    status=IngestionStatus.rejected,
                    machine_id=reading.machine_id,
                    cycle=reading.cycle,
                    error=str(exc),
                )
                rejected += 1
            except Exception as exc:  # noqa: BLE001 - surface as rejected, not 500
                result = ReadingIngestResult(
                    status=IngestionStatus.rejected,
                    machine_id=reading.machine_id,
                    cycle=reading.cycle,
                    error=f"ingestion failed: {exc}",
                )
                rejected += 1
            results.append(result)
            if result.status == IngestionStatus.stored:
                stored += 1
            elif result.status == IngestionStatus.duplicate:
                duplicates += 1
        return BatchReadingIngestResponse(
            results=results, stored=stored, duplicates=duplicates, rejected=rejected
        )

    # ------------------------------------------------------------- internals

    def _ingest_in_transaction(self, session: Any, reading: ReadingIngest) -> ReadingIngestResult:
        machine = session.query(db.Machine).filter_by(machine_id=reading.machine_id).first()
        if machine is None:
            machine = db.Machine(machine_id=reading.machine_id, dataset_id=reading.dataset_id)
            session.add(machine)
            session.flush()
        elif machine.dataset_id != reading.dataset_id:
            raise ReadingIngestionError(
                f"machine {reading.machine_id!r} is registered under dataset {machine.dataset_id}, "
                f"not {reading.dataset_id}"
            )

        # Idempotency: exact (machine_id, cycle) already stored -> return it.
        existing = (
            session.query(Reading)
            .filter_by(machine_id=reading.machine_id, cycle=reading.cycle)
            .first()
        )
        if existing is not None:
            prediction = self._get_prediction_for_reading(session, existing.id)
            return ReadingIngestResult(
                status=IngestionStatus.duplicate,
                machine_id=reading.machine_id,
                cycle=reading.cycle,
                reading_id=existing.id,
                prediction=prediction,
            )

        # Chronological ordering: cycles must strictly increase per machine.
        last_cycle = session.query(Reading.cycle).filter_by(machine_id=reading.machine_id).order_by(
            Reading.cycle.desc()
        ).first()
        if last_cycle is not None and reading.cycle <= last_cycle[0]:
            raise ReadingIngestionError(
                f"out-of-order cycle {reading.cycle} for machine {reading.machine_id!r}: "
                f"latest stored cycle is {last_cycle[0]}"
            )

        # Build the per-machine feature frame: history + new reading,
        # transformed once with the frozen pipeline (no fit).
        transformed = self._transform_with_history(session, reading)
        last_row = transformed.iloc[[-1]]

        # Run inference on the newest row only.
        last_row_dict = last_row.iloc[0].to_dict()
        # Run inference on the newest transformed row only, using the model
        # directly (no double transform - the frame is already engineered).
        model = self.service._models.get((reading.dataset_id, "random_forest"))
        detector = self.service._models.get((reading.dataset_id, "isolation_forest"))

        train_sha = (self.service._manifests.get((reading.dataset_id, "random_forest")) or {}).get(
            "dataset_version", {}
        ).get("train_sha256") or ""
        model_version = f"{reading.dataset_id}:random_forest@{train_sha[:12]}" if train_sha else f"{reading.dataset_id}:random_forest"

        probabilities = model.predict_proba(last_row)
        failure_probability = float(probabilities[0, 1])

        anomaly_scores = detector.score(last_row)
        anomaly_labels = detector.predict(last_row)

        from predictive_maintenance.api.schemas import PredictionResponse

        prediction = PredictionResponse(
            dataset_id=reading.dataset_id,
            model="random_forest",
            model_version=model_version,
            predicted_at=_utc_now(),
            anomaly_score=float(anomaly_scores[0]),
            anomaly_status=bool(int(anomaly_labels[0]) == 1),
            failure_probability=failure_probability,
            failure_status=bool(failure_probability >= 0.5),
        )

        # Persist reading + prediction in the same transaction.
        db_reading = Reading(
            machine_id=reading.machine_id,
            dataset_id=reading.dataset_id,
            cycle=reading.cycle,
            timestamp=reading.timestamp,
            setting_1=reading.setting_1,
            setting_2=reading.setting_2,
            setting_3=reading.setting_3,
            s_values=_json_sensors(reading),
        )
        session.add(db_reading)
        session.flush()

        db_prediction = Prediction(
            reading_id=db_reading.id,
            machine_id=reading.machine_id,
            model=prediction.model,
            model_version=prediction.model_version,
            predicted_at=prediction.predicted_at,
            anomaly_score=prediction.anomaly_score,
            anomaly_status=prediction.anomaly_status,
            failure_probability=prediction.failure_probability,
            failure_status=prediction.failure_status,
        )
        session.add(db_prediction)
        session.flush()

        # Alerting based on the new prediction.
        if self.alert_service is not None:
            self.alert_service.evaluate(
                session,
                machine_id=reading.machine_id,
                prediction=prediction,
                prediction_id=db_prediction.id,
            )

        session.commit()
        return ReadingIngestResult(
            status=IngestionStatus.stored,
            machine_id=reading.machine_id,
            cycle=reading.cycle,
            reading_id=db_reading.id,
            prediction=prediction,
        )

    # ------------------------------------------------------------- history

    def _transform_with_history(self, session: Any, reading: ReadingIngest) -> pd.DataFrame:
        """Stored history + new reading -> single-row engineered feature frame.

        The rolling / time-series features in the Phase 2.1 pipeline need the
        trailing history of the same engine. We reconstruct that history from
        persisted readings, append the new reading, run ``pipeline.transform``
        (frozen statistics, no fit) and keep the last row.
        """
        pipeline = self.service._pipelines.get(reading.dataset_id)
        if pipeline is None:
            raise ModelServiceNotLoadedError(
                f"no preprocessing pipeline loaded for {reading.dataset_id}"
            )

        history_rows = (
            session.query(Reading)
            .filter_by(machine_id=reading.machine_id)
            .order_by(Reading.cycle.asc())
            .all()
        )
        rows: list[dict[str, Any]] = []
        for stored in history_rows:
            sensors = _parse_sensors(stored.s_values)
            row = {"unit": reading.machine_id, "cycle": stored.cycle}
            row.update(
                {
                    "setting_1": float(stored.setting_1),
                    "setting_2": float(stored.setting_2),
                    "setting_3": float(stored.setting_3),
                }
            )
            row.update({name: float(sensors.get(name, 0.0)) for name in SENSOR_COLUMNS if name in sensors})
            rows.append(row)
        rows.append(
            {
                "unit": reading.machine_id,
                "cycle": reading.cycle,
                "setting_1": float(reading.setting_1),
                "setting_2": float(reading.setting_2),
                "setting_3": float(reading.setting_3),
                **{name: float(getattr(reading, name)) for name in SENSOR_COLUMNS},
            }
        )
        frame = pd.DataFrame(rows)
        transformed = pipeline.transform(frame)
        return transformed

    def _get_prediction_for_reading(self, session: Any, reading_id: int) -> PredictionResponse | None:
        pred = session.query(Prediction).filter_by(reading_id=reading_id).first()
        if pred is None:
            return None
        return PredictionResponse(
            dataset_id="",
            model=pred.model,
            model_version=pred.model_version,
            predicted_at=pred.predicted_at,
            anomaly_score=pred.anomaly_score,
            anomaly_status=pred.anomaly_status,
            failure_probability=pred.failure_probability,
            failure_status=pred.failure_status,
        )


def _json_sensors(reading: ReadingIngest) -> str:
    import json

    return json.dumps({name: float(getattr(reading, name)) for name in SENSOR_COLUMNS})


def _parse_sensors(payload: str) -> dict[str, float]:
    import json

    return json.loads(payload) if payload else {}
