"""Phase 2.4: XGBoost failure classifier over the identical feature matrix.

Uses exactly the same splits, feature columns and ``failure_within_<h>``
labels as the Random Forest (Phase 2.3) so their comparison in Phase 2.5 is
apples-to-apples. Differences are: gradient-boosted trees, early stopping
against a *validation-engine* eval set (never the official test engines), and
imbalance handling via ``scale_pos_weight`` (auto = ``n_negatives /
n_positives`` of the training labels, configurable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from predictive_maintenance.preprocessing.features import failure_label_column


@dataclass(frozen=True)
class BoostConfig:
    """XGBoost hyper-parameters; ``scale_pos_weight=None`` -> auto imbalance."""

    n_estimators: int = 400
    learning_rate: float = 0.05
    max_depth: int = 6
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 5
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 50
    scale_pos_weight: float | None = None
    random_state: int = 42
    n_jobs: int = -1

    def __post_init__(self) -> None:
        if self.n_estimators < 1:
            raise ValueError(f"n_estimators must be >= 1, got {self.n_estimators}")
        if not 0.0 < self.learning_rate <= 1.0:
            raise ValueError(f"learning_rate must be in (0, 1], got {self.learning_rate}")
        if self.early_stopping_rounds < 1:
            raise ValueError(f"early_stopping_rounds must be >= 1, got {self.early_stopping_rounds}")
        if self.scale_pos_weight is not None and self.scale_pos_weight <= 0:
            raise ValueError("scale_pos_weight must be positive when given")


class BoostFailureClassifier:
    """XGBClassifier wrapper with early stopping and manifest metadata."""

    name: ClassVar[str] = "xgboost"

    def __init__(
        self,
        config: BoostConfig | None = None,
        horizon: int = 30,
        feature_columns: list[str] | None = None,
    ) -> None:
        self.config = config or BoostConfig()
        self.horizon = int(horizon)
        self.feature_columns = list(feature_columns) if feature_columns is not None else None
        self.model_: XGBClassifier | None = None
        self.n_train_rows_: int = 0
        self.class_counts_: dict[int, int] | None = None
        self.best_iteration_: int | None = None
        self.eval_engine_count_: int | None = None

    # ------------------------------------------------------------------ fit

    def fit(self, frame: pd.DataFrame, eval_frame: pd.DataFrame | None = None) -> "BoostFailureClassifier":
        """Fit on training engines; early-stop against ``eval_frame`` rows.

        ``eval_frame`` must come from the held-out *validation engines* - never
        from the official test split (that would leak model selection into the
        final measurement).
        """
        label = failure_label_column(self.horizon)
        if label not in frame.columns:
            raise ValueError(f"training frame lacks the failure label '{label}'")
        y = frame[label].to_numpy()
        counts = pd.Series(y).value_counts().to_dict()
        missing = {0, 1} - set(counts)
        if missing:
            raise ValueError(f"training labels must contain both classes; missing {sorted(missing)}")
        self.class_counts_ = {int(key): int(value) for key, value in sorted(counts.items())}
        scale_pos_weight = (
            self.config.scale_pos_weight
            if self.config.scale_pos_weight is not None
            else counts.get(0, 0) / counts.get(1, 1)
        )

        if self.feature_columns is None:
            from predictive_maintenance.models.datasets import select_feature_columns

            self.feature_columns = [
                column
                for column in select_feature_columns(frame, label)
                if not column.startswith("failure_within_")
            ]
        matrix = self._matrix(frame)
        eval_set = None
        if eval_frame is not None:
            if eval_frame.empty:
                raise ValueError("empty eval_frame: drop early stopping or provide validation rows")
            eval_set = [
                (
                    self._matrix(eval_frame),
                    eval_frame[label].to_numpy(),
                )
            ]
            self.eval_engine_count_ = int(eval_frame["unit"].nunique())

        self.model_ = XGBClassifier(
            n_estimators=self.config.n_estimators,
            learning_rate=self.config.learning_rate,
            max_depth=self.config.max_depth,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            min_child_weight=self.config.min_child_weight,
            reg_lambda=self.config.reg_lambda,
            scale_pos_weight=scale_pos_weight,
            eval_metric="logloss",
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
            tree_method="hist",
            verbosity=0,
            **(
                {"early_stopping_rounds": self.config.early_stopping_rounds}
                if eval_set is not None
                else {}
            ),
        ).fit(matrix, y, eval_set=eval_set, verbose=False)
        best = self.model_.best_iteration if getattr(self.model_, "best_iteration", None) is not None else None
        self.best_iteration_ = int(best) if best is not None else int(self.config.n_estimators - 1)
        self.n_train_rows_ = int(len(frame))
        return self

    # ------------------------------------------------------------ inference

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Binary failure predictions (1 = fails within horizon)."""
        return (self.predict_proba(frame)[:, 1] >= 0.5).astype(np.int64)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Class probabilities, columns ordered ``[healthy, failure]``."""
        self._check_fitted()
        return self.model_.predict_proba(self._matrix(frame))  # type: ignore[union-attr]

    def feature_importances(self) -> pd.Series:
        """Gain importances aligned to ``feature_columns`` (descending)."""
        self._check_fitted()
        importances = self.model_.feature_importances_  # type: ignore[union-attr]
        return pd.Series(importances, index=list(self.feature_columns)).sort_values(ascending=False)

    # ------------------------------------------------------------- metadata

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        return frame[self.feature_columns].to_numpy(dtype=float)

    def _check_fitted(self) -> None:
        if self.model_ is None or self.feature_columns is None:
            raise RuntimeError("BoostFailureClassifier is not fitted; call fit() first")

    def check_fitted(self) -> None:
        self._check_fitted()

    def describe(self) -> dict[str, Any]:
        """Manifest-ready summary of the fitted booster."""
        self._check_fitted()
        return {
            "model_type": self.name,
            "config": {name: getattr(self.config, name) for name in self.config.__dataclass_fields__},  # type: ignore[attr-defined]
            "failure_horizon": self.horizon,
            "feature_columns": list(self.feature_columns),
            "n_train_rows": self.n_train_rows_,
            "class_counts": self.class_counts_,
            "early_stopping": {
                "rounds": self.config.early_stopping_rounds,
                "best_iteration": self.best_iteration_,
                "eval_engines": self.eval_engine_count_,
                "note": "eval set = held-out validation engines; official test engines were never used for fitting",
            },
            "label_definition": f"failure_within_{self.horizon}: engine fails within {self.horizon} cycles (uncapped truth)",
        }
