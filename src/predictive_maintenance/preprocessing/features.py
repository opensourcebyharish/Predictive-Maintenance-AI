"""Time-series feature engineering on per-engine sensor streams.

All operations are *history-only* per engine: rolling windows look strictly
backwards (trailing), the trend slope regresses the last ``window`` cycles, and
prefix rows use the partial history available so far. No feature references
future cycles or other engines, so any prefix of an engine's trajectory maps to
itself - the property the serving/monitoring layer later relies on.

Frames passed here must be engine-ordered (see :func:`sort_by_engine`) so each
engine's rows are contiguous; the functions group by change points of ``unit``,
which keeps per-group work O(rows) with no Python-level groupby overhead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from typing import Mapping

from predictive_maintenance.preprocessing.validation import validate_engine_frame

ENGINE_COLUMN = "unit"
CYCLE_COLUMN = "cycle"
RUL_RAW_COLUMN = "rul_raw"  # uncapped remaining cycles (label truth)
TARGET_COLUMN = "RUL"  # piecewise-linear-capped regression target
LEVEL_SUFFIX = "lvl"  # regime-normalized sensor level
ROLLING_MEAN_PREFIX = "rm"  # trailing mean
ROLLING_STD_PREFIX = "rs"  # trailing std
SLOPE_PREFIX = "sl"  # trailing linear-regression slope


def sort_by_engine(frame: pd.DataFrame) -> pd.DataFrame:
    """Canonical row order (unit, then cycle) with a fresh index."""
    return frame.sort_values([ENGINE_COLUMN, CYCLE_COLUMN], kind="stable").reset_index(drop=True)


def remaining_cycles(frame: pd.DataFrame) -> pd.Series:
    """Uncapped remaining life per row: ``lifespan(engine) - cycle``."""
    last_cycle = frame.groupby(ENGINE_COLUMN)[CYCLE_COLUMN].transform("max")
    return last_cycle - frame[CYCLE_COLUMN]


def failure_label_column(horizon: int) -> str:
    """Column name of the failure-within-horizon label (horizon in cycles)."""
    return f"failure_within_{horizon}"


def add_targets(frame: pd.DataFrame, rul_cap: int | None, horizon: int) -> pd.DataFrame:
    """Attach prediction targets: uncapped RUL, capped RUL, failure label.

    * ``rul_raw``  - uncapped remaining cycles (ground truth, and the *input*
      to the failure label so labels are never censored by the cap);
    * ``RUL``      - piecewise-linear target, ``min(rul_raw, cap)`` (same
      semantics as :func:`predictive_maintenance.data.cmapss.add_rul`);
    * ``failure_within_<horizon>`` - binary label, 1 when the engine fails
      within ``horizon`` more cycles (``rul_raw <= horizon``).

    Raises ``ValueError`` when ``rul_cap`` is set and ``horizon > rul_cap``:
    beyond the cap the true remaining life is unknown, so failure labels would
    be censored and biased.
    """
    if rul_cap is not None and horizon > rul_cap:
        raise ValueError(
            f"failure horizon {horizon} must not exceed the RUL cap {rul_cap} "
            "- labels would be censored beyond the cap"
        )
    result = frame.copy()
    rul_raw = remaining_cycles(result)
    result[RUL_RAW_COLUMN] = rul_raw
    result[TARGET_COLUMN] = rul_raw if rul_cap is None else rul_raw.clip(upper=rul_cap)
    result[failure_label_column(horizon)] = (rul_raw <= horizon).astype(int)
    return result


def history_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing rolling mean; partial windows (min_periods=1) use fewer rows."""
    return pd.Series(values, dtype=float).rolling(window, min_periods=1).mean().to_numpy()


def history_std(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing rolling std; a single sample has no spread, defined as 0.0."""
    std = pd.Series(values, dtype=float).rolling(window, min_periods=2).std()
    return std.fillna(0.0).to_numpy()


def history_slope(values: np.ndarray, window: int) -> np.ndarray:
    """Slope of the per-cycle linear regression over the last ``window`` points.

    Closed-form OLS on each trailing window (sliding-window, read-only view).
    Rows with 0 or 1 data point get slope 0; rows with >= 2 points run a
    partial-window regression, so early rows still carry a meaningful trend.
    """
    values = np.asarray(values, dtype=float)
    result = np.zeros(values.size, dtype=float)
    if values.size < 2:
        return result

    prefix_limit = min(window - 1, values.size - 1)
    for index in range(1, prefix_limit + 1):  # partial windows for the first rows
        result[index] = _ols_slope(values[: index + 1])
    if values.size >= window:
        windows = sliding_window_view(values, window)
        result[window - 1 :] = _ols_slope_batch(windows)
    return result


def _ols_slope(window_values: np.ndarray) -> float:
    """OLS slope of a 1-D window against the 0..n-1 cycle index."""
    count = window_values.size
    index = np.arange(count, dtype=float)
    numerator = count * float(window_values @ index) - float(window_values.sum()) * float(index.sum())
    denominator = count * float(index @ index) - float(index.sum()) ** 2
    return numerator / denominator


def _ols_slope_batch(window_matrix: np.ndarray) -> np.ndarray:
    """OLS slopes for a stack of trailing windows, one row per window."""
    count = window_matrix.shape[1]
    index = np.arange(count, dtype=float)
    numerator = count * (window_matrix @ index) - window_matrix.sum(axis=1) * index.sum()
    denominator = count * float(index @ index) - float(index.sum()) ** 2
    return numerator / denominator


def feature_column_names(sensor_columns: list[str] | tuple[str, ...], window: int) -> list[str]:
    """Feature columns the rolling layer emits per sensor (deterministic order)."""
    return [
        f"{sensor}_{suffix}"
        for sensor in sensor_columns
        for suffix in (
            LEVEL_SUFFIX,
            f"{ROLLING_MEAN_PREFIX}{window}",
            f"{ROLLING_STD_PREFIX}{window}",
            f"{SLOPE_PREFIX}{window}",
        )
    ]


def engine_segments(engine_ids: pd.Series) -> list[tuple[int, int]]:
    """Contiguous [start, end) row ranges of each engine in an ordered frame."""
    engine_array = engine_ids.to_numpy()
    change_points = np.flatnonzero(engine_array[1:] != engine_array[:-1]) + 1
    bounds = np.concatenate(([0], change_points, [len(engine_array)]))
    return list(zip(bounds[:-1], bounds[1:]))


def add_rolling_features(
    frame: pd.DataFrame,
    source_by_base: Mapping[str, str],
    window: int,
) -> pd.DataFrame:
    """Append trailing rolling features for each (base, source-column) pair.

    Produces ``<base>_<rm|rs|sl><window>`` (mean, std, trend slope), each
    computed within engines only. ``source_by_base`` maps the target feature
    base name (typically the sensor id) to the column to roll (typically that
    sensor's regime-normalized level column). The input must be engine-ordered
    (the canonical order of :func:`sort_by_engine`); never mutates the input.
    """
    if window < 2:
        raise ValueError(f"rolling window must be >= 2, got {window}")
    validate_engine_frame(frame)  # otherwise a reversed frame rolls silently wrong
    result = frame.copy()
    segments = engine_segments(result[ENGINE_COLUMN])

    for base, column in source_by_base.items():
        values = result[column].to_numpy(dtype=float)
        means = np.full(values.size, np.nan)
        stds = np.full(values.size, np.nan)
        slopes = np.zeros(values.size)
        for start, end in segments:
            chunk = values[start:end]
            means[start:end] = history_mean(chunk, window)
            stds[start:end] = history_std(chunk, window)
            slopes[start:end] = history_slope(chunk, window)
        if np.isnan(means).any():
            raise ValueError("rolling features produced NaNs - is the frame engine-ordered?")
        result[f"{base}_{ROLLING_MEAN_PREFIX}{window}"] = means
        result[f"{base}_{ROLLING_STD_PREFIX}{window}"] = stds
        result[f"{base}_{SLOPE_PREFIX}{window}"] = slopes
    return result
