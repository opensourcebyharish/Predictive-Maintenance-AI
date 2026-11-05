"""Phase 3.1: health and readiness endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

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
def ready(service: ModelService = Depends(get_model_service)) -> dict[str, Any]:
    """Readiness check: are the required preprocessing artefacts and models loaded?"""
    return service.readiness()
