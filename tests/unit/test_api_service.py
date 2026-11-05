"""End-to-end service tests for Phase 3.2.

All tests are synthetic: a tiny engine frame is run through the real
Phase 2.1 preprocessing pipeline, an Isolation Forest and a Random Forest are
fitted on it, the artefacts (+ manifests) are written to a temporary model
directory, and the :class:`~predictive_maintenance.api.service.ModelService`
serves predictions from them. No real C-MAPSS data is required.
"""

from __future__ import annotations

import pandas as pd
import pytest

from predictive_maintenance.api.schemas import EngineReading, PredictionResponse, PredictRequest
from predictive_maintenance.api.service import (
    IncompatibleConfigurationError,
    ModelNotFoundError,
    ModelService,
)
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS
from predictive_maintenance.models import datasets
from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier

DATASET_ID = "FD001"
HORIZON = 30


def _synthetic_frame(n_cycles: int = 40) -> pd.DataFrame:
    """One synthetic engine trajectory with varying sensors and settings."""
    rows = []
    for cycle in range(1, n_cycles + 1):
        row = {"unit": 1, "cycle": cycle}
        row.update({"setting_1": 10.0, "setting_2": 0.25, "setting_3": 100.0})
        row.update({f"s{i}": cycle * 0.05 * i + 0.5 * i for i in range(1, 22)})
        rows.append(row)
    return pd.DataFrame(rows)


def _fit_pipeline_and_models(tmp_path: Any) -> None:
    """Fit pipeline + IF + RF on synthetic data, write artefacts + manifests."""
    import joblib

    frame = _synthetic_frame()
    pipeline = datasets.PreprocessingPipeline().fit(frame)
    engineered = pipeline.transform(frame)
    feature_columns = list(pipeline.feature_columns)

    detector = IsolationForestDetector(
        AnomalyConfig(n_estimators=20, contamination=0.25, healthy_rul_min=0, random_state=3),
        feature_columns=feature_columns,
    ).fit(engineered)

    classifier = ForestFailureClassifier(
        ForestConfig(n_estimators=10, min_samples_leaf=1, random_state=3),
        horizon=HORIZON,
        feature_columns=feature_columns,
    ).fit(engineered)

    model_dir = tmp_path / DATASET_ID
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_dir / "preprocessing_pipeline.joblib")
    joblib.dump(detector, model_dir / "isolation_forest.joblib")
    joblib.dump(classifier, model_dir / "random_forest.joblib")

    import json

    base_manifest = {
        "dataset_id": DATASET_ID,
        "split_seed": 42,
        "failure_horizon": HORIZON,
        "feature_columns": feature_columns,
        "dataset_version": {"train_sha256": "synthetic-checksum-1234"},
    }
    for name, model in (("isolation_forest", detector), ("random_forest", classifier)):
        manifest = dict(base_manifest)
        manifest["model_type"] = name
        manifest["config"] = model.config.__dict__ if hasattr(model.config, "__dict__") else {}
        manifest["n_train_rows"] = int(len(frame))
        (model_dir / f"{name}.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )


def _reading(cycle: int = 40, unit: int = 1) -> EngineReading:
    values = {
        "unit": unit,
        "cycle": cycle,
        "setting_1": 10.0,
        "setting_2": 0.25,
        "setting_3": 100.0,
    }
    values.update({f"s{i}": float(i) for i in range(1, 22)})
    return EngineReading(**values)


class TestModelServiceSynthetic:
    def test_load_and_predict_isolation_forest(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        assert service.is_loaded
        report = service.readiness()
        # the synthetic catalogue only serves FD00X; FD001-FD004 have no
        # artefacts, so overall readiness is False while FD00X itself is ready
        assert report["ready"] is False
        assert report["datasets"][DATASET_ID]["ready"] is True
        assert report["datasets"][DATASET_ID]["models"]["isolation_forest"] == "loaded"

        payload = service.predict(DATASET_ID, "isolation_forest", _reading())
        assert payload["dataset_id"] == DATASET_ID
        assert payload["model"] == "isolation_forest"
        assert payload["model_version"].startswith(f"{DATASET_ID}:isolation_forest@")
        assert isinstance(payload["anomaly_score"], float)
        assert isinstance(payload["anomaly_status"], bool)
        assert payload["failure_probability"] is None
        assert payload["failure_status"] is None
        assert payload["predicted_at"].tzinfo is not None
    def test_load_and_predict_random_forest(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        payload = service.predict(DATASET_ID, None, _reading(cycle=39))  # None -> default model
        assert payload["model"] == "random_forest"
        assert 0.0 <= payload["failure_probability"] <= 1.0
        assert isinstance(payload["failure_status"], bool)
        assert payload["anomaly_score"] is None
        assert payload["anomaly_status"] is None

    def test_default_model_resolution(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        explicit = service.predict(DATASET_ID, "random_forest", _reading())
        implicit = service.predict(DATASET_ID, None, _reading())
        assert explicit["model"] == implicit["model"] == "random_forest"
        assert explicit["failure_probability"] == implicit["failure_probability"]

    def test_unknown_dataset(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        with pytest.raises(ModelNotFoundError, match="unknown dataset"):
            service.predict("FD009", None, _reading())

    def test_unknown_model_kind(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        with pytest.raises(ModelNotFoundError, match="unknown model kind"):
            service.predict("FD001", "logistic_regression", _reading())

    def test_missing_model_artefact(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()  # xgboost artefact was never written
        with pytest.raises(ModelNotFoundError, match="not available"):
            service.predict("FD001", "xgboost", _reading())

    def test_incompatible_manifest_rejected(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        import json

        manifest_path = tmp_path / DATASET_ID / "random_forest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["feature_columns"] = ["nonexistent_feature"]
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )

        service = ModelService(model_dir=tmp_path)
        service.load()
        report = service.readiness()
        assert report["datasets"]["FD001"]["ready"] is False
        assert "feature contract mismatch" in report["datasets"]["FD001"]["error"]

    def test_no_refit_during_inference(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        pipeline_before = service._pipelines[DATASET_ID]
        first = service.predict(DATASET_ID, "isolation_forest", _reading(cycle=10))
        second = service.predict(DATASET_ID, "isolation_forest", _reading(cycle=20))
        # pipeline object is reused (transform only), predictions are deterministic per reading
        assert service._pipelines[DATASET_ID] is pipeline_before
        assert isinstance(first["anomaly_score"], float)
        assert isinstance(second["anomaly_score"], float)
        assert first["predicted_at"] != second["predicted_at"]

    def test_pydantic_response_conforms(self, tmp_path: Any) -> None:
        _fit_pipeline_and_models(tmp_path)
        service = ModelService(model_dir=tmp_path)
        service.load()
        payload = service.predict(DATASET_ID, "random_forest", _reading())
        response = PredictionResponse(**payload)
        assert response.dataset_id == DATASET_ID
        assert 0.0 <= response.failure_probability <= 1.0  # type: ignore[operator]
        assert response.predicted_at.tzinfo is not None


class TestEngineReadingSchema:
    def test_all_required_fields(self) -> None:
        reading = _reading()
        data = reading.model_dump()
        assert {"unit", "cycle", *OP_SETTING_COLUMNS, *[f"s{i}" for i in range(1, 22)]} <= set(data)

    def test_request_schema_validates(self) -> None:
        request = PredictRequest(dataset_id="FD001", reading=_reading())
        assert request.dataset_id == "FD001"
        assert request.model is None

    def test_dataset_id_pattern_rejected(self) -> None:
        with pytest.raises(ValueError):
            PredictRequest(dataset_id="FD009", reading=_reading())
