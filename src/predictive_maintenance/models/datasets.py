"""Dataset plumbing for Phase 2.2-2.5: features, labels, splits, versions.

This layer sits on top of the Phase 2.1 preprocessing without modifying it:

* loads the engineered ``features_FD00X_{train,val}.parquet`` tables (building
  them exactly like ``scripts/build_features.py`` when missing),
* derives the model feature matrix by excluding the key/target columns,
* attaches *true* labels to the official NASA test frames (the C-MAPSS
  ``test_FD00X.txt`` trajectories are truncated; ``RUL_FD00X.txt`` holds the
  remaining life at the final observed cycle, so the remaining life of every
  earlier cycle is ``RUL_final + (last_cycle - cycle)``),
* and records a dataset version (SHA-256 of the raw source files) for the
  model manifests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from predictive_maintenance import config
from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, load_cmapss, load_rul
from predictive_maintenance.preprocessing import (
    PreprocessingConfig,
    PreprocessingPipeline,
    engine_group_split,
)
from predictive_maintenance.preprocessing.features import failure_label_column

KEY_COLUMNS: list[str] = ["unit", "cycle"]
TARGET_COLUMNS: list[str] = ["rul_raw", "RUL"]
# Reproduces scripts/build_features.py defaults; recorded in every manifest.
ENGINE_SPLIT_SEED: int = 42
ENGINE_TEST_FRACTION: float = 0.2


def _parquet_path(dataset_id: str, split: str) -> Path:
    return config.PROCESSED_DATA_DIR / f"features_{dataset_id}_{split}.parquet"


def _build_split(dataset_id: str) -> None:
    """Regenerate the Phase 2.1 parquet pair for one subset (default knobs)."""
    train_raw = load_cmapss(dataset_id, "train")
    train_part, val_part = engine_group_split(
        train_raw,
        test_fraction=ENGINE_TEST_FRACTION,
        seed=ENGINE_SPLIT_SEED,
    )
    pipeline = PreprocessingPipeline(PreprocessingConfig())
    train_features = pipeline.fit_transform(train_part)
    val_features = pipeline.transform(val_part)
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    train_features.to_parquet(_parquet_path(dataset_id, "train"), index=False)
    val_features.to_parquet(_parquet_path(dataset_id, "val"), index=False)


def load_split(dataset_id: str, split: str) -> pd.DataFrame:
    """Load one engineered frame, regenerating the parquet when absent."""
    path = _parquet_path(dataset_id, split)
    if not path.is_file():
        _build_split(dataset_id)
    return pd.read_parquet(path)


def select_feature_columns(frame: pd.DataFrame, label_column: str) -> list[str]:
    """Model-input columns: everything except keys, settings and targets."""
    excluded = {
        *KEY_COLUMNS,
        *OP_SETTING_COLUMNS,
        "condition_id",
        *TARGET_COLUMNS,
        label_column,
    }
    return [column for column in frame.columns if column not in excluded]


def ablate_features(columns: list[str], sensors: list[str]) -> list[str]:
    """Drop every feature derived from the listed sensors (e.g. s10, s16)."""
    prefixes = tuple(f"{sensor}_" for sensor in sensors)
    return [column for column in columns if not column.startswith(prefixes)]


def attach_truth_from_rul_file(
    features: pd.DataFrame,
    truth: pd.DataFrame,
    rul_cap: int | None,
    horizon: int,
) -> pd.DataFrame:
    """Overwrite the target columns of an official-test frame with ground truth.

    ``truth`` is the :func:`predictive_maintenance.data.cmapss.load_rul` frame
    (``unit, RUL``: remaining life at the last observed cycle). Earlier cycles
    of the truncated trajectory are reconstructed as
    ``RUL_final + (last_cycle - cycle)`` per engine. The failure label derives
    from the *unclipped* remaining life; ``RUL`` is capped exactly like the
    training targets.
    """
    result = features.copy()
    truth_mapping = truth.set_index("unit")["RUL"]
    last_cycle = result.groupby("unit")["cycle"].transform("max")
    remaining = result["unit"].map(truth_mapping) + (last_cycle - result["cycle"])
    result["rul_raw"] = remaining
    result["RUL"] = remaining if rul_cap is None else remaining.clip(upper=rul_cap)
    result[failure_label_column(horizon)] = (remaining <= horizon).astype(int)
    return result


def dataset_version(dataset_id: str) -> dict[str, object]:
    """Hashes of the raw source files backing one subset (for manifests)."""
    version: dict[str, object] = {}
    for split in ("train", "test"):
        path = config.CMAPSS_DATA_DIR / f"{split}_{dataset_id}.txt"
        version[f"{split}_sha256"] = _sha256(path)
    truth_path = config.CMAPSS_DATA_DIR / f"RUL_{dataset_id}.txt"
    version["rul_sha256"] = _sha256(truth_path)
    version["feature_split_seed"] = ENGINE_SPLIT_SEED
    version["feature_test_fraction"] = ENGINE_TEST_FRACTION
    return version


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_test_features(dataset_id: str, rul_cap: int | None, horizon: int) -> pd.DataFrame:
    """Official NASA test engines: features (train-fitted stats) + true labels.

    The preprocessing statistics stay exactly those fitted on training engines:
    the test frame only passes through ``transform`` and receives labels from
    ``RUL_<id>.txt`` afterwards, preserving the official engine separation.
    """
    raw = load_cmapss(dataset_id, "test")
    features = _train_pipeline(dataset_id).transform(raw)
    truth = load_rul(dataset_id)
    return attach_truth_from_rul_file(features, truth, rul_cap, horizon)


def _train_pipeline(dataset_id: str) -> PreprocessingPipeline:
    """Rebuild the Phase 2.1 fitted pipeline exactly as the parquet build did.

    ``fit`` is deterministic, so the re-fitted pipeline reproduces the
    statistics that produced ``features_<ds>_{train,val}.parquet``.
    """
    train_raw = load_cmapss(dataset_id, "train")
    train_part, _ = engine_group_split(
        train_raw,
        test_fraction=ENGINE_TEST_FRACTION,
        seed=ENGINE_SPLIT_SEED,
    )
    pipeline = PreprocessingPipeline(PreprocessingConfig())
    pipeline.fit(train_part)
    return pipeline
