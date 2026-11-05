"""Phase 3.2: prediction endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from predictive_maintenance.api.schemas import PredictionResponse, PredictRequest
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.service import (
    IncompatibleConfigurationError,
    ModelNotFoundError,
    PredictionServiceError,
    ModelService,
)

router = APIRouter(tags=["predict"])


@router.post("/predict", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
def predict(
    request: PredictRequest,
    service: ModelService = Depends(get_model_service),
) -> PredictionResponse:
    """Score one engine-cycle reading with the requested (or default) model.

    Returns anomaly score/status for ``isolation_forest`` and failure
    probability/status for ``random_forest``/``xgboost``, plus model version
    and a UTC prediction timestamp.
    """
    if not service.is_loaded:
        service.load()
    try:
        payload = service.predict(request.dataset_id, request.model, request.reading)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": "model_not_found", "message": str(exc)})
    except IncompatibleConfigurationError as exc:
        raise HTTPException(status_code=409, detail={"error": "incompatible_configuration", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": str(exc)})
    except PredictionServiceError as exc:
        raise HTTPException(status_code=500, detail={"error": "prediction_error", "message": str(exc)})
    return PredictionResponse(**payload)
