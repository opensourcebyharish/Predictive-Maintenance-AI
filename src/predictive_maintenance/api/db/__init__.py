"""Database package for Phase 3.5: SQLite persistence via SQLAlchemy."""

from predictive_maintenance.api.db.models import (
    Alert,
    Base,
    Machine,
    Prediction,
    Reading,
    get_engine,
    get_session,
    get_session_dependency,
    init_db,
    readiness_info,
    shutdown_engine,
)

__all__ = [
    "Alert",
    "Base",
    "Machine",
    "Prediction",
    "Reading",
    "get_engine",
    "get_session",
    "get_session_dependency",
    "init_db",
    "readiness_info",
    "shutdown_engine",
]
