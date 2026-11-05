"""Phase 3.6: alert engine.

Generates alerts from model predictions, enforces alert deduplication and
tracks the alert lifecycle (active → acknowledged → resolved).

Alert types:

* ``anomaly_detected``       - Isolation Forest flags the reading anomalous
* ``elevated_failure_risk``  - failure probability >= elevated threshold
* ``critical_failure_risk``  - failure probability >= critical threshold
* ``machine_recovered``      - machine returned to healthy after an alert

Design notes:

* At most one *active* alert per ``(machine_id, alert_type)`` - consecutive
  anomalous readings do not spawn duplicate alerts.
* An alert is created only on a state transition and resolved when the
  machine returns to a healthy state; resolving the last active alert for a
  machine emits ``machine_recovered``.
* Severity is derived from the alert type (configurable thresholds drive the
  failure-risk types).
* Alert *delivery* is intentionally separated from generation: this module
  only persists alerts; a notifier can be plugged in later by observing the
  ``alerts`` table / ``GET /alerts``.
"""

from __future__ import annotations

from typing import Any

from predictive_maintenance import config
from predictive_maintenance.api import db
from predictive_maintenance.api.db.models import Alert
from predictive_maintenance.api.schemas import AlertCreate, PredictionResponse

__all__ = ["AlertService"]


class AlertSeverity(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertService:
    """Threshold-based alert generation with deduplication."""

    def __init__(
        self,
        elevated_threshold: float | None = None,
        critical_threshold: float | None = None,
        anomaly_enabled: bool | None = None,
    ) -> None:
        from predictive_maintenance.api.config import get_settings as _gs

        s = _gs()
        self.elevated_threshold = (
            elevated_threshold if elevated_threshold is not None else s.alert_elevated_failure
        )
        self.critical_threshold = (
            critical_threshold if critical_threshold is not None else s.alert_critical_failure
        )
        self.anomaly_enabled = (
            anomaly_enabled if anomaly_enabled is not None else s.alert_anomaly_enabled
        )

    # ------------------------------------------------------------- public API

    def evaluate(
        self,
        session: Any,
        machine_id: str,
        prediction: PredictionResponse,
        prediction_id: int | None = None,
    ) -> None:
        """Inspect one prediction and create / resolve alerts as needed.

        Called within the ingestion transaction so alert state stays
        consistent with stored predictions.
        """
        from predictive_maintenance.api.config import get_settings as _gs

        settings = _gs()
        elevated = self.elevated_threshold
        critical = self.critical_threshold
        anomaly_enabled = self.anomaly_enabled

        prob = prediction.failure_probability or 0.0
        is_anomaly = bool(prediction.anomaly_status) and anomaly_enabled
        is_critical = prob >= critical
        is_elevated = prob >= elevated and not is_critical

        # Determine the machine's current alert-worthy state.
        if is_critical:
            target_type, target_severity = "critical_failure_risk", AlertSeverity.CRITICAL
        elif is_elevated:
            target_type, target_severity = "elevated_failure_risk", AlertSeverity.HIGH
        elif is_anomaly:
            target_type, target_severity = "anomaly_detected", AlertSeverity.MEDIUM
        else:
            target_type = None  # healthy

        # Resolve alerts that no longer apply.
        active = self._active_alerts(session, machine_id)
        for alert in active:
            if target_type is not None and alert.alert_type == target_type:
                # Same type still active: keep it (dedup), just touch nothing.
                continue
            if target_type is None or alert.alert_type != target_type:
                self._resolve(session, alert)

        # Create the target alert if it does not already exist (dedup).
        if target_type is not None:
            existing = next((a for a in active if a.alert_type == target_type), None)
            if existing is None:
                message = self._message(target_type, prediction)
                self._create(
                    session,
                    AlertCreate(
                        machine_id=machine_id,
                        alert_type=target_type,  # type: ignore[arg-type]
                        severity=target_severity,  # type: ignore[arg-type]
                        prediction_id=prediction_id,
                        model_version=prediction.model_version,
                        message=message,
                    ),
                )

        # If the machine is healthy and we resolved at least one alert, emit
        # a single recovery alert (deduplicated like any other type).
        if target_type is None and any(a.alert_type != "machine_recovered" for a in active):
            existing_recovery = next(
                (a for a in active if a.alert_type == "machine_recovered"), None
            )
            if existing_recovery is None:
                self._create(
                    session,
                    AlertCreate(
                        machine_id=machine_id,
                        alert_type="machine_recovered",  # type: ignore[arg-type]
                        severity=AlertSeverity.LOW,
                        prediction_id=prediction_id,
                        model_version=prediction.model_version,
                        message=(
                            f"Machine {machine_id} returned to a healthy state "
                            f"after previous alerts were resolved."
                        ),
                    ),
                )

    # ------------------------------------------------------------- internals

    @staticmethod
    def _active_alerts(session: Any, machine_id: str) -> list[Any]:
        return (
            session.query(Alert)
            .filter_by(machine_id=machine_id, status="active")
            .all()
        )

    @classmethod
    def _create(cls, session: Any, create: AlertCreate) -> None:
        alert = Alert(
            machine_id=create.machine_id,
            alert_type=create.alert_type,
            severity=create.severity,
            status="active",
            prediction_id=create.prediction_id,
            model_version=create.model_version,
            message=create.message,
        )
        session.add(alert)
        session.flush()

    @classmethod
    def _resolve(cls, session: Any, alert: Any) -> None:
        alert.status = "resolved"
        alert.resolved_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    @staticmethod
    def _message(alert_type: str, prediction: PredictionResponse) -> str:
        if alert_type == "critical_failure_risk":
            return (
                f"Critical failure risk (P={prediction.failure_probability:.3f}) "
                f"using {prediction.model} ({prediction.model_version})."
            )
        if alert_type == "elevated_failure_risk":
            return (
                f"Elevated failure risk (P={prediction.failure_probability:.3f}) "
                f"using {prediction.model} ({prediction.model_version})."
            )
        if alert_type == "anomaly_detected":
            return (
                f"Anomaly detected (score={prediction.anomaly_score:.3f}) "
                f"using {prediction.model} ({prediction.model_version})."
            )
        return f"Alert for machine using {prediction.model}."
