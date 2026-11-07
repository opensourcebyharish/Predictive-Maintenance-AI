"""Runtime settings for the Phase 3 backend, sourced from environment variables.

No external settings library is required: everything is plain ``os.environ``
with documented defaults, keeping the dependency surface small and the
behaviour predictable on Windows dev machines as well as in containers.

Environment variables (all prefixed with ``API_``):

  API_ENV                      deployment profile: development | production (default: development).
                               ``production`` is a fail-fast profile: startup aborts when
                               API_CORS_ORIGINS is unset/empty, and warns when it lists '*'.
  API_APP_NAME                 application title shown in OpenAPI  (default: predictive-maintenance-ai)
  API_APP_VERSION              version reported by GET /health (default: 0.2.0)
  API_HOST                     bind host for uvicorn (default: 127.0.0.1)
  API_PORT                     bind port for uvicorn (default: 8000)
  API_MODEL_DIR                directory holding ``models/<FD00X>/...`` artefacts (default: models/)
  API_CORS_ORIGINS             comma-separated CORS origin list (default: "*"; required in production)
  API_LOG_LEVEL                uvicorn log level (default: info)
  API_DATABASE_URL             SQLAlchemy database URL (default: sqlite:///./data/predictive_maintenance.db)
  API_ALERT_ELEVATED_FAILURE   failure probability above which ``elevated_failure_risk`` fires (default: 0.5)
  API_ALERT_CRITICAL_FAILURE   failure probability above which ``critical_failure_risk`` fires (default: 0.8)
  API_ALERT_ANOMALY_ENABLED    whether anomaly alerts are generated (default: true)
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

VALID_ENVIRONMENTS: tuple[str, ...] = ("development", "production")


@dataclass(frozen=True)
class Settings:
    """All runtime configuration, readable both as attributes and as a dict."""

    app_name: str = "predictive-maintenance-ai"
    app_version: str = "0.2.0"
    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    model_dir: str = "models"
    cors_origins: str = "*"
    log_level: str = "info"
    database_url: str = "sqlite:///./data/predictive_maintenance.db"
    alert_elevated_failure: float = 0.5
    alert_critical_failure: float = 0.8
    alert_anomaly_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables (missing -> defaults)."""

        def _float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            return float(raw)

        def _bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None or raw.strip() == "":
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        env = (os.getenv("API_ENV") or cls.env).strip().lower()
        if env not in VALID_ENVIRONMENTS:
            raise ValueError(f"API_ENV must be one of {list(VALID_ENVIRONMENTS)}, got {env!r}")
        cors_raw = os.getenv("API_CORS_ORIGINS")
        if env == "production":
            # Fail fast: the wildcard default is only acceptable for local dev,
            # where the backend would otherwise reject every browser origin a
            # developer might use. Production must name its origins explicitly.
            if cors_raw is None or cors_raw.strip() == "":
                raise ValueError(
                    "API_CORS_ORIGINS must list explicit origins when API_ENV=production "
                    "(e.g. 'https://dashboard.example.com'); the wildcard default '*' "
                    "would let any website call the API from a browser."
                )
            if "*" in {origin.strip() for origin in cors_raw.split(",")}:
                warnings.warn(
                    "API_CORS_ORIGINS contains '*' while API_ENV=production: "
                    "every origin is allowed and requests are not restricted by CORS.",
                    stacklevel=2,
                )

        return cls(
            app_name=os.getenv("API_APP_NAME", cls.app_name),
            app_version=os.getenv("API_APP_VERSION", cls.app_version),
            env=env,
            host=os.getenv("API_HOST", cls.host),
            port=_int("API_PORT", cls.port),
            model_dir=os.getenv("API_MODEL_DIR", cls.model_dir),
            cors_origins=os.getenv("API_CORS_ORIGINS", cls.cors_origins),
            log_level=os.getenv("API_LOG_LEVEL", cls.log_level),
            database_url=os.getenv("API_DATABASE_URL", cls.database_url),
            alert_elevated_failure=_float("API_ALERT_ELEVATED_FAILURE", cls.alert_elevated_failure),
            alert_critical_failure=_float("API_ALERT_CRITICAL_FAILURE", cls.alert_critical_failure),
            alert_anomaly_enabled=_bool("API_ALERT_ANOMALY_ENABLED", cls.alert_anomaly_enabled),
        )

    @property
    def is_production(self) -> bool:
        """True when the API runs under the ``production`` profile (``API_ENV=production``)."""
        return self.env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        """``API_CORS_ORIGINS`` split into a list (empty -> ``["*"]``)."""

        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["*"]

    def to_dict(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "env": self.env,
            "host": self.host,
            "port": self.port,
            "model_dir": self.model_dir,
            "cors_origins": self.cors_origins,
            "log_level": self.log_level,
            "database_url": self.database_url,
            "alert_elevated_failure": self.alert_elevated_failure,
            "alert_critical_failure": self.alert_critical_failure,
            "alert_anomaly_enabled": self.alert_anomaly_enabled,
        }


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def get_settings() -> Settings:
    """Read settings from the environment (defaults when unset)."""
    return Settings.from_env()
