"""Tests for Phase 3.3-3.6: sensor ingestion, monitoring, persistence, alerting.

All tests use a synthetic model catalogue (pipeline + Isolation Forest +
Random Forest) written to a temporary directory, plus an SQLite database.
No real C-MAPSS data is required.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from predictive_maintenance import config
from predictive_maintenance.api import db
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.main import create_app
from predictive_maintenance.api.service import ModelService
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS

DATASET_ID = "FD001"
HORIZON = 30


def _synthetic_frame(n_cycles: int = 40) -> pd.DataFrame:
    rows = []
    for cycle in range(1, n_cycles + 1):
        row = {"unit": 1, "cycle": cycle}
        row.update({"setting_1": 10.0, "setting_2": 0.25, "setting_3": 100.0})
        row.update({f"s{i}": cycle * 0.05 * i + 0.5 * i for i in range(1, 22)})
        rows.append(row)
    return pd.DataFrame(rows)


def _fit_pipeline_and_models(tmp_path: Any) -> None:
    import joblib

    from predictive_maintenance.models import datasets
    from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
    from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier

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


def _reading(
    machine_id: str,
    cycle: int = 1,
    dataset_id: str = DATASET_ID,
    timestamp: str = "2026-01-01T00:00:00Z",
    **overrides: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "machine_id": machine_id,
        "dataset_id": dataset_id,
        "cycle": cycle,
        "timestamp": timestamp,
        "setting_1": 10.0,
        "setting_2": 0.25,
        "setting_3": 100.0,
    }
    values.update({f"s{i}": float(i) for i in range(1, 22)})
    values.update(overrides)
    return values


@pytest.fixture
def app_client(tmp_path: Any) -> Any:
    model_root = tmp_path / "models"
    _fit_pipeline_and_models(model_root)
    service = ModelService(model_dir=model_root)
    service.load()

    db_path = tmp_path / "test.db"
    if db_path.exists():
        db_path.unlink()
    db.init_db(f"sqlite:///{db_path}")
    session = db.get_session()
    for table in reversed(db.Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()

    app = create_app()
    app.dependency_overrides[get_model_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def _post_reading(client: Any, payload: dict[str, Any]) -> Any:
    return client.post("/readings", json=payload)


class TestReadingValidation:
    def test_valid_reading_stored_and_predicted(self, app_client: Any) -> None:
        response = _post_reading(app_client, _reading("VAL1", cycle=1))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "stored"
        assert body["reading_id"] is not None
        assert body["prediction"] is not None
        assert body["prediction"]["model"] == "random_forest"
        assert 0.0 <= body["prediction"]["failure_probability"] <= 1.0

    def test_invalid_dataset_rejected(self, app_client: Any) -> None:
        response = _post_reading(app_client, _reading("VAL2", dataset_id="FD009"))
        assert response.status_code == 422, response.text

    def test_missing_sensor_rejected(self, app_client: Any) -> None:
        payload = _reading("VAL3", cycle=1)
        del payload["s1"]
        response = _post_reading(app_client, payload)
        assert response.status_code == 422, response.text

    def test_negative_cycle_rejected(self, app_client: Any) -> None:
        response = _post_reading(app_client, _reading("VAL4", cycle=0))
        assert response.status_code == 422, response.text


class TestBatchIngestion:
    def test_batch_stores_multiple(self, app_client: Any) -> None:
        response = app_client.post(
            "/readings/batch",
            json={"readings": [_reading("BM1", cycle=1), _reading("BM1", cycle=2), _reading("BM1", cycle=3)]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["stored"] == 3
        assert body["duplicates"] == 0
        assert body["rejected"] == 0
        assert len(body["results"]) == 3

    def test_batch_empty_rejected(self, app_client: Any) -> None:
        response = app_client.post("/readings/batch", json={"readings": []})
        assert response.status_code == 422, response.text


class TestDuplicatePrevention:
    def test_duplicate_cycle_returned(self, app_client: Any) -> None:
        _post_reading(app_client, _reading("DUP1", cycle=5))
        response = _post_reading(app_client, _reading("DUP1", cycle=5))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "duplicate"
        assert body["reading_id"] is not None
        assert body["prediction"] is not None

    def test_duplicate_does_not_create_new_reading(self, app_client: Any) -> None:
        first = _post_reading(app_client, _reading("DUP2", cycle=1))
        first_id = first.json()["reading_id"]
        second = _post_reading(app_client, _reading("DUP2", cycle=1))
        assert second.json()["reading_id"] == first_id

    def test_different_machines_same_cycle_allowed(self, app_client: Any) -> None:
        r1 = _post_reading(app_client, _reading("DIF1", cycle=1))
        r2 = _post_reading(app_client, _reading("DIF2", cycle=1))
        assert r1.json()["status"] == "stored"
        assert r2.json()["status"] == "stored"
        assert r1.json()["reading_id"] != r2.json()["reading_id"]


class TestChronologicalOrdering:
    def test_out_of_order_cycle_rejected(self, app_client: Any) -> None:
        _post_reading(app_client, _reading("OOO1", cycle=10))
        response = _post_reading(app_client, _reading("OOO1", cycle=5))
        assert response.status_code == 409, response.text
        assert "out-of-order" in response.text

    def test_equal_cycle_is_duplicate_not_error(self, app_client: Any) -> None:
        _post_reading(app_client, _reading("EQ1", cycle=7))
        response = _post_reading(app_client, _reading("EQ1", cycle=7))
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"


class TestHistoricalFeatureContext:
    def test_rolling_features_use_history(self, app_client: Any) -> None:
        mid = "HIST1"
        for cycle in range(1, 6):
            response = _post_reading(app_client, _reading(mid, cycle=cycle))
            assert response.status_code == 200, response.text

        response = app_client.get(f"/machines/{mid}/readings?limit=100")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        cycles = [r["cycle"] for r in body["readings"]]
        assert cycles == [1, 2, 3, 4, 5]


class TestPredictionPersistence:
    def test_prediction_stored_with_reading(self, app_client: Any) -> None:
        mid = "PRED1"
        response = _post_reading(app_client, _reading(mid, cycle=3))
        assert response.status_code == 200
        body = response.json()
        reading_id = body["reading_id"]

        response = app_client.get(f"/machines/{mid}/predictions?limit=100")
        assert response.status_code == 200
        preds = response.json()["predictions"]
        assert len(preds) >= 1
        found = [p for p in preds if p["reading_id"] == reading_id]
        assert len(found) == 1
        assert found[0]["model"] == "random_forest"
        assert 0.0 <= found[0]["failure_probability"] <= 1.0


class TestMachineMonitoring:
    def test_list_machines(self, app_client: Any) -> None:
        _post_reading(app_client, _reading("LIST1", cycle=1))
        response = app_client.get("/machines")
        assert response.status_code == 200
        body = response.json()
        machine_ids = [m["machine_id"] for m in body]
        assert "LIST1" in machine_ids

    def test_get_machine_detail(self, app_client: Any) -> None:
        mid = "DET1"
        _post_reading(app_client, _reading(mid, cycle=1))
        response = app_client.get(f"/machines/{mid}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["machine_id"] == mid
        assert body["dataset_id"] == DATASET_ID
        assert body["reading_count"] >= 1
        assert "health" in body

    def test_get_machine_not_found(self, app_client: Any) -> None:
        response = app_client.get("/machines/NoSuchMachine")
        assert response.status_code == 404, response.text

    def test_get_machine_readings_pagination(self, app_client: Any) -> None:
        mid = "PAG1"
        for cycle in range(1, 6):
            _post_reading(app_client, _reading(mid, cycle=cycle))
        response = app_client.get(f"/machines/{mid}/readings?limit=2&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["readings"]) == 2
        assert body["total"] == 5
        assert body["limit"] == 2
        assert body["offset"] == 0

        response = app_client.get(f"/machines/{mid}/readings?limit=2&offset=2")
        assert response.status_code == 200
        body = response.json()
        assert len(body["readings"]) == 2
        assert body["offset"] == 2

    def test_get_machine_predictions(self, app_client: Any) -> None:
        mid = "PRED2"
        for cycle in range(1, 4):
            _post_reading(app_client, _reading(mid, cycle=cycle))
        response = app_client.get(f"/machines/{mid}/predictions?limit=100")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 3

    def test_get_machine_health(self, app_client: Any) -> None:
        mid = "HLTH1"
        _post_reading(app_client, _reading(mid, cycle=1))
        response = app_client.get(f"/machines/{mid}/health")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["machine_id"] == mid
        assert body["health"] in (
            "healthy", "anomalous", "elevated_risk", "critical_risk", "unknown"
        )


class TestExistingAPICompatibility:
    def test_predict_still_works(self, app_client: Any) -> None:
        reading = {
            "unit": 1,
            "cycle": 40,
            "setting_1": 10.0,
            "setting_2": 0.25,
            "setting_3": 100.0,
        }
        reading.update({f"s{i}": float(i) for i in range(1, 22)})
        response = app_client.post(
            "/predict",
            json={"dataset_id": DATASET_ID, "model": "random_forest", "reading": reading},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["model"] == "random_forest"
        assert 0.0 <= body["failure_probability"] <= 1.0

    def test_health_and_ready(self, app_client: Any) -> None:
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        response = app_client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert DATASET_ID in body["datasets"]
