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

from datetime import datetime, timezone
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
    """Resolve relative SQLite paths against the project root (config.ROOT)."""
    if url.startswith("sqlite:///"):
        from predictive_maintenance import config

        relative = url[len("sqlite:///") :]
        if not relative.startswith("/") and not relative.startswith(":"):
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


def get_engine() -> Any:
    if _engine is None:
        init_db()
    return _engine
