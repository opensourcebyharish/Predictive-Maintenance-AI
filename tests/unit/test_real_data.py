"""Smoke tests against the *real* downloaded C-MAPSS files.

Skipped automatically while the dataset is not present, so the suite stays
green on a fresh checkout without network access.
"""

from __future__ import annotations

import pytest

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import (
    load_cmapss,
    load_rul,
    raw_cmapss_columns,
)

pytestmark = pytest.mark.skipif(
    not (config.CMAPSS_DATA_DIR / "readme.txt").is_file(),
    reason="C-MAPSS data not downloaded yet (run scripts/download_data.py)",
)


@pytest.mark.parametrize("dataset_id", list(config.DATASET_IDS))
def test_train_subsets_match_readme_engine_counts(dataset_id: str) -> None:
    df = load_cmapss(dataset_id, "train")
    assert int(df["unit"].nunique()) == config.DATASETS[dataset_id].n_train_units
    assert list(df.columns) == list(raw_cmapss_columns())
    assert not df.isna().any().any()


def test_fd001_train_cycles_increase_per_engine() -> None:
    df = load_cmapss("FD001", "train")
    grouped = df.groupby("unit")["cycle"].apply(list)
    assert grouped.apply(lambda cycles: cycles == sorted(cycles) and len(set(cycles)) == len(cycles)).all()


def test_fd001_rul_label_count_matches_test_set() -> None:
    test_df = load_cmapss("FD001", "test")
    labels = load_rul("FD001")
    assert len(labels) == config.DATASETS["FD001"].n_test_units
    assert len(labels) == int(test_df["unit"].nunique())
