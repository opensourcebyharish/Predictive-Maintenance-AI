"""Pydantic request/response contracts for the Phase 3 prediction API.

The request body carries a single engine-cycle reading: the raw C-MAPSS
columns (``unit``, ``cycle``, three operating settings, sensors ``s1``-``s21``).
The response always carries model version + prediction timestamp plus the
score/probability and status produced by the selected model kind:

* ``isolation_forest`` -> anomaly score + anomaly status
* ``random_forest`` / ``xgboost`` -> failure probability + failure status
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS

SENSOR_NAMES: list[str] = list(SENSOR_COLUMNS)


def _build_engine_reading_model() -> type[BaseModel]:
    """One row of raw C-MAPSS telemetry: keys, settings, sensors."""
    field_definitions: dict[str, tuple[type, Any]] = {
        "unit": (int, Field(gt=0, description="Engine unit id")),
        "cycle": (int, Field(gt=0, description="Cycle within the engine trajectory")),
    }
    for name in OP_SETTING_COLUMNS:
        field_definitions[name] = (float, Field(..., description=f"Operating setting {name}"))
    for name in SENSOR_NAMES:
        field_definitions[name] = (float, Field(..., description=f"Sensor signal {name}"))
    return create_model("EngineReading", **field_definitions)  # type: ignore[call-overload]


# Materialised once at import time so OpenAPI renders a stable schema.
EngineReading = _build_engine_reading_model()


class PredictRequest(BaseModel):
    """Inference request for one engine-cycle reading."""

    dataset_id: str = Field(
        pattern=r"^FD00[1-4]$",
        description="C-MAPSS subset the model was trained on",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model kind: isolation_forest, random_forest or xgboost. "
        "Defaults to the subset's best model (chosen on validation metrics).",
    )
    reading: EngineReading


class PredictionResponse(BaseModel):
    """Inference result: health/anomaly and failure signals plus provenance."""

    dataset_id: str = Field(description="C-MAPSS subset")
    model: str = Field(description="Model kind used for the prediction")
    model_version: str = Field(description="Dataset:model@source checksum (traceability)")
    predicted_at: datetime = Field(description="UTC timestamp of the prediction")
    anomaly_score: Optional[float] = Field(
        default=None, description="Isolation Forest anomaly score (higher = more anomalous)"
    )
    anomaly_status: Optional[bool] = Field(
        default=None, description="True when the detector flags the reading as anomalous"
    )
    failure_probability: Optional[float] = Field(
        default=None, description="P(engine fails within the failure horizon)"
    )
    failure_status: Optional[bool] = Field(
        default=None, description="True when failure probability >= 0.5"
    )

    def model_post_init(self, __context: Any) -> None:
        if self.predicted_at.tzinfo is None:
            self.predicted_at = self.predicted_at.replace(tzinfo=timezone.utc)
