"""Database layer for Phase 3.5: SQLite persistence via SQLAlchemy.

The database stores machines, their sensor readings, model predictions and
alerts. Schema initialization is done with ``Base.metadata.create_all`` at
application startup (documented below); no migration tool is required for
this phase — the schema is versioned in code and recreated when the database
file is removed.

Tables:

* ``machines``      - one row per ingested machine (identity + dataset)
* ``readings``      - one row per stored sensor reading (deduped by machine+cycle)
* ``predictions``   - one row per stored model prediction (references a reading)
* ``alerts``        - one row per generated alert (references a prediction, optional)

All timestamps are stored as ISO-8601 UTC strings.

Configuration
-------------
The database URL is environment-driven: ``API_DATABASE_URL`` (default
``sqlite:///./data/predictive_maintenance.db``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from predictive_maintenance.api.config import get_settings


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Machine(Base):
    """Identity of an ingested machine."""

    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(8), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    __table_args__ = (Index("ix_machines_dataset_id", "dataset_id"),)


class Reading(Base):
    """A stored sensor reading for one machine/cycle."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(8), nullable=False)
    cycle: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    setting_1: Mapped[float] = mapped_column(nullable=False)
    setting_2: Mapped[float] = mapped_column(nullable=False)
    setting_3: Mapped[float] = mapped_column(nullable=False)
    s_values: Mapped[str] = mapped_column(Text, nullable=False)  # JSON map s1..s21 -> float
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (
        Index("ix_readings_machine_cycle", "machine_id", "cycle", unique=True),
        Index("ix_readings_machine_time", "machine_id", "timestamp"),
    )


class Prediction(Base):
    """A stored model prediction for one reading."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("readings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    machine_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(nullable=True)
    anomaly_status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    failure_probability: Mapped[float | None] = mapped_column(nullable=True)
    failure_status: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Alert(Base):
    """A generated alert for one machine."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    prediction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_alerts_machine_status", "machine_id", "status"),
        Index("ix_alerts_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

_engine: Any = None
_SessionLocal: Any = None


def _normalize_sqlite_url(url: str) -> str:
    """Resolve relative SQLite paths against the project root (config.ROOT).

    Absolute paths pass through untouched: on POSIX an absolute path is
    spelled with four slashes (``sqlite:////abs/dir/app.db``), and on Windows
    a drive-letter path (``sqlite:///C:/data/app.db``) starts with a letter +
    ``:`` prefix that would otherwise be misread as a project-relative path.
    """
    if url.startswith("sqlite:///"):
        from predictive_maintenance import config

        relative = url[len("sqlite:///") :]
        is_windows_drive = len(relative) > 1 and relative[1] == ":"
        if (
            relative
            and not relative.startswith("/")
            and not relative.startswith(":")
            and not is_windows_drive
        ):
            return "sqlite:///" + str(config.ROOT / relative)
    return url


def init_db(database_url: str | None = None) -> Any:
    """Create the SQLAlchemy engine + session factory and initialize the schema.

    Safe to call multiple times: ``create_all`` only creates missing tables.
    Returns the engine (mostly useful for tests).
    """
    global _engine, _SessionLocal
    settings = get_settings()
    url = database_url or settings.database_url
    url = _normalize_sqlite_url(url)
    if url.startswith("sqlite:///"):
        sqlite_path = url[len("sqlite:///") :]
        # SQLite creates the database file on demand but never the missing
        # parent directories: create the folder so a fresh checkout/container
        # volume does not fail with "unable to open database file".
        if sqlite_path and not sqlite_path.startswith(":"):
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    _engine = engine
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine


def get_session() -> Any:
    """Return a new SQLAlchemy session (caller is responsible for closing)."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def get_session_dependency() -> Iterator[Any]:
    """FastAPI request-scoped session, guaranteed to be closed.

    ``get_session`` returns a bare session, which suits programmatic callers
    but gives FastAPI no teardown hook; a route that relies on it leaks the
    pooled connection until GC. SQLite connections are pooled (5 + 10
    overflow), so leaked sessions eventually exhaust the pool and DB-backed
    requests hang for ``pool_timeout`` (30s) and then fail. Every route must
    therefore acquire its session through this generator dependency.
    """
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_engine() -> Any:
    if _engine is None:
        init_db()
    return _engine


def shutdown_engine() -> None:
    """Release the engine's pooled connections (application shutdown hook).

    Idempotent and safe to call before initialization (no-op). The module
    globals are deliberately NOT reset: a disposed engine remains usable, so
    any ``get_session()`` after shutdown transparently opens a fresh pooled
    connection against the same database - this mirrors the restart-safe
    pattern the persistence tests rely on and avoids lazily re-initializing
    against a different URL.
    """
    if _engine is not None:
        _engine.dispose()


def readiness_info(database_url: str | None = None) -> dict[str, Any]:
    """Side-effect-free database snapshot for ``GET /ready`` (additive field).

    Reports what is *configured* and what exists *now*; it never creates the
    engine or the schema, so operators can distinguish "configured but not
    yet initialized" from "initialized and reachable". SQLite single-writer
    concurrency is a documented deployment limitation (see docs/deployment.md)
    and is not measured here.

    * ``driver``       - ``sqlite`` or ``other`` (from the URL only)
    * ``initialized``  - the process engine already exists (bool)
    * ``file``/``file_exists`` - SQLite only: resolved file path and presence
    """
    url = _normalize_sqlite_url(database_url or get_settings().database_url)
    info: dict[str, Any] = {
        "driver": "sqlite" if url.startswith("sqlite") else "other",
        "initialized": _engine is not None,
    }
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///") :]
        if raw and not raw.startswith(":"):
            path = Path(raw)
            info["file"] = str(path)
            info["file_exists"] = path.is_file()
    return info
