"""Real-data integration tests for the Phase 2.1 preprocessing pipeline.

The checks below pin down behaviour that synthetic mini-frames cannot prove:
the exact constant-sensor sets of the canonical subsets, the six operating
regimes of FD002/FD004, full row preservation through the engine split, and
fit/transform determinism on thousands of rows.

Skipped automatically while the dataset is not present.
"""

from __future__ import annotations

import pandas as pd
import pytest

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import load_cmapss
from predictive_maintenance.preprocessing import (
    PreprocessingConfig,
    PreprocessingPipeline,
    engine_group_split,
    validate_cmapss_dataset,
)

pytestmark = pytest.mark.skipif(
    not (config.CMAPSS_DATA_DIR / "readme.txt").is_file(),
    reason="C-MAPSS data not downloaded yet (run scripts/download_data.py)",
)

SEED = 42
TEST_FRACTION = 0.2


@pytest.fixture(scope="module")
def built(dataset_ids=("FD001", "FD002")) -> dict[str, tuple[PreprocessingPipeline, pd.DataFrame, pd.DataFrame]]:
    """Pipeline + engineered train/holdout frames per probed subset."""
    results: dict[str, tuple[PreprocessingPipeline, pd.DataFrame, pd.DataFrame]] = {}
    for dataset_id in dataset_ids:
        train = load_cmapss(dataset_id, "train")
        validate_cmapss_dataset({dataset_id: train})
        train_part, holdout_part = engine_group_split(train, test_fraction=TEST_FRACTION, seed=SEED)
        pipeline = PreprocessingPipeline(PreprocessingConfig())
        results[dataset_id] = (pipeline, pipeline.fit_transform(train_part), pipeline.transform(holdout_part))
    return results


class TestFd001Build:
    def test_drops_the_documented_constant_sensors(self, built) -> None:
        pipeline, out, _ = built["FD001"]
        assert pipeline.dropped_sensors == ["s1", "s5", "s10", "s16", "s18", "s19"]
        assert len(pipeline.feature_columns) == 60  # 15 kept sensors x {lvl, rm, rs, sl}

    def test_rows_are_never_dropped(self, built) -> None:
        train = load_cmapss("FD001", "train")
        train_part, holdout_part = engine_group_split(train, test_fraction=TEST_FRACTION, seed=SEED)
        pipeline, train_out, holdout_out = built["FD001"]
        assert len(train_out) == len(train_part)
        assert len(holdout_out) == len(holdout_part)
        assert len(train) == len(train_out) + len(holdout_out)

    def test_engine_disjoint_split_80_20(self, built) -> None:
        pipeline, train_out, holdout_out = built["FD001"]
        assert train_out["unit"].nunique() == 80
        assert holdout_out["unit"].nunique() == 20
        assert not set(train_out["unit"]) & set(holdout_out["unit"])

    def test_single_regime_and_clean_output(self, built) -> None:
        pipeline, train_out, holdout_out = built["FD001"]
        assert set(train_out["condition_id"].unique()) == {0}
        assert not train_out.isna().any().any()
        assert not holdout_out.isna().any().any()
        assert list(train_out.columns) == list(holdout_out.columns)

    def test_train_features_standardized_exactly(self, built) -> None:
        pipeline, train_out, _ = built["FD001"]
        features = train_out[pipeline.feature_columns]
        assert features.mean().abs().max() < 1e-9
        assert (features.std(ddof=0) - 1.0).abs().max() < 1e-9

    def test_chronological_order_preserved(self, built) -> None:
        pipeline, train_out, holdout_out = built["FD001"]
        for out in (train_out, holdout_out):
            monotone = out.groupby("unit")["cycle"].apply(lambda series: series.is_monotonic_increasing)
            assert monotone.all()

    def test_failure_label_ratio_is_plausible(self, built) -> None:
        pipeline, train_out, _ = built["FD001"]
        # last <horizon> cycles of ~80 engines out of ~16.8k rows -> ~15%
        ratio = train_out["failure_within_30"].mean()
        assert 0.10 < ratio < 0.20

    def test_transform_is_deterministic(self, built) -> None:
        train_part, holdout_part = engine_group_split(load_cmapss("FD001", "train"), test_fraction=TEST_FRACTION, seed=SEED)
        pipeline, train_out, _ = built["FD001"]
        assert pipeline.transform(train_part).equals(train_out)


class TestFd002Build:
    def test_six_regimes_learned_and_recovered(self, built) -> None:
        pipeline, train_out, holdout_out = built["FD002"]
        assert len(pipeline.regimes.pairs) == 6
        assert set(train_out["condition_id"].unique()) == set(range(6))
        assert set(holdout_out["condition_id"].unique()) == set(range(6))

    def test_level_normalization_centers_each_regime(self, built) -> None:
        pipeline, train_out, _ = built["FD002"]
        per_regime_mean = train_out.groupby("condition_id")["s11_lvl"].mean()
        assert per_regime_mean.abs().max() < 1e-9

    def test_constant_sensors_drop_and_clean_output(self, built) -> None:
        pipeline, train_out, holdout_out = built["FD002"]
        assert pipeline.dropped_sensors == ["s1", "s5", "s18", "s19"]
        assert len(pipeline.feature_columns) == 68
        assert not train_out.isna().any().any()
        assert not holdout_out.isna().any().any()
