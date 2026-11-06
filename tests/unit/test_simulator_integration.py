"""Integration tests for Phase 4 IoT simulator against the real FastAPI backend.

Uses TestClient to send simulated readings through the full ingestion pipeline
and verifies they are stored with is_simulated=true, predictions are generated,
and alerts fire correctly.
"""

from __future__ import annotations

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
from predictive_maintenance.simulator.config import SimulatorConfig
from predictive_maintenance.simulator.machine import create_machines
from predictive_maintenance.simulator.simulator import SimulatorOrchestrator

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
    from predictive_maintenance.models.anomalies import (
        AnomalyConfig,
        IsolationForestDetector,
    )
    from predictive_maintenance.models.forest import (
        ForestConfig,
        ForestFailureClassifier,
    )

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


def _reading(machine_id: str, cycle: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "machine_id": machine_id,
        "dataset_id": DATASET_ID,
        "cycle": cycle,
        "timestamp": "2026-01-01T00:00:00Z",
        "setting_1": 10.0,
        "setting_2": 0.25,
        "setting_3": 100.0,
        "is_simulated": True,
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


class TestIngestionIntegration:
    def test_single_reading_stored_with_is_simulated(self, app_client: Any) -> None:
        response = app_client.post("/readings", json=_reading("INT1", cycle=1))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "stored"
        assert body["reading_id"] is not None
        assert body["prediction"] is not None
        assert body["prediction"]["model"] == "random_forest"

    def test_is_simulated_stored_in_database(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("INT2", cycle=1))
        # Query readings via machine endpoint
        response = app_client.get("/machines/INT2/readings?limit=100")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["readings"][0]["is_simulated"] is True

    def test_batch_ingestion(self, app_client: Any) -> None:
        response = app_client.post(
            "/readings/batch",
            json={
                "readings": [
                    _reading("INT3", cycle=1),
                    _reading("INT3", cycle=2),
                    _reading("INT3", cycle=3),
                ]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["stored"] == 3
        assert body["duplicates"] == 0
        assert body["rejected"] == 0

    def test_duplicate_prevention(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("INT4", cycle=5))
        response = app_client.post("/readings", json=_reading("INT4", cycle=5))
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"

    def test_out_of_order_rejected(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("INT5", cycle=10))
        response = app_client.post("/readings", json=_reading("INT5", cycle=5))
        assert response.status_code == 409, response.text


class TestSimulatorOrchestratorIntegration:
    def test_orchestrator_submits_readings(self, app_client: Any) -> None:
        cfg = SimulatorConfig(
            api_url="http://testserver",  # not used directly by TestClient
            machine_count=2,
            interval_seconds=0.0,
            duration_seconds=0.0,
            seed=42,
            scenario="normal",
            batch_size=10,
            dataset_id=DATASET_ID,
        )
        orch = SimulatorOrchestrator(config=cfg)

        # Manually submit a batch using the client
        batch = [m.next_reading() for m in orch.machines]
        # Convert to dicts for TestClient (mode='json' serializes datetimes)
        payload = {"readings": [r.model_dump(mode="json") for r in batch]}
        response = app_client.post("/readings/batch", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["stored"] == 2

    def test_scenario_change(self, app_client: Any) -> None:
        orch = SimulatorOrchestrator()
        assert orch.config.scenario == "normal"
        orch.set_scenario("abnormal_vibration")
        assert orch.config.scenario == "abnormal_vibration"
        for m in orch.machines:
            assert m.scenario == "abnormal_vibration"


class TestAlertsFromSimulation:
    def test_anomaly_alert_generated(self, app_client: Any) -> None:
        # Submit readings with extreme values to trigger failure risk alerts
        for cycle in range(1, 6):
            app_client.post(
                "/readings",
                json=_reading("ALERTINT", cycle=cycle, s8=50000.0, s9=50000.0),
            )

        response = app_client.get("/alerts/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        # Extreme vibration values drive failure probability high, triggering
        # critical_failure_risk (anomaly_detected would require lower failure prob)
        assert "critical_failure_risk" in body.get("by_type", {})


class TestMachineMonitoringIntegration:
    def test_machine_list_contains_simulated_machine(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("MON1", cycle=1))
        response = app_client.get("/machines")
        assert response.status_code == 200
        body = response.json()
        machine_ids = [m["machine_id"] for m in body]
        assert "MON1" in machine_ids

    def test_machine_detail_includes_simulated_reading(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("MON2", cycle=1))
        response = app_client.get("/machines/MON2")
        assert response.status_code == 200
        body = response.json()
        assert body["machine_id"] == "MON2"
        assert body["reading_count"] >= 1
        assert body["latest_sensor_values"] is not None

    def test_machine_health(self, app_client: Any) -> None:
        app_client.post("/readings", json=_reading("MON3", cycle=1))
        response = app_client.get("/machines/MON3/health")
        assert response.status_code == 200
        body = response.json()
        assert body["machine_id"] == "MON3"
        assert body["health"] in (
            "healthy", "anomalous", "elevated_risk", "critical_risk", "unknown"
        )

    def test_predictions_stored_for_simulated_readings(self, app_client: Any) -> None:
        response = app_client.post("/readings", json=_reading("MON4", cycle=3))
        assert response.status_code == 200
        reading_id = response.json()["reading_id"]

        response = app_client.get("/machines/MON4/predictions?limit=100")
        assert response.status_code == 200
        preds = response.json()["predictions"]
        found = [p for p in preds if p["reading_id"] == reading_id]
        assert len(found) == 1
        assert found[0]["machine_id"] == "MON4"
