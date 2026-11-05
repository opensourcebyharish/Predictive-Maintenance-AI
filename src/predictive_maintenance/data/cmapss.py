"""Loaders for the NASA C-MAPSS turbofan degradation dataset.

The raw files are header-less, space-separated tables. ``train_<id>.txt`` and
``test_<id>.txt`` hold 26 columns (unit, cycle, 3 operating settings, 21 sensor
signals); ``RUL_<id>.txt`` holds one remaining-life value per *line*, one line
per test engine. Train trajectories run to failure; test trajectories are
truncated and their ground-truth remaining life is the label file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from predictive_maintenance import config

UNIT_COLUMNS: tuple[str, ...] = ("unit", "cycle")
OP_SETTING_COLUMNS: tuple[str, ...] = ("setting_1", "setting_2", "setting_3")
# Raw file columns 6..26 -> sensor signals s1..s21 (names in config.SENSOR_LABELS).
SENSOR_COLUMNS: list[str] = [f"s{index}" for index in range(1, 22)]


def raw_cmapss_columns() -> tuple[str, ...]:
    """The 26 raw-file column names in file order.

    Kept as a function (over a plain constant) because tests treat it as the
    single source of truth for the documented layout.
    """
    return (
        "unit",
        "cycle",
        "setting_1",
        "setting_2",
        "setting_3",
        *SENSOR_COLUMNS,
    )


# Everything a model may consume in Phase 2 (settings identify the regime).
FEATURE_COLUMNS: list[str] = [*OP_SETTING_COLUMNS, *SENSOR_COLUMNS]

_VALID_SPLITS: tuple[str, ...] = ("train", "test")


def subset_path(dataset_id: str, split: str, directory: Path | None = None) -> Path:
    """Path of one split file, validating ids/splits so errors are actionable."""
    if dataset_id not in config.DATASET_IDS:
        raise ValueError(f"Unknown dataset id {dataset_id!r} (expected one of {config.DATASET_IDS})")
    if split not in _VALID_SPLITS:
        raise ValueError(f"Unknown split {split!r} (expected 'train' or 'test')")
    base = config.CMAPSS_DATA_DIR if directory is None else Path(directory)
    return base / f"{split}_{dataset_id}.txt"


def rul_path(dataset_id: str, directory: Path | None = None) -> Path:
    """Path of one test-set label file (``RUL_<id>.txt``)."""
    if dataset_id not in config.DATASET_IDS:
        raise ValueError(f"Unknown dataset id {dataset_id!r} (expected one of {config.DATASET_IDS})")
    base = config.CMAPSS_DATA_DIR if directory is None else Path(directory)
    return base / f"RUL_{dataset_id}.txt"


def _read_space_table(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=r"\s+", header=None, names=list(raw_cmapss_columns()))
    if frame.shape[1] != 26 or frame.isna().any().any():
        raise ValueError(f"{path.name}: expected 26 numeric columns; file may be truncated")
    return frame


def load_cmapss(dataset_id: str, split: str, directory: Path | None = None) -> pd.DataFrame:
    """Load one subset's ``train_<id>.txt`` / ``test_<id>.txt`` with names applied."""
    path = subset_path(dataset_id, split, directory)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing - run 'python scripts/download_data.py' first (C-MAPSS file)."
        )
    return _read_space_table(path)


def load_rul(dataset_id: str, directory: Path | None = None) -> pd.DataFrame:
    """Load ``RUL_<id>.txt`` -> DataFrame with ``unit`` (1-based) and ``RUL``.

    The ``i``-th value is the remaining life after the last observed cycle of
    test engine ``i`` (aligning with ``load_cmapss(dataset_id, "test")``).
    """
    path = rul_path(dataset_id, directory)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing - run 'python scripts/download_data.py' first (C-MAPSS file)."
        )
    values = pd.read_csv(path, header=None, names=["RUL"])
    return pd.DataFrame({"unit": range(1, len(values) + 1), "RUL": values["RUL"]})


def add_rul(frame: pd.DataFrame, cap: int | None = config.RUL_CAP) -> pd.DataFrame:
    """Add the remaining-useful-life column ``RUL = cycles_left_at_row``.

    ``cap`` implements the standard piecewise-linear target (health is
    indistinguishable beyond ``cap`` cycles, so RUL is clipped there);
    ``cap=None`` keeps the full uncapped range, as used by the EDA.
    """
    result = frame.copy()
    last_cycle = result.groupby("unit")["cycle"].transform("max")
    rul = last_cycle - result["cycle"]
    if cap is not None:
        rul = rul.clip(upper=cap)
    result["RUL"] = rul
    return result
