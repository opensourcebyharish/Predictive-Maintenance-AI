"""Configurable, leak-safe preprocessing pipeline (Phase 2.1).

Contract
--------
``fit`` may look at *anything* in the training frame (its rows belong to whole
engines in the training split). ``transform`` must work on any subset of rows -
engines held out by the engine split, or single readings from the later serving
layer - using only statistics learned at fit time plus each engine's own past
(trailing windows). Refitting on the same frame reproduces the identical state;
transform output (schema + values) is deterministic.

Stage order (identical in fit and transform so both produce the same schema):

1. validate + canonical (``unit``, ``cycle``) row order + target attachment
2. operating-regime encoding (:class:`RegimeEncoder`, learned on train)
3. missing-value repair: NaN sensors -> forward-fill within the engine, then
   the train-time per-regime median (never a future or cross-engine value)
4. per-regime level normalization of each sensor (z-score conditioned on
   ``condition_id``; regimes unseen in training fall back to train-global stats)
5. sensors the *training* data declared constant are dropped
6. trailing rolling features on the normalized level (mean / std / trend slope)
7. global standardization of all derived features (train mean/std)

A fitted pipeline is a small picklable object. Raw sensor columns are inputs
only: the output schema carries their regime-normalized level and history
features, from which the raw column is recoverable via the fit statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS, SENSOR_COLUMNS
from predictive_maintenance.preprocessing.features import (
    LEVEL_SUFFIX,
    RUL_RAW_COLUMN,
    TARGET_COLUMN,
    add_rolling_features,
    add_targets,
    engine_segments,
    feature_column_names,
    failure_label_column,
    sort_by_engine,
)
from predictive_maintenance.preprocessing.regimes import RegimeEncoder
from predictive_maintenance.preprocessing.validation import validate_engine_frame

MIN_LEVEL_STD = 1e-6  # guards zero-variance regimes at level normalization
MIN_FEATURE_STD = 1e-9  # guards zero-variance features at standardization


def _finite(value: float, fallback: float) -> float:
    """Coerce NaN/inf statistics (e.g. a fully-missing sensor) to a fallback."""
    value = float(value)
    return value if np.isfinite(value) else fallback


@dataclass(frozen=True)
class PreprocessingConfig:
    """All knobs of the Phase 2.1 feature build (defaults = literature standard)."""

    rolling_window: int = 5
    rul_cap: int | None = 130
    failure_horizon: int = 30
    drop_constant_sensors: bool = True
    constant_tolerance: float = 1e-6
    condition_normalization: bool = True
    altitude_tolerance: float = 2.0
    mach_tolerance: float = 0.02

    def __post_init__(self) -> None:
        if self.rolling_window < 2:
            raise ValueError(f"rolling_window must be >= 2, got {self.rolling_window}")
        if self.failure_horizon < 1:
            raise ValueError(f"failure_horizon must be >= 1, got {self.failure_horizon}")
        if self.rul_cap is not None and self.failure_horizon > self.rul_cap:
            raise ValueError(
                f"failure_horizon {self.failure_horizon} must not exceed rul_cap {self.rul_cap} "
                "- failure labels would be censored beyond the cap"
            )
        if self.constant_tolerance < 0:
            raise ValueError("constant_tolerance must be non-negative")


@dataclass
class PreprocessingPipeline:
    """Fit/transform feature builder; fitted state is plain Python + Series."""

    config: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    sensor_columns: list[str] = field(default_factory=list)
    feature_columns: list[str] = field(default_factory=list)
    regimes: RegimeEncoder | None = None
    level_mean: dict[tuple[int, str], float] = field(default_factory=dict)
    level_std: dict[tuple[int, str], float] = field(default_factory=dict)
    impute_median: dict[tuple[int, str], float] = field(default_factory=dict)
    global_mean: dict[str, float] = field(default_factory=dict)
    global_std: dict[str, float] = field(default_factory=dict)
    global_median: dict[str, float] = field(default_factory=dict)
    dropped_sensors: list[str] = field(default_factory=list)
    feature_mean: pd.Series | None = None
    feature_std: pd.Series | None = None

    # ------------------------------------------------------------- public

    def fit(self, frame: pd.DataFrame) -> "PreprocessingPipeline":
        """Learn every statistic from training rows only; returns ``self``."""
        if frame.empty:
            raise ValueError("cannot fit on an empty frame")
        config = self.config
        prepared = self._prepare(frame)
        sensors = [column for column in SENSOR_COLUMNS if column in prepared.columns]
        if not sensors:
            raise ValueError("no C-MAPSS sensor columns found in the frame")
        self.sensor_columns = sensors

        self.regimes = RegimeEncoder(
            altitude_tolerance=config.altitude_tolerance,
            mach_tolerance=config.mach_tolerance,
        ).fit(prepared)
        conditions = self.regimes.transform(prepared).to_numpy()
        self._learn_statistics(prepared, conditions)
        self.dropped_sensors = self._constant_sensors(prepared, conditions)
        self.feature_columns = feature_column_names(self._kept_sensors(), config.rolling_window)
        if not self.feature_columns:
            raise ValueError("every sensor was constant on the training data; nothing would remain")

        engineered = self._engineer(prepared, conditions)
        numeric = engineered[self.feature_columns].astype(float)
        if numeric.isna().any().any():
            raise RuntimeError("feature engineering produced missing values on training data")
        self.feature_mean = numeric.mean()
        self.feature_std = numeric.std(ddof=0).clip(lower=MIN_FEATURE_STD)
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Engineered frame for any subset of engine rows (train or new data)."""
        self.check_fitted()
        if frame.empty:
            return self._empty_output()
        prepared = self._prepare(frame)
        conditions = self.regimes.transform(prepared).to_numpy()
        result = self._engineer(prepared, conditions)
        numeric = result[self.feature_columns].astype(float)
        result[self.feature_columns] = (numeric - self.feature_mean) / self.feature_std
        return self._ordered(result)

    def fit_transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """fit + transform in one call (training-data convenience)."""
        return self.fit(frame).transform(frame)

    def check_fitted(self) -> None:
        """Raise when the pipeline has never completed :meth:`fit`."""
        if self.regimes is None or self.feature_mean is None:
            raise RuntimeError("PreprocessingPipeline is not fitted; call fit() first")

    def describe(self) -> dict[str, object]:
        """Manifest-ready summary of the fitted state."""
        self.check_fitted()
        return {
            "config": {
                name: getattr(self.config, name) for name in self.config.__dataclass_fields__  # type: ignore[attr-defined]
            },
            "sensors": list(self.sensor_columns),
            "dropped_sensors": list(self.dropped_sensors),
            "n_features": len(self.feature_columns),
            "regimes": self.regimes.describe(),
        }

    # --------------------------------------------------------- internals

    def _prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Validate, order canonically, attach prediction targets."""
        return add_targets(
            sort_by_engine(validate_engine_frame(frame)),
            rul_cap=self.config.rul_cap,
            horizon=self.config.failure_horizon,
        )

    def _kept_sensors(self) -> list[str]:
        return [sensor for sensor in self.sensor_columns if sensor not in self.dropped_sensors]

    def _learn_statistics(self, prepared: pd.DataFrame, conditions: np.ndarray) -> None:
        """Train-only sensor statistics: imputation medians + level moments."""
        sensors = self.sensor_columns
        raw = prepared[sensors]
        for sensor in sensors:
            observed = raw[sensor].dropna()
            self.global_median[sensor] = _finite(observed.median(), 0.0)
            self.global_mean[sensor] = _finite(observed.mean(), 0.0)
            self.global_std[sensor] = max(_finite(observed.std(ddof=0), 0.0), MIN_LEVEL_STD)
        if not self.config.condition_normalization:
            return
        per_condition = raw.groupby(pd.Series(conditions, index=prepared.index), sort=True)
        for condition, rows in per_condition:
            code = int(condition)
            for sensor in sensors:
                observed = rows[sensor].dropna()
                self.impute_median[(code, sensor)] = _finite(observed.median(), self.global_median[sensor])
                self.level_mean[(code, sensor)] = _finite(observed.mean(), self.global_mean[sensor])
                self.level_std[(code, sensor)] = max(
                    _finite(observed.std(ddof=0), 0.0),
                    MIN_LEVEL_STD,
                )

    def _constant_sensors(self, prepared: pd.DataFrame, conditions: np.ndarray) -> list[str]:
        """Sensors whose *post-normalization* train level is constant.

        Both sources of constancy are handled: a sensor that never varies
        within a regime, and one that varies only across regimes (its
        normalized level is a dead zero column either way). Measured after the
        level stage, on training rows only.
        """
        tolerance = self.config.constant_tolerance
        if not self.config.condition_normalization:
            return [
                sensor
                for sensor in self.sensor_columns
                if self.global_std[sensor] <= tolerance
            ]
        dropped: list[str] = []
        for sensor in self.sensor_columns:
            means, stds = self._regime_arrays(sensor, conditions)
            normalized = prepared[sensor].to_numpy(dtype=float) - means
            normalized /= stds
            if float(np.nanstd(normalized, ddof=0)) <= tolerance:
                dropped.append(sensor)
        return dropped

    def _level_stats(self, sensor: str, code: int) -> tuple[float, float]:
        """(mean, std) for one sensor under one regime code, global fallback."""
        if self.config.condition_normalization:
            mean = self.level_mean.get((code, sensor))
            if mean is not None:
                return mean, self.level_std[(code, sensor)]
        return self.global_mean[sensor], self.global_std[sensor]

    def _impute_median_for(self, sensor: str, code: int) -> float:
        """Train-time median of a sensor inside a regime (global fallback)."""
        if self.config.condition_normalization:
            median = self.impute_median.get((code, sensor))
            if median is not None:
                return median
        return self.global_median[sensor]

    def _regime_arrays(self, sensor: str, conditions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Per-row (mean, std) vectors for one sensor under its regime coding."""
        means = np.empty(conditions.size)
        stds = np.empty(conditions.size)
        for code in np.unique(conditions):
            mask = conditions == code
            means[mask], stds[mask] = self._level_stats(sensor, int(code))
        return means, stds

    def _engineer(self, prepared: pd.DataFrame, conditions: np.ndarray) -> pd.DataFrame:
        """Stages 3-6 on an ordered frame (used identically by fit/transform)."""
        sensors = self.sensor_columns
        kept = self._kept_sensors()
        result = prepared.copy()
        result["condition_id"] = conditions

        # stage 3: imputation
        imputed = _impute_matrix(result[sensors], result["unit"], conditions, self)
        position = {sensor: index for index, sensor in enumerate(sensors)}

        # stage 4: regime-conditional level normalization (kept sensors only)
        for sensor in kept:
            means, stds = self._regime_arrays(sensor, conditions)
            result[f"{sensor}_{LEVEL_SUFFIX}"] = (imputed[:, position[sensor]] - means) / stds

        # stage 6: trailing rolling features on the normalized level columns
        level_sources = {sensor: f"{sensor}_{LEVEL_SUFFIX}" for sensor in kept}
        result = add_rolling_features(result, level_sources, self.config.rolling_window)
        # raw sensor columns were draft inputs; they are not part of the schema
        return result.drop(columns=[column for column in sensors if column in result.columns])

    def _ordered(self, result: pd.DataFrame) -> pd.DataFrame:
        """Deterministic output schema: keys, settings, targets, then features."""
        head = [
            "unit",
            "cycle",
            "condition_id",
            *OP_SETTING_COLUMNS,
            RUL_RAW_COLUMN,
            TARGET_COLUMN,
            failure_label_column(self.config.failure_horizon),
        ]
        head = [column for column in head if column in result.columns]
        tail = [column for column in result.columns if column not in head]
        return result[head + tail]

    def _empty_output(self) -> pd.DataFrame:
        """Schema-correct DataFrame for an empty input frame."""
        head = ["unit", "cycle", "condition_id", *OP_SETTING_COLUMNS]
        targets = [RUL_RAW_COLUMN, TARGET_COLUMN, failure_label_column(self.config.failure_horizon)]
        return pd.DataFrame({column: [] for column in [*head, *targets, *self.feature_columns]})


def _impute_matrix(
    values: pd.DataFrame,
    engine_ids: pd.Series,
    conditions: np.ndarray,
    state: "PreprocessingPipeline",
) -> np.ndarray:
    """Missing-value repair: forward-fill inside engines, then train medians.

    Imputations originate only from the same engine's past rows (forward fill)
    or from training-set medians - never future rows or foreign engines.
    """
    matrix = values.to_numpy(dtype=float, copy=True)
    sensor_columns = state.sensor_columns
    bounds = engine_segments(engine_ids)
    for sensor_index, sensor in enumerate(sensor_columns):
        column = matrix[:, sensor_index]
        for start, end in bounds:
            if end - start > 1 and np.isnan(column[start:end]).any():
                column[start:end] = pd.Series(column[start:end]).ffill().to_numpy()
        missing = np.isnan(column)
        if missing.any():
            medians = np.fromiter(
                (state._impute_median_for(sensor, int(code)) for code in conditions),
                dtype=float,
                count=len(conditions),
            )
            column[missing] = medians[missing]
        matrix[:, sensor_index] = column
    return matrix
