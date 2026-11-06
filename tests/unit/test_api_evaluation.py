"""Tests for the Phase 5 evaluation report routes (GET /evaluation*).

The routes serve the Phase 2.5 static JSON reports read-only, so tests build
tiny synthetic reports in a temporary directory and monkeypatch the module's
report directory constant. No model artefacts are required.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def eval_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Temporary evaluation-reports directory wired into the routes module."""
    reports = tmp_path / "evaluation"
    reports.mkdir()
    from predictive_maintenance.api.routes import evaluation

    monkeypatch.setattr(evaluation, "EVALUATION_REPORTS_DIR", reports)
    return reports


@pytest.fixture
def client(eval_dir: Any) -> TestClient:
    from predictive_maintenance.api.routes import evaluation

    app = FastAPI()
    app.include_router(evaluation.router)
    with TestClient(app) as test_client:
        yield test_client


def _write_report(dir_: Any, dataset_id: str, models: Dict[str, Any]) -> None:
    payload = {
        "dataset_id": dataset_id,
        "label_config": {
            "failure_horizon": 30,
            "rul_cap": 130,
            "healthy_rul_min": 50,
            "classification_threshold": 0.5,
            "label_definition": "test",
        },
        "data": {"train_rows": 10, "train_engines": 2},
        "models": models,
    }
    (dir_ / f"eval_{dataset_id}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestEvaluationIndex:
    def test_lists_only_available_datasets(self, client: TestClient, eval_dir: Any) -> None:
        _write_report(
            eval_dir,
            "FD001",
            {
                "random_forest": {"validation": {"f1": 0.8, "roc_auc": 0.9}},
                "xgboost": {"validation": {"f1": 0.75, "roc_auc": 0.88}},
            },
        )
        response = client.get("/evaluation")
        assert response.status_code == 200
        body = response.json()
        assert body["datasets"] == ["FD001"]
        assert "FD002" not in body["datasets"]

    def test_best_model_is_highest_validation_f1(self, client: TestClient, eval_dir: Any) -> None:
        _write_report(
            eval_dir,
            "FD001",
            {
                "random_forest": {"validation": {"f1": 0.7}},
                "xgboost": {"validation": {"f1": 0.9, "pr_auc": 0.93}},
                "isolation_forest": {"validation": {"f1": 0.99}},  # never the default
            },
        )
        response = client.get("/evaluation")
        dataset = response.json()["by_dataset"]["FD001"]
        assert dataset["default_model"] == "xgboost"
        assert dataset["metrics"]["pr_auc"] == 0.93

    def test_empty_directory(self, client: TestClient) -> None:
        response = client.get("/evaluation")
        assert response.status_code == 200
        assert response.json() == {"datasets": [], "by_dataset": {}}

    def test_isolation_forest_fallback_without_supervised(self, client: TestClient, eval_dir: Any) -> None:
        _write_report(
            eval_dir,
            "FD002",
            {
                "isolation_forest": {"validation": {"f1": 0.6}},
                "random_forest": {"validation": {}},
            },
        )
        response = client.get("/evaluation")
        dataset = response.json()["by_dataset"]["FD002"]
        assert dataset["default_model"] == "isolation_forest"


class TestEvaluationReport:
    def test_full_report_served(self, client: TestClient, eval_dir: Any) -> None:
        models = {"random_forest": {"validation": {"f1": 0.8}, "test": {"f1": 0.6}}}
        _write_report(eval_dir, "FD004", models)
        response = client.get("/evaluation/FD004")
        assert response.status_code == 200
        assert response.json()["models"]["random_forest"]["test"]["f1"] == 0.6

    def test_missing_report_404(self, client: TestClient) -> None:
        response = client.get("/evaluation/FD003")
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "evaluation_report_missing"

    def test_unknown_dataset_404(self, client: TestClient) -> None:
        response = client.get("/evaluation/FD999")
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "unknown_dataset"
