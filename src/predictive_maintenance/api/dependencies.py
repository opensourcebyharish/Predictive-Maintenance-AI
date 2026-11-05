"""Cached FastAPI dependencies for the Phase 3 backend.

Both dependencies are singletons for the process lifetime: settings are read
from the environment once and the model service loads artefacts once.
"""

from __future__ import annotations

from functools import lru_cache

from predictive_maintenance.api.config import Settings, get_settings as read_settings
from predictive_maintenance.api.service import ModelService


@lru_cache(maxsize=None)
def get_settings() -> Settings:
    """Application settings (environment variables, defaults otherwise)."""
    return read_settings()


@lru_cache(maxsize=None)
def get_model_service() -> ModelService:
    """Model service singleton; artefacts are loaded on first use / startup."""
    settings = get_settings()
    return ModelService(model_dir=settings.model_dir)
