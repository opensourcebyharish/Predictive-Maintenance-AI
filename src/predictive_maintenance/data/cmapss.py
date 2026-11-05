"""Loaders for the NASA C-MAPSS turbofan degradation dataset.

The raw files are header-less, space-separated tables (26 columns: unit, cycle,
3 operating settings, 21 sensor signals). Train trajectories run to failure;
test trajectories are truncated and their remaining life is given separately
in ``RUL_<dataset>.txt`` (one value per test engine).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from predictive_maintenance import config

UNIT_COLUMNS: list[str] = ["unit", "cycle"]
OP_SETTING_COLUMNS: list[str] = ["setting_1", "setting_2", "setting_3"]
# Raw file columns 6..26 -> sensor signals s1..s21 (see config.SENSOR_LABELS).
SENSOR_COLUMNS: list[str] = [f"s{index}" for index in range(1, 22)]

_raw_columns: list[str] = [
    *UNIT_COLUMNS,
    *OP_SETTING_COLUMNS,
    *SENSOR_COLUMNS,
]

# Everything a model may consume in Phase 2 (settings identify the regime).
FEATURE_COLUMNS: list[str] = [*OP_SETTING_COLUMNS, *SENSOR_COLUMNS]


def load_cmapss(dataset_id: str, split: str, directory: Path | None = None) -> pd.DataFrame:
    """Load one subset's ``train_<id>.txt`` or ``test_<id>.txt`` with names applied.

    Raises ``ValueError`` if the split is unknown or the file does not have the
    documented 26 columns (catches truncated / corrupt downloads).
    """
    if split not in ("train", "test"):
        raise ValueError(f"split must be 'train' or 'test', got: {split!r}")
    directory = config.CMAPSS_DATA_DIR if directory is None else Path(directory)
    path = directory / f"{split}_{dataset_id}.txt"
    frame = pd.read_csv(path, sep=r"\s+", header=None, names=_raw_columns)
    if frame.shape[1] != len(_raw_columns) or frame.isna().any().any():
        raise ValueError(f"{path.name}: expected {len(_raw_columns)} numeric columns")
    return frame


def load_rul(dataset_id: str, directory: Path | None = None) -> pd.DataFrame:
    """Load ``RUL_<id>.txt`` -> one row per test engine: ``unit`` and ``RUL``.

    The ``i``-th line is the remaining life after the last observed cycle of
    test engine ``i`` (1-based, matching ``load_cmapss(..., "test")["unit"]``).
    """
    directory = config.CMAPSS_DATA_DIR if directory is None else Path(directory)
    path = directory / f"RUL_{dataset_id}.txt"
    values = pd.read_csv(path, header=None, names=["RUL"])
    return pd.DataFrame({"unit": range(1, len(values) + 1), "RUL": values["RUL"]})


def add_rul(frame: pd.DataFrame, cap: int | None = config.RUL_CAP) -> pd.DataFrame:
    """Add the remaining-useful-life column ``RUL = cycles_left_at_row``.

    ``cap`` implements the standard piecewise-linear target (health is indistinguishable
    beyond ``cap`` cycles, so RUL is clipped there) - pass ``cap=None`` for
    uncapped degradation analysis as done in the EDA.
    """
    result = frame.copy()
    last_cycle = result.groupby("unit")["cycle"].transform("max")
    rul = last_cycle - result["cycle"]
    if cap is not None:
        rul = rul.clip(upper=cap)
    result["RUL"] = rul
    return result
