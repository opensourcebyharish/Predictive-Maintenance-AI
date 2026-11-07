"""Phase 3.1: health and readiness endpoints.

Phase 6.1: ``GET /ready`` additionally carries an additive, informational
``database`` block produced by :func:`db.readiness_info` (driver, whether the
process engine is initialized, resolved SQLite file + presence). Consuming
clients can ignore unknown keys, so the existing contract is unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from predictive_maintenance.api import db
from predictive_maintenance.api.config import Settings
from predictive_maintenance.api.dependencies import get_model_service, get_settings
from predictive_maintenance.api.service import ModelService

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings), service: ModelService = Depends(get_model_service)) -> dict[str, Any]:
    """Liveness check: the API process is up and the service object exists."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "service_loaded": service.is_loaded,
    }


@router.get("/ready")
def ready(
    settings: Settings = Depends(get_settings), service: ModelService = Depends(get_model_service)
) -> dict[str, Any]:
    """Readiness: are the required preprocessing artefacts and models loaded.

    The top-level ``ready`` flag concerns the *model* artifacts only; the
    additive ``database`` block reports configured/observed database state
    without ever initializing anything.
    """
    payload = service.readiness()
    payload["database"] = db.readiness_info(settings.database_url)
    return payload
