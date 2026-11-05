"""API route tests for Phase 3 (FastAPI backend).

Tests use a synthetic model catalogue in a temporary directory (no real
C-MAPSS data required). A real-data smoke test against the trained FD001
artefacts is included but skipped when the dataset is absent.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from predictive_maintenance import config
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.main import create_app
from predictive_maintenance.api.service import ModelService
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS

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
    from predictive_maintenance.models import datasets
    from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
    from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier

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


def _reading(cycle: int = 40, unit: int = 1) -> dict[str, Any]:
    values: dict[str, Any] = {
        "unit": unit,
        "cycle": cycle,
        "setting_1": 4.0,
        "setting_2": 0.2,
        "setting_3": 140.0,
    }
    values.update({f"s{i}": float(i) for i in range(1, 22)})
    return values


@pytest.fixture(scope="module")
def client(tmp_path_factory: Any) -> Any:
    model_root = tmp_path_factory.mktemp("models")
    _fit_pipeline_and_models(model_root)
    service = ModelService(model_dir=model_root)
    service.load()
    app = create_app()
    app.dependency_overrides[get_model_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


class TestHealth:
    def test_health_ok(self, client: Any) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["app"] == "predictive-maintenance-ai"
        assert "version" in body
        assert "service_loaded" in body

    def test_ready_ok(self, client: Any) -> None:
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        # synthetic catalogue serves only FD00X, so top-level readiness is
        # False while FD00X itself reports ready
        assert body["ready"] is False
        assert DATASET_ID in body["datasets"]
        assert body["datasets"][DATASET_ID]["ready"] is True
        assert body["datasets"][DATASET_ID]["models"]["random_forest"] == "loaded"
        assert body["datasets"][DATASET_ID]["error"] is None

    def test_docs_available(self, client: Any) -> None:
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_openapi_available(self, client: Any) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/predict" in schema["paths"]
        assert "/health" in schema["paths"]
        assert "/ready" in schema["paths"]


class TestPredict:
    def _post(self, client: Any, payload: Any) -> Any:
        return client.post("/predict", json=payload)

    def test_predict_isolation_forest(self, client: Any) -> None:
        response = self._post(
            client,
            {
                "dataset_id": DATASET_ID,
                "model": "isolation_forest",
                "reading": _reading(cycle=20),
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dataset_id"] == DATASET_ID
        assert body["model"] == "isolation_forest"
        assert body["model_version"] == f"{DATASET_ID}:isolation_forest@synthetic-ch"
        assert "predicted_at" in body
        assert isinstance(body["anomaly_score"], float)
        assert isinstance(body["anomaly_status"], bool)
        assert body["failure_probability"] is None
        assert body["failure_status"] is None

    def test_predict_random_forest_default_model(self, client: Any) -> None:
        response = self._post(
            client,
            {"dataset_id": DATASET_ID, "reading": _reading(cycle=39)},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["model"] == "random_forest"  # default for FD00X
        assert 0.0 <= body["failure_probability"] <= 1.0
        assert isinstance(body["failure_status"], bool)
        assert body["anomaly_score"] is None
        assert body["anomaly_status"] is None

    def test_predict_invalid_dataset(self, client: Any) -> None:
        response = self._post(
            client,
            {
                "dataset_id": "FD009",
                "reading": _reading(),
            },
        )
        assert response.status_code == 422, response.text  # request-shape validation

    def test_predict_missing_model(self, client: Any) -> None:
        response = self._post(
            client,
            {
                "dataset_id": DATASET_ID,
                "model": "xgboost",
                "reading": _reading(),
            },
        )
        assert response.status_code == 404, response.text
        assert response.json()["detail"]["error"] == "model_not_found"

    def test_predict_invalid_body(self, client: Any) -> None:
        response = client.post(
            "/predict",
            json={"dataset_id": DATASET_ID, "reading": {"unit": 1}},  # missing cycle, settings, sensors
        )
        assert response.status_code == 422, response.text


class TestRealDataSmoke:
    @pytest.mark.skipif(
        not (config.CMAPSS_DATA_DIR / "readme.txt").is_file(),
        reason="C-MAPSS data not downloaded yet",
    )
    def test_real_fd001_prediction(self) -> None:
        """End-to-end prediction on the real trained FD001 artefacts."""
        service = ModelService(model_dir=config.MODELS_DIR)
        service.load()
        readiness = service.readiness()
        assert readiness["ready"] is True, readiness["datasets"]

        from predictive_maintenance.data.cmapss import load_cmapss

        raw = load_cmapss("FD001", "train")
        row = raw.iloc[0]
        reading = _reading(cycle=int(row["cycle"]), unit=int(row["unit"]))
        for name in OP_SETTING_COLUMNS + SENSOR_COLUMNS:
            reading[name] = float(row[name])

        payload = service.predict("FD001", "random_forest", reading)
        assert payload["model"] == "random_forest"
        assert 0.0 <= payload["failure_probability"] <= 1.0
        assert isinstance(payload["failure_status"], bool)
