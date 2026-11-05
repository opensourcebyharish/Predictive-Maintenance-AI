"""Validation of engine-run frames and of the loaded C-MAPSS ids.

Two levels:

* ``validate_engine_frame`` - structural sanity for *any* frame carrying
  ``unit``/``cycle`` (loaders, simulator rows, later API ingestion).
* ``validate_cmapss_dataset`` - the strict layout contract of the raw files:
  contiguous unit ids 1..N, integer dtypes, documented 26 columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from predictive_maintenance.data.cmapss import raw_cmapss_columns

ENGINE_COLUMN = "unit"
CYCLE_COLUMN = "cycle"


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing required columns: {missing}")


def validate_engine_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Check a run-level frame is a coherent time series per engine.

    Enforces: ``unit``/``cycle`` present and NaN-free, cycle strictly
    increasing within every engine, at most one row per (unit, cycle).
    Returns the input unchanged (never mutates) so callers can chain.
    """
    _require_columns(frame, (ENGINE_COLUMN, CYCLE_COLUMN))
    keys = frame[[ENGINE_COLUMN, CYCLE_COLUMN]]
    if keys.isna().any().any():
        raise ValueError("unit/cycle columns must not contain missing values")

    grouped = frame.groupby(ENGINE_COLUMN, sort=False)[CYCLE_COLUMN]
    steps = grouped.diff()
    bad_units = frame.loc[steps <= 0.0, ENGINE_COLUMN].unique()
    if len(bad_units) > 0:
        raise ValueError(
            f"cycle must strictly increase within an engine; broken engines: {sorted(bad_units)}"
        )
    duplicates = keys.duplicated()
    if duplicates.any():
        first = int(np.flatnonzero(duplicates.to_numpy())[0])
        raise ValueError(f"duplicate (unit, cycle) row at position {first}")
    return frame


def validate_cmapss_dataset(
    train: dict[str, pd.DataFrame],
    test: dict[str, pd.DataFrame] | None = None,
) -> None:
    """Validate every loaded C-MAPSS subset against the documented layout.

    * exact 26 raw columns, integer unit/cycle, no NaNs;
    * engine ids are the contiguous range 1..N (parallel to ``RUL_<id>.txt``);
    * cycles start at 1 and are consecutive per engine.
    """
    for dataset_id, frame in train.items():
        _validate_subset(dataset_id, frame, split="train")
    if test is not None:
        for dataset_id, frame in test.items():
            _validate_subset(dataset_id, frame, split="test")


def _validate_subset(dataset_id: str, frame: pd.DataFrame, split: str) -> None:
    expected_columns = list(raw_cmapss_columns())
    if list(frame.columns) != expected_columns:
        raise ValueError(f"{split}_{dataset_id}: expected columns {expected_columns}")
    _require_columns(frame, (ENGINE_COLUMN, CYCLE_COLUMN))
    if frame.isna().any().any():
        raise ValueError(f"{split}_{dataset_id}: unexpected missing values in raw file")
    for column in (ENGINE_COLUMN, CYCLE_COLUMN):
        if not pd.api.types.is_integer_dtype(frame[column]):
            raise ValueError(f"{split}_{dataset_id}: {column} must have integer dtype")
    units = frame[ENGINE_COLUMN].unique()
    if not np.array_equal(np.sort(units), np.arange(1, len(units) + 1)):
        raise ValueError(f"{split}_{dataset_id}: unit ids must be contiguous 1..N")
    if (frame[CYCLE_COLUMN] <= 0).any():
        raise ValueError(f"{split}_{dataset_id}: cycle numbers must be >= 1")
    _validate_gaps(dataset_id, frame, split)


def _validate_gaps(dataset_id: str, frame: pd.DataFrame, split: str) -> None:
    grouped = frame.groupby(ENGINE_COLUMN)[CYCLE_COLUMN]
    counts = grouped.size()
    last = grouped.max()
    if not (counts == last).all():
        offending = counts[counts != last].index[:5].tolist()
        raise ValueError(f"{split}_{dataset_id}: cycle gaps in engines {offending} (must be 1..lifespan)")
