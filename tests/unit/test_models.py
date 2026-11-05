"""Unit tests for Phase 2.2-2.5 (synthetic frames only, no real dataset).

Tight helper frames mimic the engineered parquet schema (keys + settings +
``rul_raw``/``RUL``/``failure_within_<h>`` + a handful of sensor features) so
every model/eval layer is exercised without touching the real files. Real-data
integration checks live in ``test_models_real.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from predictive_maintenance.models import AnomalyConfig, IsolationForestDetector
from predictive_maintenance.models.boost import BoostConfig, BoostFailureClassifier
from predictive_maintenance.models.datasets import (
    ablate_features,
    attach_truth_from_rul_file,
    select_feature_columns,
)
from predictive_maintenance.models.evaluation import (
    anomaly_metrics,
    classification_metrics,
    detection_lead_time,
    healthy_false_positive_rate,
    score_quantiles,
    _jsonifiable,
)
from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier
from predictive_maintenance.models.persistence import (
    load_artifact,
    read_manifest,
    save_artifact,
    write_manifest,
    environment_versions,
)
from predictive_maintenance.models.training import model_name, ablation_applies

HORIZON = 3
FEATURE_COLUMNS = ["s3_lvl", "s3_rm5", "s3_rs5", "s3_sl5", "s10_lvl", "s16_lvl"]


def model_frame(
    lifespans: tuple[int, ...] = (14, 12),
    horizon: int = HORIZON,
    degradation_gap: float = 1.0,
) -> pd.DataFrame:
    """Engineered-schema miniature: degradation grows as remaining life falls.

    ``s3_*`` features separate healthy from degraded rows by ``degradation_gap``
    (healthy = remaining-life >= 5), which makes anomaly detectors learnable on
    tiny data; ``s10_lvl``/``s16_lvl`` exist so ablation tests have targets.
    """
    rows = []
    for unit, lifespan in enumerate(lifespans, start=1):
        for cycle in range(1, lifespan + 1):
            rul = lifespan - cycle
            level = 0.9 - rul / 20.0 + (degradation_gap if rul <= 4 else 0.0)
            rows.append(
                {
                    "unit": unit,
                    "cycle": cycle,
                    "condition_id": 0,
                    "setting_1": 10.0,
                    "setting_2": 0.25,
                    "setting_3": 100.0,
                    "rul_raw": float(rul),
                    "RUL": float(rul),
                    f"failure_within_{horizon}": int(rul <= horizon),
                    "s3_lvl": level,
                    "s3_rm5": level * 0.9,
                    "s3_rs5": 0.05 if rul <= 4 else 0.01,
                    "s3_sl5": -0.02 if rul <= 4 else 0.02,
                    "s10_lvl": float(cycle) * 0.01,
                    "s16_lvl": 0.0,
                }
            )
    return pd.DataFrame(rows)


def detector_config(**overrides) -> AnomalyConfig:
    defaults = dict(n_estimators=60, contamination=0.15, healthy_rul_min=5, random_state=7)
    return AnomalyConfig(**{**defaults, **overrides})


def forest_config(**overrides) -> ForestConfig:
    defaults = dict(n_estimators=40, min_samples_leaf=1, random_state=7)
    return ForestConfig(**{**defaults, **overrides})


def boost_config(**overrides) -> BoostConfig:
    defaults = dict(n_estimators=30, learning_rate=0.3, early_stopping_rounds=5, random_state=7)
    return BoostConfig(**{**defaults, **overrides})


# ------------------------------------------------------- feature plumbing


class TestFeaturePlumbing:
    def test_feature_selection_excludes_keys_targets_settings(self) -> None:
        frame = model_frame()
        columns = select_feature_columns(frame, f"failure_within_{HORIZON}")
        assert columns == FEATURE_COLUMNS  # deterministic order, no unit/cycle/settings/rul leakage

    def test_ablation_keeps_prefix_safety(self) -> None:
        assert ablate_features(["s1_lvl", "s10_lvl", "s16_rm5"], ["s10", "s16"]) == ["s1_lvl"]
        assert ablate_features(["s10_lvl"], ["s1"]) == ["s10_lvl"]  # s1 must not kill s10

    def test_truth_attachment_reconstructs_remaining_life(self) -> None:
        truncated = pd.DataFrame({"unit": [1, 1, 1], "cycle": [1, 2, 3], "rul_raw": [0, 0, 0]})
        truth = pd.DataFrame({"unit": [1], "RUL": [5]})
        out = attach_truth_from_rul_file(truncated, truth, rul_cap=None, horizon=5)
        assert out["rul_raw"].tolist() == [7, 6, 5]
        assert out["failure_within_5"].tolist() == [0, 0, 1]  # inclusive boundary
        capped = attach_truth_from_rul_file(truncated.assign(unit=[1, 1, 1]), truth.assign(RUL=[200]), rul_cap=130, horizon=30)
        assert capped["rul_raw"].tolist() == [202, 201, 200]
        assert capped["RUL"].tolist() == [130, 130, 130]  # cap applied like training targets


# -------------------------------------------------------- anomaly detector


class TestIsolationForestDetector:
    def test_fitted_only_on_healthy_rows(self) -> None:
        frame = model_frame()
        detector = IsolationForestDetector(detector_config(), feature_columns=FEATURE_COLUMNS).fit(frame)
        assert detector.n_healthy_ == int((frame["rul_raw"] >= 5).sum())
        scores = detector.score(frame)
        healthy = frame["rul_raw"] >= 5
        assert scores[healthy.to_numpy()].mean() < scores[~healthy.to_numpy()].mean()

    def test_no_healthy_rows_rejected(self) -> None:
        frame = model_frame((14,))
        with pytest.raises(ValueError, match="no healthy rows"):
            IsolationForestDetector(detector_config(healthy_rul_min=50), FEATURE_COLUMNS).fit(frame)

    def test_predictions_are_binary_and_reproducible(self) -> None:
        frame = model_frame((14, 12, 10))
        first = IsolationForestDetector(detector_config(), FEATURE_COLUMNS).fit(frame)
        second = IsolationForestDetector(detector_config(), FEATURE_COLUMNS).fit(frame)
        predictions = first.predict(frame)
        assert set(np.unique(predictions)) <= {0, 1}
        np.testing.assert_array_equal(predictions, second.predict(frame))
        np.testing.assert_allclose(first.score(frame), second.score(frame))

    def test_contamination_controls_detection_share(self) -> None:
        frame = model_frame((14, 12, 10))
        relaxed = IsolationForestDetector(detector_config(contamination=0.45), FEATURE_COLUMNS).fit(frame)
        strict = IsolationForestDetector(detector_config(contamination=0.05), FEATURE_COLUMNS).fit(frame)
        assert relaxed.predict(frame).sum() > strict.predict(frame).sum()

    def test_serialization_roundtrip(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        frame = model_frame()
        detector = IsolationForestDetector(detector_config(), FEATURE_COLUMNS).fit(frame)
        original = detector.score(frame)
        save_artifact(detector, "FD000", "isolation_forest")
        restored = load_artifact("FD000", "isolation_forest")
        np.testing.assert_allclose(restored.score(frame), original)

    def test_describe_reports_healthy_definition_and_caveat(self) -> None:
        detector = IsolationForestDetector(detector_config(), FEATURE_COLUMNS).fit(model_frame())
        summary = detector.describe()
        assert summary["model_type"] == "IsolationForestDetector"
        assert "rul_raw >= 5" in summary["healthy_definition"]
        assert "simulated" in summary["caveat"]


# -------------------------------------------------------- failure classifiers


class TestForestClassifier:
    def test_train_requires_both_classes(self) -> None:
        frame = model_frame((12,)).assign(  # one engine, last `horizon` rows labelled
            **{f"failure_within_{HORIZON}": 1}
        )
        with pytest.raises(ValueError, match="both classes"):
            ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)

    def test_missing_label_column_rejected(self) -> None:
        frame = model_frame().drop(columns=[f"failure_within_{HORIZON}"])
        with pytest.raises(ValueError, match="failure label"):
            ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)

    def test_probability_output_is_valid(self) -> None:
        frame = model_frame()
        model = ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)
        probabilities = model.predict_proba(frame)
        assert probabilities.shape == (len(frame), 2)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-9)
        assert probabilities.min() >= 0.0 and probabilities.max() <= 1.0
        assert set(np.unique(model.predict(frame))) <= {0, 1}

    def test_reproducible_and_engine_separated(self) -> None:
        train, holdout = model_frame((14,)), model_frame((12,))
        first = ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(train)
        second = ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(train)
        np.testing.assert_array_equal(first.predict(holdout), second.predict(holdout))
        assert first.class_counts_ == {0: 10, 1: 4}  # engine 1: lifespan 14, horizon 3
        with pytest.raises(RuntimeError, match="not fitted"):
            ForestFailureClassifier(forest_config(), horizon=HORIZON).check_fitted()

    def test_importances_sorted_descending(self) -> None:
        model = ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(model_frame())
        importances = model.feature_importances()
        assert list(importances.index) == FEATURE_COLUMNS or len(importances) == len(FEATURE_COLUMNS)
        assert importances.is_monotonic_decreasing if len(importances) > 1 else True

    def test_serialization_roundtrip(self) -> None:
        frame = model_frame((14, 12))
        model = ForestFailureClassifier(forest_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)
        expected = model.predict(frame)
        save_artifact(model, "FD000", "random_forest")
        restored = load_artifact("FD000", "random_forest")
        np.testing.assert_array_equal(restored.predict(frame), expected)


class TestBoostClassifier:
    def test_probability_output_is_valid(self) -> None:
        frame = model_frame()
        model = BoostFailureClassifier(boost_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)
        probabilities = model.predict_proba(frame)
        assert probabilities.shape == (len(frame), 2)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, atol=1e-9)
        assert probabilities.min() >= 0.0 and probabilities.max() <= 1.0

    def test_early_stopping_uses_validation_engines(self) -> None:
        train, val = model_frame((14,)), model_frame((12,))
        model = BoostFailureClassifier(boost_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(train, eval_frame=val)
        # valid range: 0 (stopped from the first round) .. n-1
        assert 0 <= model.best_iteration_ < boost_config().n_estimators
        summary = model.describe()
        assert summary["early_stopping"]["eval_engines"] == 1
        assert "never used" in summary["early_stopping"]["note"]

    def test_empty_eval_frame_rejected(self) -> None:
        frame = model_frame()
        model = BoostFailureClassifier(boost_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS)
        with pytest.raises(ValueError, match="empty eval_frame"):
            model.fit(frame, eval_frame=frame.iloc[0:0])

    def test_class_counts_and_automation_recorded(self) -> None:
        model = BoostFailureClassifier(boost_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(model_frame())
        assert model.class_counts_ == {0: 18, 1: 8}  # engines (14, 12) with horizon 3
        summary = model.describe()
        assert summary["class_counts"] == {0: 18, 1: 8}

    def test_serialization_roundtrip(self) -> None:
        frame = model_frame((14, 12))
        model = BoostFailureClassifier(boost_config(), horizon=HORIZON, feature_columns=FEATURE_COLUMNS).fit(frame)
        expected = model.predict(frame)
        save_artifact(model, "FD000", "xgboost")
        restored = load_artifact("FD000", "xgboost")
        np.testing.assert_array_equal(restored.predict(frame), expected)


# ------------------------------------------------------------- evaluation


class TestClassificationMetrics:
    HANDS = (
        np.array([0, 0, 1, 1]),
        np.array([0.1, 0.4, 0.35, 0.8]),
    )

    def test_metrics_match_hand_computation(self) -> None:
        y_true, y_score = self.HANDS
        metrics = classification_metrics(y_true, y_score, threshold=0.5)
        assert metrics["precision"] == pytest.approx(1.0)  # tp=1, fp=0
        assert metrics["recall"] == pytest.approx(0.5)
        assert metrics["f1"] == pytest.approx(2 / 3)
        assert metrics["roc_auc"] == pytest.approx(0.75)
        assert metrics["pr_auc"] == pytest.approx(0.8333333333333333)  # hand-derived average precision
        assert metrics["macro_f1"] == pytest.approx(11 / 15, abs=1e-9)  # (f1_healthy=0.8 + f1_failure=2/3) / 2
        assert metrics["confusion_matrix"] == {"tn": 2, "fp": 0, "fn": 1, "tp": 1}
        assert metrics["false_negatives"] == 1 and metrics["false_positives"] == 0

    def test_single_class_auc_is_none(self) -> None:
        metrics = classification_metrics(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3]))
        assert metrics["roc_auc"] is None and metrics["pr_auc"] is None

    def test_explicit_predictions_override_threshold(self) -> None:
        y_true, y_score = self.HANDS
        metrics = classification_metrics(y_true, y_score, y_pred=np.array([1, 1, 1, 1]))
        assert metrics["confusion_matrix"] == {"tn": 0, "fp": 2, "fn": 0, "tp": 2}

    def test_healthy_fpr_fraction(self) -> None:
        y_true = np.array([0, 0, 1, 0])
        y_pred = np.array([1, 0, 1, 1])
        assert healthy_false_positive_rate(y_true, y_pred) == pytest.approx(2 / 3)
        assert healthy_false_positive_rate(np.array([1, 1]), np.array([1, 1])) is None


class TestLeadTime:
    def test_lead_is_remaining_life_at_first_alert(self) -> None:
        frame = model_frame((4, 3), degradation_gap=0.0)  # engine rows: rul 3..0 and 2..0
        y_pred = np.array([0, 1, 1, 0, 0, 0, 0])
        y_true = frame[f"failure_within_{HORIZON}"].to_numpy()
        result = detection_lead_time(frame, y_pred, y_true)
        assert result["engines_with_degradation"] == 2
        assert result["engines_detected"] == 1
        assert result["detection_rate"] == pytest.approx(0.5)
        assert result["mean_lead_cycles"] == pytest.approx(2.0)  # remaining life at cycle 2 of engine 1

    def test_no_degraded_rows_returns_empty_stats(self) -> None:
        frame = model_frame((14,)).assign(**{f"failure_within_{HORIZON}": 0, "rul_raw": 100.0})
        result = detection_lead_time(frame, np.zeros(len(frame), dtype=int), frame[f"failure_within_{HORIZON}"].to_numpy())
        assert result["engines_with_degradation"] == 0
        assert result["detection_rate"] is None
        assert result["mean_lead_cycles"] is None


class TestAnomalyMetricBlocks:
    def test_block_uses_given_predictions(self) -> None:
        y_true = np.array([0, 0, 1, 1, 1])
        y_score = np.array([0.1, 0.2, 0.5, 0.9, 0.8])
        y_pred = np.array([1, 0, 1, 1, 0])
        metrics = anomaly_metrics(y_true, y_score, y_pred)
        assert metrics["precision"] == pytest.approx(2 / 3)
        assert metrics["recall"] == pytest.approx(2 / 3)
        assert metrics["healthy_cycle_fpr"] == pytest.approx(0.5)
        assert metrics["anomaly_score_quantiles"]["degraded"]["n"] == 3
        # all positive scores above all negative scores -> AUC exactly 1
        assert metrics["roc_auc"] == pytest.approx(1.0)

    def test_quantiles_exist_for_both_classes(self) -> None:
        quantiles = score_quantiles(np.array([0.1, 0.2, 0.9, 0.8]), np.array([0, 0, 1, 1]))
        assert set(quantiles) == {"healthy", "degraded"}
        assert quantiles["healthy"]["median"] == pytest.approx(0.15)

    def test_numpy_scalars_jsonifiable(self) -> None:
        payload = _jsonifiable({"a": np.int64(3), "b": [np.float64(1.5), None], "c": np.float64(np.nan)})
        assert payload == {"a": 3, "b": [1.5, None], "c": None}


# ------------------------------------------------------------ persistence


class TestPersistence:
    def test_manifest_roundtrip_and_environment(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        write_manifest({"split_seed": 42}, "FD000", "random_forest")
        assert read_manifest("FD000", "random_forest") == {"split_seed": 42}
        versions = environment_versions()
        assert {"numpy", "pandas", "sklearn"} <= set(versions)

    def test_artifact_naming(self) -> None:
        assert model_name("xgboost") == "xgboost"
        assert model_name("xgboost", ablated=True) == "xgboost_no_s10_s16"
        assert ablation_applies("FD002") and ablation_applies("FD004")
        assert not ablation_applies("FD001")
        with pytest.raises(ValueError, match="unknown model kind"):
            model_name("prophet")
