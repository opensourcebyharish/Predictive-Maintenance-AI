"""Phase 3.6: alert routes.

GET /alerts
GET /alerts/summary
POST /alerts/{alert_id}/acknowledge
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from predictive_maintenance.api import db
from predictive_maintenance.api.schemas import (
    AlertAcknowledgeRequest,
    AlertAcknowledgeResponse,
    AlertRecord,
    AlertSummary,
)

router = APIRouter(tags=["alerts"])


def get_session_dependency() -> Any:
    return db.get_session


@router.get("/alerts", response_model=list[AlertRecord], status_code=status.HTTP_200_OK)
def list_alerts(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    machine_id: str | None = Query(None, description="Filter by machine id"),
    status: str | None = Query(None, description="Filter by alert status (active/acknowledged/resolved)"),
    session: Any = Depends(db.get_session_dependency),
) -> list[AlertRecord]:
    """List alerts with optional machine / status filtering and pagination."""
    query = session.query(db.Alert)
    if machine_id is not None:
        query = query.filter_by(machine_id=machine_id)
    if status is not None:
        query = query.filter_by(status=status)
    query = query.order_by(db.Alert.created_at.desc()).offset(offset).limit(limit)
    return [_alert_record(a) for a in query.all()]


@router.get("/alerts/summary", response_model=AlertSummary, status_code=status.HTTP_200_OK)
def alerts_summary(session: Any = Depends(db.get_session_dependency)) -> AlertSummary:
    """Aggregate alert counts by status, type, severity and machine."""
    rows = session.query(db.Alert).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    active_by_machine: dict[str, int] = {}
    for alert in rows:
        by_status[alert.status] = by_status.get(alert.status, 0) + 1
        by_type[alert.alert_type] = by_type.get(alert.alert_type, 0) + 1
        by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
        if alert.status == "active":
            active_by_machine[alert.machine_id] = active_by_machine.get(alert.machine_id, 0) + 1
    return AlertSummary(
        total=len(rows),
        by_status=by_status,
        by_type=by_type,
        by_severity=by_severity,
        active_by_machine=active_by_machine,
    )


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
    status_code=status.HTTP_200_OK,
)
def acknowledge_alert(
    alert_id: int = Path(..., ge=1, description="Alert identifier"),
    request: AlertAcknowledgeRequest | None = None,
    session: Any = Depends(db.get_session_dependency),
) -> AlertAcknowledgeResponse:
    """Acknowledge an active alert."""
    alert = session.query(db.Alert).filter_by(id=alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail={"error": "alert_not_found", "message": f"no alert {alert_id}"})
    if alert.status != "active":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "alert_not_active",
                "message": f"alert {alert_id} is {alert.status}, cannot acknowledge",
            },
        )
    from datetime import datetime, timezone

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = (request or AlertAcknowledgeRequest()).acknowledged_by
    session.commit()
    return AlertAcknowledgeResponse(
        alert_id=alert.id,
        status=alert.status,  # type: ignore[arg-type]
        acknowledged_at=alert.acknowledged_at,
    )


def _alert_record(alert: db.Alert) -> AlertRecord:
    return AlertRecord(
        id=alert.id,
        machine_id=alert.machine_id,
        alert_type=alert.alert_type,  # type: ignore[arg-type]
        severity=alert.severity,  # type: ignore[arg-type]
        status=alert.status,  # type: ignore[arg-type]
        prediction_id=alert.prediction_id,
        model_version=alert.model_version,
        message=alert.message,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
    )
