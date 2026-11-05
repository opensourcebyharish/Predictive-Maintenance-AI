"""Phase 2.2: Isolation Forest anomaly detection on healthy-cycle baselines.

Important context (documented everywhere it matters): C-MAPSS mock-up
degradation is *simulated* - the "failure" is the end of a run-out trajectory
chosen by the dataset designers, not a discrete physical event like a bearing
crack. An "anomaly" here therefore means "degradation-consistent with signal
drift", and anomaly scores should be read as a health index rather than a
crash detector.

Design:

* The detector is fitted on *healthy* observations only - training rows whose
  remaining life is at least ``healthy_rul_min`` cycles (default 50), i.e.
  before degradation onset contaminates the nominal baseline.
* ``contamination`` and ``random_state`` are configurable; ``random_state``
  also gates every downstream shuffle, so a fixed seed reproduces everything.
* Scores are ``-decision_function`` (higher = more anomalous), which keeps the
  ROC-AUC / PR-AUC orientation aligned with a "risk score".
* Binary predictions come from the contamination-calibrated
  ``IsolationForest.predict`` (``-1`` -> anomaly) - the threshold is set at fit
  time on healthy data, never tuned on validation/test rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from predictive_maintenance.models.persistence import environment_versions


@dataclass(frozen=True)
class AnomalyConfig:
    """All knobs of the anomaly detector (defaults = sensible baselines)."""

    n_estimators: int = 300
    contamination: float = 0.05
    healthy_rul_min: int = 50  # rows with remaining life >= this are "healthy"
    random_state: int = 42
    n_jobs: int = -1

    def __post_init__(self) -> None:
        if not 0.0 < self.contamination < 0.5:
            raise ValueError(f"contamination must be in (0, 0.5), got {self.contamination}")
        if self.healthy_rul_min < 0:
            raise ValueError(f"healthy_rul_min must be non-negative, got {self.healthy_rul_min}")
        if self.n_estimators < 1:
            raise ValueError(f"n_estimators must be >= 1, got {self.n_estimators}")


class IsolationForestDetector:
    """Healthy-baseline anomaly detector with a stable fit/score contract."""

    def __init__(self, config: AnomalyConfig | None = None, feature_columns: list[str] | None = None) -> None:
        self.config = config or AnomalyConfig()
        self.feature_columns = list(feature_columns) if feature_columns is not None else None
        self.model_: IsolationForest | None = None
        self.n_healthy_: int = 0
        self.n_train_rows_: int = 0

    # ------------------------------------------------------------------ fit

    def healthy_mask(self, frame: pd.DataFrame) -> pd.Series:
        """Rows considered healthy: remaining life >= healthy_rul_min for fitting."""
        return frame["rul_raw"] >= self.config.healthy_rul_min

    def fit(self, frame: pd.DataFrame) -> "IsolationForestDetector":
        """Fit on healthy training rows only; everything else is ignored."""
        healthy = frame[self.healthy_mask(frame)]
        if healthy.empty:
            raise ValueError(
                f"no healthy rows with rul_raw >= {self.config.healthy_rul_min} to fit on"
            )
        if self.feature_columns is None:
            from predictive_maintenance.models.datasets import select_feature_columns

            self.feature_columns = [
                column
                for column in select_feature_columns(healthy, "")
                if not column.startswith("failure_within_")
            ]
        matrix = healthy[self.feature_columns].to_numpy(dtype=float)
        self.model_ = IsolationForest(
            n_estimators=self.config.n_estimators,
            contamination=self.config.contamination,
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
            max_samples="auto",
        ).fit(matrix)
        self.n_healthy_ = int(len(healthy))
        self.n_train_rows_ = int(len(frame))
        return self

    # ------------------------------------------------------------ inference

    def score(self, frame: pd.DataFrame) -> np.ndarray:
        """Anomaly score per row: higher = more anomalous."""
        self._check_fitted()
        matrix = frame[self.feature_columns].to_numpy(dtype=float)
        return -self.model_.decision_function(matrix)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Binary predictions (1 = anomaly) from the contamination threshold."""
        self._check_fitted()
        matrix = frame[self.feature_columns].to_numpy(dtype=float)
        labels = self.model_.predict(matrix)
        return (labels == -1).astype(int)

    # ------------------------------------------------------------- metadata

    def _check_fitted(self) -> None:
        if self.model_ is None:
            raise RuntimeError("IsolationForestDetector is not fitted; call fit() first")

    def check_fitted(self) -> None:  # public alias with self-describing error
        self._check_fitted()

    def describe(self) -> dict[str, Any]:
        """Manifest-ready summary of the fitted detector."""
        self._check_fitted()
        return {
            "model_type": "IsolationForestDetector",
            "config": {name: getattr(self.config, name) for name in self.config.__dataclass_fields__},  # type: ignore[attr-defined]
            "feature_columns": list(self.feature_columns),
            "fitted_on": {"healthy_rows": self.n_healthy_, "train_rows_seen": self.n_train_rows_},
            "healthy_definition": f"rul_raw >= {self.config.healthy_rul_min} (training rows only)",
            "environment": environment_versions(),
            "caveat": (
                "C-MAPSS degradation is simulated: 'failure' is the end of a run-out "
                "trajectory chosen by the dataset designers, not a discrete physical "
                "event. Anomaly scores are degradation/health indicators."
            ),
        }
