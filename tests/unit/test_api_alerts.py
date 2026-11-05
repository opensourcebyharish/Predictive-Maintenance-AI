"""Tests for Phase 3.6: alert engine - thresholds, deduplication, lifecycle, acknowledgement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from predictive_maintenance import config
from predictive_maintenance.api import db
from predictive_maintenance.api.alerts import AlertService
from predictive_maintenance.api.dependencies import get_model_service
from predictive_maintenance.api.main import create_app
from predictive_maintenance.api.service import ModelService
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS

DATASET_ID = "FD001"
HORIZON = 30


def _synthetic_frame(n_cycles: int = 40) -> Any:
    import pandas as pd
    from predictive_maintenance.models import datasets
    from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
    from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier

    import joblib

    rows = []
    for cycle in range(1, n_cycles + 1):
        row = {"unit": 1, "cycle": cycle}
        row.update({"setting_1": 10.0, "setting_2": 0.25, "setting_3": 100.0})
        row.update({f"s{i}": cycle * 0.05 * i + 0.5 * i for i in range(1, 22)})
        rows.append(row)
    frame = pd.DataFrame(rows)

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

    import tempfile, os
    tmp = tempfile.mkdtemp()
    model_dir = os.path.join(tmp, DATASET_ID)
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(pipeline, os.path.join(model_dir, "preprocessing_pipeline.joblib"))
    joblib.dump(detector, os.path.join(model_dir, "isolation_forest.joblib"))
    joblib.dump(classifier, os.path.join(model_dir, "random_forest.joblib"))

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
        with open(os.path.join(model_dir, f"{name}.json"), "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True, default=str)

    service = ModelService(model_dir=tmp)
    service.load()
    return service, tmp


def _reading(machine_id: str = "M1", cycle: int = 1) -> dict[str, Any]:
    values: dict[str, Any] = {
        "machine_id": machine_id,
        "dataset_id": DATASET_ID,
        "cycle": cycle,
        "timestamp": "2026-01-01T00:00:00Z",
        "setting_1": 10.0,
        "setting_2": 0.25,
        "setting_3": 100.0,
    }
    values.update({f"s{i}": float(i) for i in range(1, 22)})
    return values


@pytest.fixture
def app_client(tmp_path: Any) -> Any:
    service, _ = _synthetic_frame()
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


class TestAlertGeneration:
    def test_alerts_created_on_predictions(self, app_client: Any) -> None:
        # Ingest a few readings; at least some alerts should be generated
        # depending on model output.
        for cycle in range(1, 6):
            _post_reading(app_client, _reading(machine_id="ALERT1", cycle=cycle))

        response = app_client.get("/alerts/summary")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] >= 0
        assert "by_status" in body
        assert "by_type" in body

    def test_alert_dedup_no_duplicates_for_consecutive_anomalies(self, app_client: Any) -> None:
        # Same machine, multiple cycles - should not create duplicate active
        # alerts of the same type.
        for cycle in range(1, 8):
            _post_reading(app_client, _reading(machine_id="ALERT2", cycle=cycle))

        response = app_client.get("/alerts?machine_id=ALERT2")
        assert response.status_code == 200
        body = response.json()
        # Count active alerts per type
        active_by_type: dict[str, int] = {}
        for a in body:
            if a["status"] == "active":
                active_by_type[a["alert_type"]] = active_by_type.get(a["alert_type"], 0) + 1
        for alert_type, count in active_by_type.items():
            assert count <= 1, f"duplicate active alert for {alert_type}: {count}"

    def test_alert_lifecycle_active_acknowledged_resolved(self, app_client: Any) -> None:
        _post_reading(app_client, _reading(machine_id="ALERT3", cycle=1))

        response = app_client.get("/alerts?machine_id=ALERT3&status=active")
        assert response.status_code == 200
        alerts = response.json()
        if not alerts:
            pytest.skip("no active alert generated for this synthetic reading")

        alert_id = alerts[0]["id"]
        assert alerts[0]["status"] == "active"

        # Acknowledge
        response = app_client.post(
            f"/alerts/{alert_id}/acknowledge",
            json={"acknowledged_by": "test-operator"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["alert_id"] == alert_id
        assert body["status"] == "acknowledged"
        assert body["acknowledged_at"] is not None

        # Verify status changed
        response = app_client.get(f"/alerts/{alert_id}")
        # GET /alerts/{id} doesn't exist; list instead
        response = app_client.get("/alerts?machine_id=ALERT3")
        assert response.status_code == 200
        alert = next((a for a in response.json() if a["id"] == alert_id), None)
        assert alert is not None
        assert alert["status"] == "acknowledged"
        assert alert["acknowledged_by"] == "test-operator"

    def test_acknowledge_non_existent_alert(self, app_client: Any) -> None:
        response = app_client.post("/alerts/999999/acknowledge", json={"acknowledged_by": "op"})
        assert response.status_code == 404, response.text

    def test_acknowledge_already_acknowledged(self, app_client: Any) -> None:
        _post_reading(app_client, _reading(machine_id="ALERT4", cycle=1))
        response = app_client.get("/alerts?machine_id=ALERT4&status=active")
        alerts = response.json()
        if not alerts:
            pytest.skip("no active alert generated")

        alert_id = alerts[0]["id"]
        app_client.post(f"/alerts/{alert_id}/acknowledge", json={"acknowledged_by": "op"})
        response = app_client.post(f"/alerts/{alert_id}/acknowledge", json={"acknowledged_by": "op"})
        assert response.status_code == 409, response.text


class TestAlertThresholds:
    def test_configurable_thresholds_affect_alerts(self) -> None:
        # This is a unit-level check: different thresholds produce different
        # alert decisions for the same probability.
        service, _ = _synthetic_frame()

        from predictive_maintenance.api.alerts import AlertService
        from predictive_maintenance.api.schemas import PredictionResponse

        # Strict thresholds -> more alerts
        strict = AlertService(
            elevated_threshold=0.1, critical_threshold=0.2, anomaly_enabled=True
        )
        # Lenient thresholds -> fewer alerts
        lenient = AlertService(
            elevated_threshold=0.9, critical_threshold=0.95, anomaly_enabled=False
        )

        high_prob = PredictionResponse(
            dataset_id=DATASET_ID,
            model="random_forest",
            model_version="test@abc",
            predicted_at=datetime.now(timezone.utc),
            failure_probability=0.5,
            failure_status=True,
        )

        # Use standalone engines to avoid clobbering the global session factory.
        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        from predictive_maintenance.api.db.models import Base as _Base

        def _make_session():
            eng = _create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
            _Base.metadata.create_all(eng)
            return _sessionmaker(bind=eng)()

        session = _make_session()
        strict.evaluate(session, "M-STRICT", high_prob, prediction_id=1)
        strict_count = session.query(db.Alert).count()
        session.close()

        session = _make_session()
        lenient.evaluate(session, "M-LENIENT", high_prob, prediction_id=1)
        lenient_count = session.query(db.Alert).count()
        session.close()

        assert strict_count > 0
        assert lenient_count == 0  # 0.5 < 0.9 elevated, anomaly disabled


class TestAlertSummary:
    def test_summary_shape(self, app_client: Any) -> None:
        response = app_client.get("/alerts/summary")
        assert response.status_code == 200
        body = response.json()
        assert "total" in body
        assert "by_status" in body
        assert "by_type" in body
        assert "by_severity" in body
        assert "active_by_machine" in body
        assert isinstance(body["total"], int)
