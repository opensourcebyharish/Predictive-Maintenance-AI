"""Phase 3.4: machine monitoring routes.

GET /machines
GET /machines/{machine_id}
GET /machines/{machine_id}/readings
GET /machines/{machine_id}/predictions
GET /machines/{machine_id}/health
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from predictive_maintenance.api import db
from predictive_maintenance.api.monitoring import MachineMonitoringService
from predictive_maintenance.api.schemas import (
    MachineDetail,
    MachineSummary,
    PaginatedPredictions,
    PaginatedReadings,
)

router = APIRouter(tags=["machines"])


def get_monitoring_service() -> MachineMonitoringService:
    return MachineMonitoringService()


@router.get("/machines", response_model=list[MachineSummary], status_code=status.HTTP_200_OK)
def list_machines(
    monitoring: MachineMonitoringService = Depends(get_monitoring_service),
    session: Any = Depends(db.get_session_dependency),
) -> list[MachineSummary]:
    """List all ingested machines with their latest health."""
    return monitoring.list_machines(session)


@router.get(
    "/machines/{machine_id}",
    response_model=MachineDetail,
    status_code=status.HTTP_200_OK,
)
def get_machine(
    machine_id: str = Path(..., min_length=1, description="Machine / engine identifier"),
    monitoring: MachineMonitoringService = Depends(get_monitoring_service),
    session: Any = Depends(db.get_session_dependency),
) -> MachineDetail:
    """Return full detail for one machine: latest reading, prediction, alerts."""
    detail = monitoring.get_machine(session, machine_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": "machine_not_found", "message": f"no machine {machine_id!r}"})
    return detail


@router.get(
    "/machines/{machine_id}/readings",
    response_model=PaginatedReadings,
    status_code=status.HTTP_200_OK,
)
def get_machine_readings(
    machine_id: str = Path(..., min_length=1),
    limit: int = Query(50, ge=1, le=1000, description="Maximum readings to return"),
    offset: int = Query(0, ge=0, description="Number of readings to skip"),
    monitoring: MachineMonitoringService = Depends(get_monitoring_service),
    session: Any = Depends(db.get_session_dependency),
) -> PaginatedReadings:
    """Paginated chronological reading history for one machine."""
    return monitoring.get_readings(session, machine_id, limit=limit, offset=offset)


@router.get(
    "/machines/{machine_id}/predictions",
    response_model=PaginatedPredictions,
    status_code=status.HTTP_200_OK,
)
def get_machine_predictions(
    machine_id: str = Path(..., min_length=1),
    limit: int = Query(50, ge=1, le=1000, description="Maximum predictions to return"),
    offset: int = Query(0, ge=0, description="Number of predictions to skip"),
    monitoring: MachineMonitoringService = Depends(get_monitoring_service),
    session: Any = Depends(db.get_session_dependency),
) -> PaginatedPredictions:
    """Paginated prediction history for one machine (newest first)."""
    return monitoring.get_predictions(session, machine_id, limit=limit, offset=offset)


@router.get(
    "/machines/{machine_id}/health",
    status_code=status.HTTP_200_OK,
)
def get_machine_health(
    machine_id: str = Path(..., min_length=1),
    monitoring: MachineMonitoringService = Depends(get_monitoring_service),
    session: Any = Depends(db.get_session_dependency),
) -> dict[str, Any]:
    """Latest health snapshot for one machine."""
    health = monitoring.get_health(session, machine_id)
    if health is None:
        raise HTTPException(status_code=404, detail={"error": "machine_not_found", "message": f"no machine {machine_id!r}"})
    return health
