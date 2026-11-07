"""Phase 6.1: production deployment configuration tests.

Covers the development/production settings separation (``API_ENV`` with the
production CORS fail-fast rule), the deployment-driven SQLite path handling
(missing parent directory creation, absolute/drive-letter pass-through, the
additive ``database`` block on ``GET /ready`` and the shutdown engine hook.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predictive_maintenance import config
from predictive_maintenance.api import config as api_config
from predictive_maintenance.api import db, routes
from predictive_maintenance.api.config import Settings
from predictive_maintenance.api.db import models as db_models
from predictive_maintenance.api.dependencies import get_model_service, get_settings
from predictive_maintenance.api.service import ModelService


class TestEnvironmentProfile:
    """``API_ENV`` selects the development/production settings profile."""

    def test_defaults_to_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("API_ENV", raising=False)
        settings = api_config.get_settings()
        assert settings.env == "development"
        assert settings.is_production is False

    def test_invalid_profile_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", "staging")
        with pytest.raises(ValueError, match="API_ENV"):
            api_config.get_settings()

    def test_value_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", " Production ")
        monkeypatch.setenv("API_CORS_ORIGINS", "https://ops.example.com")
        settings = api_config.get_settings()
        assert settings.env == "production"
        assert settings.is_production is True


class TestProductionCorsGuard:
    """Production requires explicit CORS origins; wildcard only warns."""

    def test_unset_cors_fails_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", "production")
        monkeypatch.delenv("API_CORS_ORIGINS", raising=False)
        with pytest.raises(ValueError, match="API_CORS_ORIGINS"):
            api_config.get_settings()

    def test_empty_cors_fails_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", "production")
        monkeypatch.setenv("API_CORS_ORIGINS", "   ")
        with pytest.raises(ValueError, match="API_CORS_ORIGINS"):
            api_config.get_settings()

    def test_explicit_origins_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", "production")
        monkeypatch.setenv("API_CORS_ORIGINS", " https://dashboard.example.com , https://ops.example.com ")
        settings = api_config.get_settings()
        assert settings.is_production is True
        assert settings.cors_origin_list == [
            "https://dashboard.example.com",
            "https://ops.example.com",
        ]

    def test_explicit_wildcard_warns_but_boots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_ENV", "production")
        monkeypatch.setenv("API_CORS_ORIGINS", "*")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            settings = api_config.get_settings()
        cors_warnings = [w for w in caught if "CORS" in str(w.message)]
        assert settings.cors_origin_list == ["*"]
        assert cors_warnings, "production wildcard must emit a CORS warning"

    def test_development_wildcard_is_silent_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("API_ENV", raising=False)
        monkeypatch.delenv("API_CORS_ORIGINS", raising=False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            settings = api_config.get_settings()
        assert not [w for w in caught if "CORS" in str(w.message)]
        assert settings.cors_origin_list == ["*"]


class TestSqlitePaths:
    """Deployment-driven SQLite URL + filesystem handling."""

    def test_relative_url_resolves_against_project_root(self) -> None:
        url = db_models._normalize_sqlite_url("sqlite:///./data/predictive_maintenance.db")
        assert url == "sqlite:///" + str(config.ROOT / "data" / "predictive_maintenance.db")

    def test_memory_urls_untouched(self) -> None:
        for url in ("sqlite:///:memory:", "sqlite://"):
            assert db_models._normalize_sqlite_url(url) == url

    def test_posix_absolute_url_untouched(self) -> None:
        url = "sqlite:////var/lib/app/predictive_maintenance.db"
        assert db_models._normalize_sqlite_url(url) == url

    def test_windows_drive_letter_url_untouched(self) -> None:
        url = "sqlite:///C:/data/predictive_maintenance.db"
        assert db_models._normalize_sqlite_url(url) == url

    def test_init_db_creates_missing_parent_directory(self, tmp_path: Any) -> None:
        previous = (db_models._engine, db_models._SessionLocal)
        target = tmp_path / "nested" / "deep" / "app.db"
        engine = db.init_db(f"sqlite:///{target}")
        try:
            assert target.is_file()
            with engine.connect() as connection:  # schema initialized for real
                names = {
                    row[0]
                    for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
                }
            assert {"machines", "readings", "predictions", "alerts"} <= names
        finally:
            engine.dispose()
            db_models._engine, db_models._SessionLocal = previous


class TestReadinessInfo:
    """``db.readiness_info`` reports state without side effects."""

    def test_uninitialized_file_reported_absent(self, tmp_path: Any) -> None:
        target = tmp_path / "not-created.db"
        info = db.readiness_info(f"sqlite:///{target}")
        assert info["driver"] == "sqlite"
        assert info["initialized"] == (db_models._engine is not None)
        assert info["file"] == str(target)
        assert info["file_exists"] is False

    def test_existing_file_reported_present(self, tmp_path: Any) -> None:
        target = tmp_path / "exists.db"
        target.write_bytes(b"")
        info = db.readiness_info(f"sqlite:///{target}")
        assert info["file_exists"] is True

    def test_memory_url_has_no_file(self) -> None:
        info = db.readiness_info("sqlite:///:memory:")
        assert "file" not in info
        assert "file_exists" not in info

    def test_non_sqlite_url(self) -> None:
        info = db.readiness_info("postgresql://db.example.com/predictive_maintenance")
        assert info["driver"] == "other"
        assert "file" not in info


class TestShutdownEngine:
    """Shutdown disposes pooled connections without poisoning module state."""

    def test_no_op_when_never_initialized(self) -> None:
        previous = (db_models._engine, db_models._SessionLocal)
        db_models._engine, db_models._SessionLocal = None, None
        try:
            db.shutdown_engine()
            db.shutdown_engine()  # idempotent
        finally:
            db_models._engine, db_models._SessionLocal = previous

    def test_engine_remains_usable_after_dispose(self, tmp_path: Any) -> None:
        previous = (db_models._engine, db_models._SessionLocal)
        target = tmp_path / "shutdown.db"
        db.init_db(f"sqlite:///{target}")
        try:
            session = db.get_session()
            session.add(db.Machine(machine_id="SHUTDOWN-TEST", dataset_id="FD001"))
            session.commit()
            db.shutdown_engine()
            # disposed pool, still the same engine globals: a new session
            # transparently opens a fresh connection and finds old data
            session = db.get_session()
            row = session.query(db.Machine).filter_by(machine_id="SHUTDOWN-TEST").one()
            assert row.dataset_id == "FD001"
            session.close()
        finally:
            db_models._engine, db_models._SessionLocal = previous


class TestReadyEndpointDatabaseBlock:
    """/ready carries an additive, informational ``database`` block."""

    @staticmethod
    def _client(tmp_path: Any) -> TestClient:
        service = ModelService(model_dir=tmp_path / "absent-models")
        service.load()
        app = FastAPI()
        app.include_router(routes.health.router)
        app.dependency_overrides[get_settings] = lambda: Settings(
            cors_origins="http://test", database_url=f"sqlite:///{tmp_path / 'ready.db'}"
        )
        app.dependency_overrides[get_model_service] = lambda: service
        return TestClient(app)

    def test_database_block_present_and_shape(self, tmp_path: Any) -> None:
        with self._client(tmp_path) as client:
            body = client.get("/ready").json()
        assert body["ready"] is False  # empty model catalogue
        database = body["database"]
        assert database["driver"] == "sqlite"
        assert isinstance(database["initialized"], bool)
        assert database["file"].endswith("ready.db")
        assert database["file_exists"] is False
        # pre-existing contract unaffected
        assert set(body["datasets"]) == set(config.DATASET_IDS)
