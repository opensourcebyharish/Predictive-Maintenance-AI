"""Unit tests for Phase 2.1 preprocessing: validation, features, leakage.

Synthetic frames only - no charts, no real dataset, deterministic seeds. The
real-dataset integration checks live in ``test_preprocessing_real.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from predictive_maintenance.data.cmapss import SENSOR_COLUMNS
from predictive_maintenance.preprocessing import (
    PreprocessingConfig,
    PreprocessingPipeline,
    RegimeEncoder,
    add_rolling_features,
    add_targets,
    engine_group_split,
    feature_column_names,
    history_mean,
    history_slope,
    history_std,
    remaining_cycles,
    sort_by_engine,
    validate_cmapss_dataset,
    validate_engine_frame,
)

WINDOW = 3


def synthetic_frame(
    lifespans: tuple[int, ...] = (4, 3),
    regime: tuple[float, float] = (10.0, 0.25),
    extra_rows: dict[int, list[tuple[int, float]]] | None = None,
) -> pd.DataFrame:
    """Miniature engine-run frame in C-MAPSS layout (settings + all sensors).

    Sensor s<index> equals ``index + 0.1 * cycle`` scaled by the engine's
    ordinal, so engineered features are easy to verify by hand. The frame is
    already in canonical (unit, cycle) order.
    """
    rows = []
    for unit_index, lifespan in enumerate(lifespans, start=1):
        for cycle in range(1, lifespan + 1):
            sensors = [index + 0.1 * cycle * unit_index for index in range(1, 22)]
            values = [unit_index, cycle, regime[0], regime[1], 100.0, *sensors]
            rows.append(values)
    return pd.DataFrame(rows, columns=["unit", "cycle", "setting_1", "setting_2", "setting_3", *SENSOR_COLUMNS])


# --------------------------------------------------------------- validation


class TestValidation:
    def test_missing_required_columns_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing required columns"):
            validate_engine_frame(pd.DataFrame({"cycle": [1]}))

    def test_cycle_must_not_decrease_within_engine(self) -> None:
        frame = synthetic_frame((3,))
        frame.loc[1, "cycle"] = 1  # second row repeats cycle 1
        with pytest.raises(ValueError, match="cycle must strictly increase"):
            validate_engine_frame(frame)

    def test_duplicate_key_rejected(self) -> None:
        frame = pd.DataFrame(
            {"unit": [1, 1, 2], "cycle": [1, 1, 1], "s1": [1.0, 1.0, 2.0]}
        )
        # the repeated cycle also breaks monotonicity, so either diagnostic is valid
        with pytest.raises(ValueError, match="duplicate|strictly increase"):
            validate_engine_frame(frame)

    def test_strict_cmapss_layout_rejects_broken_columns(self) -> None:
        frame = synthetic_frame().drop(columns=["s21"])
        with pytest.raises(ValueError, match="expected columns"):
            validate_cmapss_dataset({"FD001": frame})

    def test_strict_cmapss_layout_rejects_unit_gaps(self) -> None:
        train = {"FD001": synthetic_frame()}
        validate_cmapss_dataset(train)
        broken = {**train, "FD002": synthetic_frame().assign(unit=lambda df: df["unit"] + 1)}
        with pytest.raises(ValueError, match="contiguous"):
            validate_cmapss_dataset({**train, **broken})


# ------------------------------------------------------------- targets


class TestTargets:
    def test_remaining_cycles_and_rul_cap(self) -> None:
        frame = add_targets(synthetic_frame((4, 3)), rul_cap=2, horizon=2)
        grouped = frame.groupby("unit")["rul_raw"]
        assert grouped.apply(lambda series: series.is_monotonic_decreasing).all()
        assert grouped.apply(lambda series: series.min()).tolist() == [0, 0]
        assert frame[frame["unit"] == 1]["rul_raw"].tolist() == [3, 2, 1, 0]
        assert frame[frame["unit"] == 1]["RUL"].tolist() == [2, 2, 1, 0]  # capped

    def test_failure_label_boundary_is_inclusive(self) -> None:
        horizon = 2
        frame = add_targets(synthetic_frame((4, 3)), rul_cap=130, horizon=horizon)
        assert frame[frame["unit"] == 1]["rul_raw"].tolist() == [3, 2, 1, 0]
        # rul_raw == horizon is labelled positive: failure guaranteed within horizon
        assert frame[frame["unit"] == 1][ f"failure_within_{horizon}"].tolist() == [0, 1, 1, 1]
        assert frame[frame["unit"] == 2]["rul_raw"].tolist() == [2, 1, 0]
        assert frame[frame["unit"] == 2][f"failure_within_{horizon}"].tolist() == [1, 1, 1]
        assert set(frame.failure_within_2.unique()) <= {0, 1}

    def test_horizon_beyond_cap_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="censored"):
            add_targets(synthetic_frame(), rul_cap=130, horizon=180)


# ------------------------------------------------------------- rolling math


class TestRollingHistory:
    def test_trailing_mean_uses_partial_windows(self) -> None:
        values = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        assert history_mean(values, 3).tolist() == pytest.approx([0.0, 0.5, 1.0, 2.0, 3.0])

    def test_trailing_std_two_samples_needed(self) -> None:
        values = np.array([0.0, 1.0, 2.0])
        result = history_std(values, 3)
        assert result[0] == pytest.approx(0.0)  # only one sample -> spread 0
        assert result[1] == pytest.approx(np.std([0.0, 1.0], ddof=1))
        assert result[2] == pytest.approx(np.std([0.0, 1.0, 2.0], ddof=1))

    def test_trend_slope_matches_closed_form(self) -> None:
        assert history_slope(np.array([0.0, 2.0, 2.0]), WINDOW).tolist() == pytest.approx([0.0, 2.0, 1.0])
        linear = np.arange(5, dtype=float)
        assert history_slope(linear, WINDOW).tolist() == pytest.approx([0.0, 1.0, 1.0, 1.0, 1.0])

    def test_feature_names_are_deterministic(self) -> None:
        names = feature_column_names(["s3", "s7"], WINDOW)
        assert names == [
            "s3_lvl", "s3_rm3", "s3_rs3", "s3_sl3",
            "s7_lvl", "s7_rm3", "s7_rs3", "s7_sl3",
        ]

    def test_rolling_features_never_cross_engines(self) -> None:
        # identical sensor trajectories in both engines -> identical features
        frame = synthetic_frame((3, 3))
        same_sensors = pd.DataFrame(
            {
                "unit": [1, 1, 1, 2, 2, 2],
                "cycle": [1, 2, 3, 1, 2, 3],
                "s3": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
            }
        )
        result = add_rolling_features(same_sensors, {"s3": "s3"}, WINDOW)
        engine_one = result[result["unit"] == 1]["s3_rm3"].tolist()
        engine_two = result[result["unit"] == 2]["s3_rm3"].tolist()
        assert engine_one == engine_two == pytest.approx([1.0, 1.5, 2.0])
        # and each engine's trailing window never averages the other one's rows:
        different = synthetic_frame((3, 3))  # engines here have different trajectories
        mixed_only = add_rolling_features(different, {"s3": "s3"}, WINDOW)
        first_of_engine_two = different[different["unit"] == 2]["s3"].iloc[0]
        assert mixed_only[mixed_only["unit"] == 2]["s3_rm3"].iloc[0] == pytest.approx(
            first_of_engine_two
        )

    def test_rolling_features_reject_unordered_frames(self) -> None:
        frame = synthetic_frame((3, 3)).iloc[::-1].reset_index(drop=True)
        with pytest.raises(ValueError, match="strictly increase"):
            add_rolling_features(frame, {"s3": "s3"}, WINDOW)


# ------------------------------------------------------------- regimes


class TestRegimes:
    def test_learned_centers_match_canonical_conditions(self) -> None:
        frame = _multi_regime_frame()
        encoder = RegimeEncoder().fit(frame)
        summary = encoder.describe()
        assert summary["n_regimes"] == 2
        assert summary["altitude_centers"] == pytest.approx([10.0, 35.0])

    def test_single_regime_degenerates_to_one_condition(self) -> None:
        frame = synthetic_frame()
        conditions = RegimeEncoder().fit(frame).transform(frame)
        assert set(conditions.unique()) == {0}

    def test_unknown_pair_falls_back_to_nearest_regime(self) -> None:
        frame = _multi_regime_frame()
        encoder = RegimeEncoder().fit(frame)
        novel = pd.DataFrame(
            {
                "unit": [99],
                "cycle": [1],
                "setting_1": [22.0],  # between altitude 10 and 35
                "setting_2": [0.25],
                "setting_3": [100.0],
                **{"s%d" % index: [0.0] for index in range(1, 22)},
            }
        )
        conditions = encoder.transform(novel)
        assert conditions.iloc[0] in {code for code in range(len(encoder.pairs))}


def _multi_regime_frame(factor: int = 6) -> pd.DataFrame:
    """Two-regime synthetic frame: 3 engines per regime with paired settings."""
    frames = []
    for regime_index, regime in enumerate([(10.0, 0.25), (35.0, 0.62)]):
        rows = []
        for offset, lifespan in enumerate((3, 4, 5)):
            unit = regime_index * factor + offset + 1
            for cycle in range(1, lifespan + 1):
                sensors = [index + 0.1 * cycle * (unit % 10) for index in range(1, 22)]
                rows.append([unit, cycle, regime[0], regime[1], 100.0, *sensors])
        frames.append(pd.DataFrame(rows, columns=["unit", "cycle", "setting_1", "setting_2", "setting_3", *SENSOR_COLUMNS]))
    return sort_by_engine(pd.concat(frames, ignore_index=True))


# ------------------------------------------------------------- splits


class TestEngineGroupSplit:
    def test_engines_are_disjoint_and_complete(self) -> None:
        frame = synthetic_frame(tuple(range(1, 11)))  # 10 engines
        train, holdout = engine_group_split(frame, test_fraction=0.2, seed=7)
        train_units = set(train["unit"])
        holdout_units = set(holdout["unit"])
        assert not train_units & holdout_units
        assert train_units | holdout_units == set(range(1, 11))
        assert len(train) + len(holdout) == len(frame)

    def test_split_is_deterministic_given_seed(self) -> None:
        frame = synthetic_frame(tuple(range(1, 11)))
        first = engine_group_split(frame, test_fraction=0.3, seed=3)
        second = engine_group_split(frame, test_fraction=0.3, seed=3)
        assert set(first[0]["unit"]) == set(second[0]["unit"])
        assert set(first[1]["unit"]) == set(second[1]["unit"])

    def test_fraction_bounds_and_tiny_fleets_rejected(self) -> None:
        frame = synthetic_frame((4, 3))
        with pytest.raises(ValueError, match="test_fraction"):
            engine_group_split(frame, test_fraction=1.5)
        with pytest.raises(ValueError, match="at least 2 engines"):
            engine_group_split(frame.iloc[:3], test_fraction=0.2)


# ------------------------------------------------------------- pipeline


class TestPreprocessingPipeline:
    def _pipeline(self, **overrides) -> PreprocessingPipeline:
        return PreprocessingPipeline(
            PreprocessingConfig(rolling_window=WINDOW, rul_cap=8, failure_horizon=2, **overrides)
        )

    def test_fit_transform_is_deterministic_and_schema_stable(self) -> None:
        train = _multi_regime_frame()
        pipeline = self._pipeline()
        first = pipeline.fit_transform(train)
        rebuilt = self._pipeline().fit_transform(train)
        assert first.equals(rebuilt)
        assert pipeline.check_fitted() is None
        head = ["unit", "cycle", "condition_id", "setting_1", "setting_2", "setting_3"]
        assert list(first.columns[: len(head)]) == head
        assert list(first.columns[len(head):len(head) + 3]) == ["rul_raw", "RUL", "failure_within_2"]
        assert not (set(pipeline.sensor_columns) & set(first.columns))  # raw sensors excluded

    def test_training_features_are_standardized(self) -> None:
        train = _multi_regime_frame()
        pipeline = self._pipeline()
        out = pipeline.fit_transform(train)
        numeric = out[pipeline.feature_columns]
        assert numeric.mean().abs().max() == pytest.approx(0.0, abs=1e-9)
        assert (numeric.std(ddof=0).max() - 1.0) < 1e-9

    def test_constants_dropped_and_absent_from_all_outputs(self) -> None:
        frame = synthetic_frame((4, 3))
        frame["s17"] = 0.0  # sensor with zero variance
        pipeline = self._pipeline()
        train_out = pipeline.fit_transform(frame)
        assert "s17" in pipeline.dropped_sensors
        assert not any(column.startswith("s17") for column in train_out.columns)

    def test_train_only_statistics_used_for_new_data(self) -> None:
        train = synthetic_frame((6, 5, 4, 3, 3))  # s-values: mean over these rows
        other = synthetic_frame((5, 5))
        pipeline = self._pipeline(drop_constant_sensors=False).fit(train)
        expected_mean = train["s3"].mean()
        expected_std = train["s3"].std(ddof=0)
        out = pipeline.transform(other)
        expected_level = (other["s3"] - expected_mean) / expected_std
        assert out["s3_lvl"].sub(expected_level).abs().max() < 1e-9
        # sanity: the same normalization was NOT re-fit on the new data
        other_only_mean = other["s3"].mean()
        assert other_only_mean != pytest.approx(expected_mean)

    def test_missing_values_imputed_from_engine_past_then_train_median(self) -> None:
        train = synthetic_frame((4, 3))
        frame = synthetic_frame((4, 3))
        frame.loc[2, "s3"] = np.nan   # inner row of engine 1 (later row: cycle 3)
        frame.loc[0, "s9"] = np.nan   # leading row -> per-regime train median
        pipeline = self._pipeline(drop_constant_sensors=False).fit(train)

        out = pipeline.transform(frame)
        # the NaN sits in engine 1 cycle 3; forward fill copies cycle 2's value
        imputed_inner = out[(out.unit == 1) & (out.cycle == 3)]["s3_lvl"]
        from_past = out[(out.unit == 1) & (out.cycle == 2)]["s3_lvl"]
        assert imputed_inner.iloc[0] == pytest.approx(from_past.iloc[0])  # ffill wins

        expected_lead = (pipeline.impute_median[(0, "s9")] - pipeline.global_mean["s9"]) / pipeline.global_std["s9"]
        assert out[(out.unit == 1) & (out.cycle == 1)]["s9_lvl"].iloc[0] == pytest.approx(expected_lead)
        assert not out.isna().any().any()

    def test_condition_id_present_and_regimes_learned(self) -> None:
        train = _multi_regime_frame()
        pipeline = self._pipeline()
        out = pipeline.fit_transform(train)
        assert set(out["condition_id"].unique()) == {0, 1}
        assert pipeline.regimes is not None and len(pipeline.regimes.pairs) == 2

    def test_empty_input_transforms_to_empty_schema(self) -> None:
        pipeline = self._pipeline().fit(synthetic_frame())
        out = pipeline.transform(synthetic_frame().iloc[0:0])
        assert out.empty
        assert list(out.columns)[:3] == ["unit", "cycle", "condition_id"]
        assert list(out.columns)[-1] == pipeline.feature_columns[-1]

    def test_not_fitted_check(self) -> None:
        with pytest.raises(RuntimeError, match="not fitted"):
            self._pipeline().transform(synthetic_frame())

    def test_invalid_config_rejected(self) -> None:
        with pytest.raises(ValueError, match="rolling_window"):
            PreprocessingConfig(rolling_window=1)
        with pytest.raises(ValueError, match="rul_cap"):
            PreprocessingConfig(rolling_window=WINDOW, rul_cap=2, failure_horizon=30)
        with pytest.raises(ValueError, match="constant_tolerance"):
            PreprocessingConfig(constant_tolerance=-1.0)
