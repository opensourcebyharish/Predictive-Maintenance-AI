"""Unit tests for the Phase 3 backend configuration (environment variables)."""

from __future__ import annotations

import os
from typing import Any

import pytest

from predictive_maintenance.api import config


def _env(**pairs: str) -> dict[str, str]:
    return {f"API_{key}": value for key, value in pairs.items()}


class TestSettingsDefaults:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in _env(app_name="x", app_version="y", host="h", port="9", model_dir="m", cors_origins="o", log_level="l"):
            monkeypatch.delenv(key, raising=False)
        settings = config.get_settings()
        assert settings.app_name == "predictive-maintenance-ai"
        assert settings.app_version == "0.2.0"
        assert settings.host == "127.0.0.1"
        assert settings.port == 8000
        assert settings.model_dir == "models"
        assert settings.cors_origins == "*"
        assert settings.log_level == "info"

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_APP_NAME", "test-app")
        monkeypatch.setenv("API_PORT", "9999")
        monkeypatch.setenv("API_MODEL_DIR", "/tmp/model-dir")
        monkeypatch.setenv("API_CORS_ORIGINS", " http://localhost:3000 , https://example.com ")
        settings = config.get_settings()
        assert settings.app_name == "test-app"
        assert settings.port == 9999
        assert settings.model_dir == "/tmp/model-dir"
        assert settings.cors_origin_list == ["http://localhost:3000", "https://example.com"]

    def test_cors_origins_empty_defaults_to_star(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_CORS_ORIGINS", "")
        settings = config.get_settings()
        assert settings.cors_origin_list == ["*"]

    def test_to_dict(self) -> None:
        settings = config.get_settings()
        data = settings.to_dict()
        assert set(data) == {
            "app_name", "app_version", "host", "port", "model_dir", "cors_origins",
            "log_level", "database_url", "alert_elevated_failure", "alert_critical_failure",
            "alert_anomaly_enabled",
        }
        assert isinstance(data["port"], int)


class TestGetSettingsCached:
    def test_same_object_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = config.get_settings()
        second = config.get_settings()
        assert first == second
