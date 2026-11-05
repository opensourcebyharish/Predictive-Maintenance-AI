"""Phase 2.3: RandomForest baseline for within-horizon failure prediction.

The classifier answers one question per engine-cycle: *"will this engine fail
within ``failure_horizon`` cycles (default 30)?"* Labels are the configurable
``failure_within_<h>`` columns produced by the Phase 2.1 pipeline; rows are
engine-grain data and must never be row-shuffled across engines.

Training receives *whole engine trajectories*, from the engine-level splits
(``preprocessing.splits`` via :mod:`predictive_maintenance.models.datasets`);
the official NASA test engines are consumed only by the evaluation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from predictive_maintenance.preprocessing.features import failure_label_column


@dataclass(frozen=True)
class ForestConfig:
    """Hyper-parameters of the RF baseline (kept intentionally small)."""

    n_estimators: int = 300
    max_depth: int | None = None
    min_samples_leaf: int = 2
    class_weight: str | dict[str, int] | None = "balanced"
    random_state: int = 42
    n_jobs: int = -1

    def __post_init__(self) -> None:
        if self.n_estimators < 1:
            raise ValueError(f"n_estimators must be >= 1, got {self.n_estimators}")
        if self.min_samples_leaf < 1:
            raise ValueError(f"min_samples_leaf must be >= 1, got {self.min_samples_leaf}")


class ForestFailureClassifier:
    """RandomForestClassifier wrapper with a stable metadata contract."""

    name: ClassVar[str] = "random_forest"

    def __init__(
        self,
        config: ForestConfig | None = None,
        horizon: int = 30,
        feature_columns: list[str] | None = None,
    ) -> None:
        self.config = config or ForestConfig()
        self.horizon = int(horizon)
        self.feature_columns = list(feature_columns) if feature_columns is not None else None
        self.model_: RandomForestClassifier | None = None
        self.n_train_rows_: int = 0
        self.class_counts_: dict[int, int] | None = None

    # ------------------------------------------------------------------ fit

    def _label(self, frame: pd.DataFrame) -> pd.Series:
        return frame[failure_label_column(self.horizon)]

    def fit(self, frame: pd.DataFrame) -> "ForestFailureClassifier":
        """Fit on whole-engine training rows (labels from the horizon column)."""
        label = failure_label_column(self.horizon)
        if label not in frame.columns:
            raise ValueError(f"training frame lacks the failure label '{label}'")
        counts = self._label(frame).value_counts().to_dict()
        missing = {0, 1} - set(counts)
        if missing:
            raise ValueError(f"training labels must contain both classes; missing {sorted(missing)}")
        counts_int = {int(key): int(value) for key, value in sorted(counts.items())}
        self.class_counts_ = counts_int

        if self.feature_columns is None:
            from predictive_maintenance.models.datasets import select_feature_columns

            self.feature_columns = [
                column
                for column in select_feature_columns(frame, label)
                if not column.startswith("failure_within_")
            ]
        matrix = self._matrix(frame)
        self.model_ = RandomForestClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            min_samples_leaf=self.config.min_samples_leaf,
            class_weight=self.config.class_weight,
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
        ).fit(matrix, self._label(frame).to_numpy())
        self.n_train_rows_ = int(len(frame))
        return self

    # ------------------------------------------------------------ inference

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Binary failure predictions (1 = fails within horizon)."""
        return (self.predict_proba(frame)[:, 1] >= 0.5).astype(np.int64)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Class probabilities, columns ordered ``[healthy, failure]``."""
        self._check_fitted()
        matrix = self._matrix(frame)
        return self.model_.predict_proba(matrix)

    def feature_importances(self) -> pd.Series:
        """Impurity importances aligned to ``feature_columns`` (descending)."""
        self._check_fitted()
        return pd.Series(self.model_.feature_importances_, index=list(self.feature_columns)).sort_values(
            ascending=False
        )

    # ------------------------------------------------------------- metadata

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        return frame[self.feature_columns].to_numpy(dtype=float)

    def _check_fitted(self) -> None:
        if self.model_ is None or self.feature_columns is None:
            raise RuntimeError("ForestFailureClassifier is not fitted; call fit() first")

    def check_fitted(self) -> None:
        self._check_fitted()

    def describe(self) -> dict[str, Any]:
        """Manifest-ready summary of the fitted classifier."""
        self._check_fitted()
        return {
            "model_type": self.name,
            "config": {name: getattr(self.config, name) for name in self.config.__dataclass_fields__},  # type: ignore[attr-defined]
            "failure_horizon": self.horizon,
            "feature_columns": list(self.feature_columns),
            "n_train_rows": self.n_train_rows_,
            "class_counts": self.class_counts_,
            "label_definition": f"failure_within_{self.horizon}: engine fails within {self.horizon} cycles (uncapped truth)",
        }
