"""Phase 3.3: sensor ingestion routes.

POST /readings - accept validated sensor readings for FD001–FD004, run model
inference, persist reading + prediction + alerts transactionally, and return
the stored reading id and corresponding prediction.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from predictive_maintenance.api import db
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.ingestion import (
    ReadingIngestionError,
    ReadingIngestionService,
    ModelServiceNotLoadedError,
)
from predictive_maintenance.api.schemas import (
    BatchReadingIngestRequest,
    BatchReadingIngestResponse,
    ReadingIngest,
    ReadingIngestResult,
)
from predictive_maintenance.api.service import ModelService

router = APIRouter(tags=["ingestion"])


def get_ingestion_service(
    service: ModelService = Depends(get_model_service),
) -> ReadingIngestionService:
    return ReadingIngestionService(service=service)


@router.post(
    "/readings",
    response_model=ReadingIngestResult,
    status_code=status.HTTP_200_OK,
)
def ingest_reading(
    reading: ReadingIngest,
    ingestion: ReadingIngestionService = Depends(get_ingestion_service),
) -> ReadingIngestResult:
    """Ingest a single sensor reading.

    The reading is validated, stored (unless a duplicate of an existing
    ``machine_id`` + ``cycle``), scored through the Phase 2 model service,
    and the reading + prediction are persisted in one transaction.
    """
    try:
        return ingestion.ingest(reading)
    except ReadingIngestionError as exc:
        raise HTTPException(status_code=409, detail={"error": "ingestion_error", "message": str(exc)})
    except ModelServiceNotLoadedError as exc:
        raise HTTPException(status_code=503, detail={"error": "model_not_loaded", "message": str(exc)})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"error": "ingestion_error", "message": str(exc)})


@router.post(
    "/readings/batch",
    response_model=BatchReadingIngestResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_readings_batch(
    batch: BatchReadingIngestRequest,
    ingestion: ReadingIngestionService = Depends(get_ingestion_service),
) -> BatchReadingIngestResponse:
    """Ingest multiple sensor readings in one request.

    Each reading is processed independently: valid readings are stored and
    scored, duplicates are returned as-is, and malformed / out-of-order
    readings are rejected without aborting the batch.
    """
    return ingestion.ingest_batch(batch.readings)
