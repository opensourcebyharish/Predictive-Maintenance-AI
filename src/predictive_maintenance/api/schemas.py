"""Pydantic request/response contracts for the Phase 3 prediction API.

The request body carries a single engine-cycle reading: the raw C-MAPSS
columns (``unit``, ``cycle``, three operating settings, sensors ``s1``-``s21``).
The response always carries model version + prediction timestamp plus the
score/probability and status produced by the selected model kind:

* ``isolation_forest`` -> anomaly score + anomaly status
* ``random_forest`` / ``xgboost`` -> failure probability + failure status

Phase 3.3-3.6 adds sensor ingestion, machine monitoring and alerting
contracts on top of these core prediction schemas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS

SENSOR_NAMES: list[str] = list(SENSOR_COLUMNS)
DATASET_IDS: tuple[str, ...] = config.DATASET_IDS


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


# ---------------------------------------------------------------------------
# Phase 3.3: sensor ingestion schemas
# ---------------------------------------------------------------------------

class ReadingIngestRequest(BaseModel):
    """A single sensor reading submitted for storage + inference."""

    machine_id: str = Field(
        min_length=1,
        description="Machine / engine identifier (maps to the C-MAPSS unit column)",
    )
    dataset_id: str = Field(
        pattern=r"^FD00[1-4]$",
        description="C-MAPSS subset whose model/features are used for inference",
    )
    cycle: int = Field(gt=0, description="Cycle within the machine trajectory")
    timestamp: datetime = Field(description="UTC timestamp of the reading")
    setting_1: float = Field(..., description="Operating setting 1")
    setting_2: float = Field(..., description="Operating setting 2")
    setting_3: float = Field(..., description="Operating setting 3")

    @property
    def sensor_values(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in SENSOR_NAMES}


def _build_ingest_reading_model() -> type[BaseModel]:
    """ReadingIngestRequest with explicit s1..s21 fields for OpenAPI."""
    base = {name: (float, Field(..., description=f"Sensor signal {name}")) for name in SENSOR_NAMES}
    return create_model(
        "ReadingIngest",
        __base__=ReadingIngestRequest,
        **base,  # type: ignore[arg-type]
    )  # type: ignore[call-overload]


# Materialised once at import time so OpenAPI renders the s1..s21 columns.
ReadingIngest = _build_ingest_reading_model()


class BatchReadingIngestRequest(BaseModel):
    """Multiple sensor readings submitted in one request."""

    readings: list[ReadingIngest] = Field(..., min_length=1, description="Readings to ingest")


class IngestionStatus(str, Enum):
    stored = "stored"
    duplicate = "duplicate"
    rejected = "rejected"


class ReadingIngestResult(BaseModel):
    """Outcome of ingesting one reading."""

    status: IngestionStatus
    machine_id: str
    cycle: int
    reading_id: Optional[int] = Field(default=None, description="Stored reading id (null when duplicate/rejected)")
    prediction: Optional[PredictionResponse] = Field(default=None, description="Model prediction for the stored reading")
    error: Optional[str] = Field(default=None, description="Error message when rejected")


class BatchReadingIngestResponse(BaseModel):
    """Outcome of a batch ingestion request."""

    results: list[ReadingIngestResult]
    stored: int = Field(description="Number of readings newly stored")
    duplicates: int = Field(description="Number of duplicate readings returned as-is")
    rejected: int = Field(description="Number of rejected readings")


# ---------------------------------------------------------------------------
# Phase 3.4: machine monitoring schemas
# ---------------------------------------------------------------------------

class MachineHealth(str, Enum):
    healthy = "healthy"
    anomalous = "anomalous"
    elevated_risk = "elevated_risk"
    critical_risk = "critical_risk"
    unknown = "unknown"


class MachineSummary(BaseModel):
    """Lightweight machine entry for list endpoints."""

    machine_id: str
    dataset_id: str
    reading_count: int
    first_cycle: Optional[int] = None
    last_cycle: Optional[int] = None
    latest_reading_at: Optional[datetime] = None
    health: MachineHealth = MachineHealth.unknown


class MachineDetail(MachineSummary):
    """Full machine detail including latest reading, prediction and alerts."""

    latest_sensor_values: Optional[dict[str, float]] = None
    latest_prediction: Optional[PredictionRecord] = None
    active_alerts: int = 0


class ReadingRecord(BaseModel):
    """A stored sensor reading."""

    id: int
    machine_id: str
    cycle: int
    timestamp: datetime
    setting_1: float
    setting_2: float
    setting_3: float
    sensor_values: dict[str, float]
    stored_at: datetime


class PredictionRecord(BaseModel):
    """A stored model prediction."""

    id: int
    reading_id: int
    machine_id: str
    model: str
    model_version: str
    predicted_at: datetime
    anomaly_score: Optional[float] = None
    anomaly_status: Optional[bool] = None
    failure_probability: Optional[float] = None
    failure_status: Optional[bool] = None


class PaginatedReadings(BaseModel):
    machine_id: str
    readings: list[ReadingRecord]
    limit: int
    offset: int
    total: int


class PaginatedPredictions(BaseModel):
    machine_id: str
    predictions: list[PredictionRecord]
    limit: int
    offset: int
    total: int


# ---------------------------------------------------------------------------
# Phase 3.6: alert schemas
# ---------------------------------------------------------------------------

class AlertType(str, Enum):
    anomaly_detected = "anomaly_detected"
    elevated_failure_risk = "elevated_failure_risk"
    critical_failure_risk = "critical_failure_risk"
    machine_recovered = "machine_recovered"


class AlertSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AlertStatus(str, Enum):
    active = "active"
    acknowledged = "acknowledged"
    resolved = "resolved"


class AlertRecord(BaseModel):
    """A generated alert."""

    id: int
    machine_id: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    prediction_id: Optional[int] = None
    model_version: Optional[str] = None
    message: str
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class AlertAcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field(default="operator", description="Who acknowledged the alert")


class AlertAcknowledgeResponse(BaseModel):
    alert_id: int
    status: AlertStatus
    acknowledged_at: datetime


class AlertSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_severity: dict[str, int]
    active_by_machine: dict[str, int]


class AlertCreate(BaseModel):
    """Internal contract used by the alert service to create an alert."""

    machine_id: str
    alert_type: AlertType
    severity: AlertSeverity
    prediction_id: Optional[int] = None
    model_version: Optional[str] = None
    message: str
