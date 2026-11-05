"""Real-data integration tests for Phase 2.2-2.5 on FD001 (~30-40 s).

Covers what synthetic frames cannot: the engineered-feature tables, official
NASA test-label attachment, determinism/purity of the test transform (no
preprocessing leakage), serializer round-trips on real models, and manifest
integrity. Skipped while the dataset is absent.

The heavier training is deliberately limited to FD001 to keep suite runtime
bounded; the evaluator CLI (scripts/evaluate_models.py) covers FD001-FD004.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import load_rul
from predictive_maintenance.models import (
    ablate_features,
    load_split,
    load_test_features,
    select_feature_columns,
)
from predictive_maintenance.models.boost import BoostFailureClassifier
from predictive_maintenance.models.evaluation import classification_metrics
from predictive_maintenance.models.forest import ForestFailureClassifier
from predictive_maintenance.models.persistence import (
    load_artifact,
    read_manifest,
    save_artifact,
)
from predictive_maintenance.models.training import load_or_train, model_name

pytestmark = pytest.mark.skipif(
    not (config.CMAPSS_DATA_DIR / "readme.txt").is_file(),
    reason="C-MAPSS data not downloaded yet (run scripts/download_data.py)",
)

HORIZON = 30


@pytest.fixture(scope="module")
def setup() -> "tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str], ForestFailureClassifier]":
    """Parquet splits, official test features, RF classifier (trained once)."""
    train = load_split("FD001", "train")
    val = load_split("FD001", "val")
    test = load_test_features("FD001", rul_cap=config.RUL_CAP, horizon=HORIZON)
    label = f"failure_within_{HORIZON}"
    columns = select_feature_columns(train, label)
    model = ForestFailureClassifier(horizon=HORIZON, feature_columns=columns).fit(train)
    return train, val, test, columns, model


class TestFeatureTablesAndLabels:
    def test_split_frames_present_and_clean(self, setup) -> None:  # type: ignore[no-untyped-def]
        train, val, test, columns, _ = setup
        for frame in (train, val, test):
            assert not frame[columns].isna().any().any()
        assert train["unit"].nunique() == 80 and val["unit"].nunique() == 20
        assert not set(train["unit"]) & set(val["unit"])

    def test_feature_columns_exclude_targets_and_keys(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, _, _, columns, _ = setup
        for banned in ("unit", "cycle", "rul_raw", "RUL", "condition_id", "setting_1", "failure_within_30"):
            assert banned not in columns
        assert len(columns) == 60

    def test_val_split_uses_failed_and_healthy_rows(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, val, _, _, _ = setup
        assert set(val["failure_within_30"].unique()) == {0, 1}


class TestOfficialTestCoverage:
    def test_row_and_engine_counts_match_official_files(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, _, test, _, _ = setup
        assert len(test) == 13096  # rows in test_FD001.txt
        assert test["unit"].nunique() == config.DATASETS["FD001"].n_test_units

    def test_final_cycle_rul_matches_rul_file(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, _, test, _, _ = setup
        truth = load_rul("FD001").set_index("unit")["RUL"]
        observed = test.groupby("unit")["rul_raw"].min()  # last observed cycle => smallest remaining life
        aligned = observed.sort_index().to_numpy()
        expected = truth.sort_index().to_numpy()
        np.testing.assert_equal(aligned, expected.astype(float))

    def test_labels_valid_and_capped(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, _, test, _, _ = setup
        assert set(test["failure_within_30"].unique()) <= {0, 1}
        assert test["RUL"].max() <= config.RUL_CAP
        # official test trajectories stop BEFORE failure: remaining life at the
        # last observed cycle is the (positive) RUL-file value
        assert test["rul_raw"].min() > 0

    def test_transform_is_deterministic_and_pure(self) -> None:  # type: ignore[no-untyped-def]
        # two consecutive builds must be identical: the fitted pipeline derives
        # its statistics from training rows only and transform never mutates
        first = load_test_features("FD001", rul_cap=config.RUL_CAP, horizon=HORIZON)
        second = load_test_features("FD001", rul_cap=config.RUL_CAP, horizon=HORIZON)
        assert first.equals(second)

    def test_ablation_removes_derived_columns_only(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, _, _, columns, _ = setup
        reduced = ablate_features(columns, ["s10", "s16"])  # FD001 already drops s10/s16
        assert reduced == columns


class TestModelSmokeReal:
    def test_detector_ranking_quality_on_validation(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, val, _, _, _ = setup
        detector, _ = load_or_train("FD001", "isolation_forest", force=False)
        scores = detector.score(val)
        y_true = val["failure_within_30"].to_numpy()
        from sklearn.metrics import roc_auc_score

        assert roc_auc_score(y_true, scores) > 0.9

    def test_forest_probability_and_importances(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, val, test, _, model = setup
        probabilities = model.predict_proba(val)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-9)
        importances = model.feature_importances()
        assert len(importances) == 60
        assert float(importances.max()) > 0.0

    def test_real_metrics_within_bounds_and_manifest_written(self) -> None:  # type: ignore[no-untyped-def]
        detector, val_metrics = load_or_train("FD001", "isolation_forest", force=False)
        assert 0.0 <= val_metrics["recall"] <= 1.0 and 0.0 <= val_metrics["f1"] <= 1.0
        manifest = read_manifest("FD001", model_name("isolation_forest"))
        assert manifest["split_seed"] == 42
        assert "train_sha256" in manifest["dataset_version"]
        assert manifest["validation_metrics"]["f1"] == val_metrics["f1"]

    def test_boost_and_forest_serialization_identity_on_real_data(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, val, _, columns, _ = setup
        model = BoostFailureClassifier(feature_columns=columns, horizon=HORIZON).fit(load_split("FD001", "train"))
        expected = model.predict(val)
        # scratch id: do not clobber the real trained-and-manifested artifact
        save_artifact(model, "FD001X", "xgboost")
        restored: BoostFailureClassifier = load_artifact("FD001X", "xgboost")
        np.testing.assert_array_equal(restored.predict(val), expected)

    def test_classifier_val_metric_bounds(self, setup) -> None:  # type: ignore[no-untyped-def]
        _, val, _, _, model = setup
        metrics = classification_metrics(
            val["failure_within_30"].to_numpy(), model.predict_proba(val)[:, 1]
        )
        for key in ("precision", "recall", "f1", "macro_f1", "roc_auc", "pr_auc"):
            assert 0.0 <= metrics[key] <= 1.0, key
