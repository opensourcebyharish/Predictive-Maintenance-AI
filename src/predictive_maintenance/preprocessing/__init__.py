"""Phase 2.1: ML preprocessing and feature engineering for C-MAPSS."""

from predictive_maintenance.preprocessing.features import (
    add_rolling_features,
    add_targets,
    engine_segments,
    feature_column_names,
    history_mean,
    history_slope,
    history_std,
    remaining_cycles,
    sort_by_engine,
)
from predictive_maintenance.preprocessing.pipeline import (
    PreprocessingConfig,
    PreprocessingPipeline,
)
from predictive_maintenance.preprocessing.regimes import RegimeEncoder
from predictive_maintenance.preprocessing.splits import engine_group_split
from predictive_maintenance.preprocessing.validation import (
    validate_cmapss_dataset,
    validate_engine_frame,
)

__all__ = [
    "PreprocessingConfig",
    "PreprocessingPipeline",
    "RegimeEncoder",
    "add_rolling_features",
    "add_targets",
    "engine_group_split",
    "engine_segments",
    "feature_column_names",
    "history_mean",
    "history_slope",
    "history_std",
    "remaining_cycles",
    "sort_by_engine",
    "validate_cmapss_dataset",
    "validate_engine_frame",
]
