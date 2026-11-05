"""Phase 3: FastAPI model-serving backend for the Predictive Maintenance AI project.

Package layout::

  api/
    __init__.py
    config.py          runtime settings from environment variables
    schemas.py         Pydantic request/response contracts
    service.py         ModelService: loads artifacts once, serves predictions
    dependencies.py    cached FastAPI dependencies (settings + service)
    main.py            application factory: CORS, error handlers, routers
    routes/
      __init__.py
      health.py        GET /health, GET /ready
      predict.py       POST /predict
"""

from predictive_maintenance.api.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
