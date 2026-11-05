"""Operating-regime encoding for the three operational settings.

C-MAPSS simulates distinct flight conditions by appointment: ``setting_1``
(altitude) visits the centers {0, 10, 20, 25, 35, 42} and ``setting_2``
(Mach number) the centers {0, 0.25, 0.62, 0.7, 0.84}, both contaminated with
small noise (|delta| < 0.005 in the files; setting_3/TRA is a constant 100).

Raw floating settings therefore cannot be used as categorical keys, and naive
rounding splits single regimes at the noise floor (the EDA showed this). The
encoder learns the actual center values from the *training* rows only (values
within ``tolerance`` of each other collapse to one center), then assigns any
row to its nearest learned center-pair. Unseen combinations fall back to the
nearest known regime instead of erroring out, keeping serving robust.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from predictive_maintenance.data.cmapss import OP_SETTING_COLUMNS

ALTITUDE_COLUMN = OP_SETTING_COLUMNS[0]
MACH_COLUMN = OP_SETTING_COLUMNS[1]


def _learn_centers(values: np.ndarray, tolerance: float) -> np.ndarray:
    """Cluster sorted unique values: each gap > tolerance starts a new center."""
    if tolerance <= 0.0:
        raise ValueError(f"tolerance must be > 0, got {tolerance}")
    uniques = np.unique(np.round(values, 4))
    if uniques.size == 0:
        return np.array([], dtype=float)
    centers: list[float] = [float(uniques[0])]
    for value in uniques[1:]:
        if value - centers[-1] > tolerance:
            centers.append(float(value))
    return np.array(centers)


def _assign(values: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Index of the nearest center per value (monotone centers -> bin search)."""
    if centers.size == 0:
        raise ValueError("no regime centers learned")
    position = np.searchsorted(centers, values)
    left = np.clip(position - 1, 0, centers.size - 1)
    right = np.clip(position, 0, centers.size - 1)
    take_left = np.abs(values - centers[left]) <= np.abs(centers[right] - values)
    return np.where(take_left, left, right).astype(np.int64)


def feature_span(centers: np.ndarray) -> float:
    """Span of a center axis (for scale-free nearest-pair distances)."""
    return float(centers.max() - centers.min()) or 1.0


@dataclass(frozen=True)
class RegimeEncoder:
    """Learns the discrete operating regimes behind the setting columns.

    ``condition_id`` is the integer index of the (altitude, Mach) center pair -
    the categorical key the level normalizer conditions on. A single-regime
    subset (FD001/FD003) degenerates to ``condition_id == 0`` everywhere.
    """

    altitude_tolerance: float = 2.0
    mach_tolerance: float = 0.02
    altitude_centers: np.ndarray | None = None
    mach_centers: np.ndarray | None = None
    pairs: tuple[tuple[float, float], ...] | None = None

    def fit(self, frame: pd.DataFrame) -> "RegimeEncoder":
        """Learn centers/center-pairs from the training frame only."""
        altitude_values = frame[ALTITUDE_COLUMN].to_numpy(dtype=float)
        mach_values = frame[MACH_COLUMN].to_numpy(dtype=float)
        altitude = _learn_centers(altitude_values, self.altitude_tolerance)
        mach = _learn_centers(mach_values, self.mach_tolerance)
        altitude_codes = _assign(altitude_values, altitude)
        mach_codes = _assign(mach_values, mach)
        uniq = sorted({(int(a), int(m)) for a, m in zip(altitude_codes, mach_codes)})
        pairs = tuple((float(altitude[a]), float(mach[m])) for a, m in uniq)
        return RegimeEncoder(
            altitude_tolerance=self.altitude_tolerance,
            mach_tolerance=self.mach_tolerance,
            altitude_centers=altitude,
            mach_centers=mach,
            pairs=pairs,
        )

    def check_fitted(self) -> None:
        """Raise when :meth:`fit` has not produced centers yet."""
        if self.pairs is None or self.altitude_centers is None or self.mach_centers is None:
            raise RuntimeError("RegimeEncoder is not fitted; call fit() on training data first")

    def transform(self, frame: pd.DataFrame) -> pd.Series:
        """Integer ``condition_id`` per row (nearest learned pair, deterministic).

        Rows whose exact (altitude, Mach) pair never occurred in training are
        mapped to the nearest learned pair, so transform keeps working when the
        test split - or the future serving layer - produces a value blend.
        """
        self.check_fitted()
        altitude = self.altitude_centers
        mach = self.mach_centers
        known = {pair: code for code, pair in enumerate(self.pairs)}

        altitude_codes = _assign(frame[ALTITUDE_COLUMN].to_numpy(dtype=float), altitude)
        mach_codes = _assign(frame[MACH_COLUMN].to_numpy(dtype=float), mach)
        conditions = np.empty(len(frame), dtype=np.int64)
        altitude_scale = feature_span(altitude)
        mach_scale = feature_span(mach)
        altitude_values = frame[ALTITUDE_COLUMN].to_numpy(dtype=float)
        mach_values = frame[MACH_COLUMN].to_numpy(dtype=float)

        for row, (a_code, m_code) in enumerate(zip(altitude_codes, mach_codes)):
            code = known.get((int(a_code), int(m_code)), -1)
            if code >= 0:
                conditions[row] = code
                continue
            pair_values = np.array(self.pairs, dtype=float)
            distance = (altitude_values[row] - pair_values[:, 0]) / altitude_scale
            distance = distance**2 + ((mach_values[row] - pair_values[:, 1]) / mach_scale) ** 2
            conditions[row] = int(np.argmin(distance))  # ties break to the lower code
        return pd.Series(conditions, index=frame.index, name="condition_id")

    def describe(self) -> dict[str, object]:
        """Human-readable regime summary for manifests/logs."""
        self.check_fitted()
        return {
            "altitude_centers": self.altitude_centers.tolist(),
            "mach_centers": self.mach_centers.tolist(),
            "n_regimes": len(self.pairs),
            "pairs": [list(pair) for pair in self.pairs],
        }
