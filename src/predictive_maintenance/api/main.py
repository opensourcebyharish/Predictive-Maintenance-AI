"""FastAPI application factory for the Phase 3 backend.

``create_app`` assembles the routers, CORS middleware and error handlers. The
model service is loaded at startup (best effort: failures are reported by
``GET /ready`` instead of crashing startup) and kept in memory for inference.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from predictive_maintenance.api.config import get_settings
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.routes import health, predict
from predictive_maintenance.api.service import (
    IncompatibleConfigurationError,
    ModelNotFoundError,
    PredictionServiceError,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Model-serving API for the Predictive Maintenance AI project "
        "(Phase 3: FastAPI backend; NASA C-MAPSS anomaly + failure models).",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ------------------------------------------------------------------ CORS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ state

    app.state.settings = settings
    app.state.service = get_model_service()

    @app.on_event("startup")
    def _load_artefacts_at_startup() -> None:
        """Load all trained artefacts once (best effort)."""
        try:
            app.state.service.load()
        except Exception:  # noqa: BLE001 - /ready surfaces load problems
            pass

    # ------------------------------------------------------------------ routers

    app.include_router(health.router)
    app.include_router(predict.router)

    # ------------------------------------------------------------------ error handlers

    @app.exception_handler(ModelNotFoundError)
    async def _not_found_handler(_request: Request, exc: ModelNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "model_not_found", "message": str(exc)})

    @app.exception_handler(IncompatibleConfigurationError)
    async def _incompatible_handler(_request: Request, exc: IncompatibleConfigurationError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "incompatible_configuration", "message": str(exc)})

    @app.exception_handler(PredictionServiceError)
    async def _service_handler(_request: Request, exc: PredictionServiceError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "prediction_error", "message": str(exc)})

    return app


app = create_app()
