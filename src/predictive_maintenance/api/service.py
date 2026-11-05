"""Phase 3.2: model-loading and prediction service.

The service loads every trained Phase 2 artefact exactly once (at startup or
first request) and keeps it in memory for the lifetime of the process:

* a fitted ``PreprocessingPipeline`` per C-MAPSS subset
* Isolation Forest / Random Forest / XGBoost wrappers plus their JSON manifests

Inference never fits or refits anything: readings are transformed with the
frozen pipeline and scored with the in-memory model wrappers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS
from predictive_maintenance.models import datasets
from predictive_maintenance.models.datasets import _train_pipeline

PIPELINE_NAME = "preprocessing_pipeline"
MODEL_KINDS: tuple[str, ...] = ("isolation_forest", "random_forest", "xgboost")
# Best model per subset, chosen on validation metrics only (Phase 2.5 report).
DEFAULT_MODEL: dict[str, str] = {
    "FD001": "random_forest",
    "FD002": "random_forest",
    "FD003": "xgboost",
    "FD004": "xgboost",
}

SENSOR_NAMES: list[str] = list(SENSOR_COLUMNS)
READING_COLUMNS: list[str] = ["unit", "cycle", *OP_SETTING_COLUMNS, *SENSOR_NAMES]


class PredictionServiceError(Exception):
    """Base class for service-level failures."""


class ModelNotFoundError(PredictionServiceError):
    """Requested dataset/model is unknown or has no trained artefact."""


class IncompatibleConfigurationError(PredictionServiceError):
    """Manifest, pipeline and model disagree on features/horizon."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelService:
    """In-memory catalogue of fitted pipelines and models, loaded once."""

    def __init__(self, model_dir: str | Path | None = None) -> None:
        self.model_dir = Path(model_dir or config.MODELS_DIR)
        self._pipelines: dict[str, Any] = {}
        self._models: dict[tuple[str, str], Any] = {}
        self._manifests: dict[tuple[str, str], dict[str, Any]] = {}
        self._dataset_errors: dict[str, str] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ---------------------------------------------------------------- loading

    def load(self) -> None:
        """Load (or deterministically rebuild) all artefacts; never raises."""
        self._pipelines.clear()
        self._models.clear()
        self._manifests.clear()
        self._dataset_errors.clear()
        for dataset_id in config.DATASET_IDS:
            try:
                self._load_dataset(dataset_id)
            except Exception as exc:  # noqa: BLE001 - /ready surfaces per-dataset problems
                self._dataset_errors[dataset_id] = f"{type(exc).__name__}: {exc}"
        self._loaded = True

    def _load_dataset(self, dataset_id: str) -> None:
        dataset_root = self.model_dir / dataset_id
        pipeline_path = dataset_root / f"{PIPELINE_NAME}.joblib"
        if not pipeline_path.is_file():
            self._dataset_errors[dataset_id] = "preprocessing pipeline artefact missing"
            return  # no serving artefacts for this subset
        pipeline = joblib.load(pipeline_path)
        pipeline.check_fitted()
        self._pipelines[dataset_id] = pipeline
        for kind in MODEL_KINDS:
            joblib_path = dataset_root / f"{kind}.joblib"
            manifest_path = dataset_root / f"{kind}.json"
            if not joblib_path.is_file() or not manifest_path.is_file():
                continue  # model not trained yet; /ready reports it as missing
            model = joblib.load(joblib_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self._validate_artifact(dataset_id, kind, pipeline, model, manifest)
            self._models[(dataset_id, kind)] = model
            self._manifests[(dataset_id, kind)] = manifest

    def _load_pipeline(self, dataset_id: str) -> Any:
        """Fitted Phase 2.1 pipeline: persisted artefact first, deterministic rebuild otherwise.

        The rebuild happens once per process start - inference only ever calls
        ``transform`` on the returned pipeline.
        """
        path = self.model_dir / dataset_id / f"{PIPELINE_NAME}.joblib"
        if path.is_file():
            pipeline = joblib.load(path)
            pipeline.check_fitted()
            return pipeline
        pipeline = _train_pipeline(dataset_id)  # deterministic; identical to Phase 2.1 build
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(pipeline, path)
        except OSError:
            pass  # read-only deployments keep the in-memory pipeline
        return pipeline

    @staticmethod
    def _validate_artifact(
        dataset_id: str,
        kind: str,
        pipeline: Any,
        model: Any,
        manifest: dict[str, Any],
    ) -> None:
        """Reject artefacts whose feature contract disagrees (defensive; training keeps them in sync).

        Comparison is by feature *set*: training writes model, pipeline and
        manifest columns from the same derivation, so any divergence indicates
        a stale or mixed artefact. Column order is irrelevant because the
        matrix is built by name at inference time.
        """
        model_columns = set(model.feature_columns)
        pipeline_columns = set(pipeline.feature_columns)
        manifest_columns = set(manifest.get("feature_columns", []))
        if not (model_columns == pipeline_columns == manifest_columns):
            raise IncompatibleConfigurationError(
                f"feature contract mismatch for {dataset_id}/{kind}: "
                f"model has {len(model_columns)} features, pipeline {len(pipeline_columns)}, "
                f"manifest {len(manifest_columns)}"
            )
        if kind != "isolation_forest" and manifest.get("failure_horizon") != pipeline.config.failure_horizon:
            raise IncompatibleConfigurationError(
                f"failure-horizon mismatch for {dataset_id}/{kind}: manifest "
                f"{manifest.get('failure_horizon')}, pipeline {pipeline.config.failure_horizon}"
            )

    # ------------------------------------------------------------- readiness

    def readiness(self) -> dict[str, Any]:
        """JSON-friendly readiness report for GET /ready."""
        per_dataset: dict[str, dict[str, Any]] = {}
        all_ready = self._loaded
        for dataset_id in config.DATASET_IDS:
            models = {
                kind: ("loaded" if (dataset_id, kind) in self._models else "missing")
                for kind in MODEL_KINDS
            }
            default = DEFAULT_MODEL.get(dataset_id)
            dataset_ready = (
                dataset_id not in self._dataset_errors
                and dataset_id in self._pipelines
                and models.get(default) == "loaded"
            )
            per_dataset[dataset_id] = {
                "ready": dataset_ready,
                "default_model": default,
                "models": models,
                "error": self._dataset_errors.get(dataset_id),
            }
            all_ready = all_ready and dataset_ready
        return {"ready": bool(all_ready and self._loaded), "datasets": per_dataset}

    # ------------------------------------------------------------- prediction

    def predict(
        self,
        dataset_id: str,
        model_name: str | None,
        reading: Any,
    ) -> dict[str, Any]:
        """Score one engine-cycle reading.

        Returns a plain dict conforming to :class:`PredictionResponse`; the
        route layer validates it through Pydantic.
        """
        if not self._loaded:
            self.load()
        if dataset_id not in config.DATASET_IDS:
            raise ModelNotFoundError(
                f"unknown dataset id {dataset_id!r}; expected one of {list(config.DATASET_IDS)}"
            )
        kind = model_name or DEFAULT_MODEL.get(dataset_id)
        if kind not in MODEL_KINDS:
            raise ModelNotFoundError(f"unknown model kind {kind!r}; expected one of {list(MODEL_KINDS)}")

        key = (dataset_id, kind)
        model = self._models.get(key)
        if model is None:
            hint = f" (default for {dataset_id} is {DEFAULT_MODEL.get(dataset_id)})" if model_name is None else ""
            raise ModelNotFoundError(f"model {kind!r} is not available for {dataset_id}{hint}")

        manifest = self._manifests[key]
        pipeline = self._pipelines[dataset_id]
        frame = _reading_to_frame(reading)
        transformed = pipeline.transform(frame)  # pure transform: frozen statistics, no fit
        matrix = _feature_matrix(transformed, model)

        train_sha = (manifest.get("dataset_version") or {}).get("train_sha256") or ""
        model_version = f"{dataset_id}:{kind}@{train_sha[:12]}" if train_sha else f"{dataset_id}:{kind}"
        base: dict[str, Any] = {
            "dataset_id": dataset_id,
            "model": kind,
            "model_version": model_version,
            "predicted_at": _utc_now(),
            "anomaly_score": None,
            "anomaly_status": None,
            "failure_probability": None,
            "failure_status": None,
        }

        if kind == "isolation_forest":
            scores = model.score(transformed)
            labels = model.predict(transformed)
            base["anomaly_score"] = float(scores[0])
            base["anomaly_status"] = bool(int(labels[0]) == 1)
        else:
            probabilities = model.predict_proba(transformed)
            failure_probability = float(probabilities[0, 1])
            base["failure_probability"] = failure_probability
            base["failure_status"] = bool(failure_probability >= 0.5)
        return base


# ------------------------------------------------------------- helpers


def _reading_to_frame(reading: Any) -> pd.DataFrame:
    """Convert one validated reading into the single-row frame the pipeline expects."""
    data = reading.model_dump() if hasattr(reading, "model_dump") else dict(reading)
    unit = int(data.pop("unit"))
    cycle = int(data.pop("cycle"))
    row = {"unit": unit, "cycle": cycle}
    row.update({name: float(value) for name, value in data.items()})
    return pd.DataFrame([row], columns=READING_COLUMNS)


def _feature_matrix(frame: pd.DataFrame, model: Any) -> Any:
    missing = [column for column in model.feature_columns if column not in frame.columns]
    if missing:
        raise IncompatibleConfigurationError(
            f"transformed frame is missing model features: {missing}"
        )
    return frame[list(model.feature_columns)].to_numpy(dtype=float)
