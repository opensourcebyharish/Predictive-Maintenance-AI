"""Shared fit-and-persist helpers for Phase 2.2-2.4 model training.

Both the CLI scripts (force retrain) and the Phase 2.5 evaluation layer
(load-or-train) route through this module so training behaviour, artifact
names and manifest contents stay consistent across the project.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from predictive_maintenance import config
from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
from predictive_maintenance.models.boost import BoostConfig, BoostFailureClassifier
from predictive_maintenance.models.datasets import (
    ENGINE_SPLIT_SEED,
    ablate_features,
    dataset_version,
    load_split,
    select_feature_columns,
)
from predictive_maintenance.models.evaluation import (
    DEFAULT_THRESHOLD,
    anomaly_metrics,
    classification_metrics,
)
from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier
from predictive_maintenance.models.persistence import (
    environment_versions,
    load_artifact,
    read_manifest,
    save_artifact,
    write_manifest,
)

DETECTOR_NAME: str = "isolation_forest"
FOREST_NAME: str = "random_forest"
BOOST_NAME: str = "xgboost"
ABLATION_SUFFIX: str = "_no_s10_s16"

VALID_KINDS: tuple[str, ...] = (DETECTOR_NAME, FOREST_NAME, BOOST_NAME)


def model_name(kind: str, ablated: bool = False) -> str:
    """Artifact name; ablated variants carry the sensor suffix."""
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown model kind '{kind}', expected one of {VALID_KINDS}")
    return f"{kind}{ABLATION_SUFFIX}" if ablated else kind


def ablation_applies(dataset_id: str) -> bool:
    """The s10/s16 comparison is specified for the six-regime subsets."""
    return dataset_id in {"FD002", "FD004"}


def feature_columns_for(frame: pd.DataFrame, horizon: int, ablated: bool) -> list[str]:
    """Model matrix columns; ablation drops the s10/s16 derived features."""
    columns = [
        column
        for column in select_feature_columns(frame, f"failure_within_{horizon}")
        if not column.startswith("failure_within_")
    ]
    if ablated:
        columns = ablate_features(columns, ["s10", "s16"])
    return columns


def _pipeline_feature_config(dataset_id: str) -> dict[str, Any]:
    """Snapshot of the Phase 2.1 preprocessing recipe backing the features."""
    manifest_path = config.PROCESSED_DATA_DIR / f"manifest_{dataset_id}.json"
    if not manifest_path.is_file():
        return {"note": "Phase 2.1 manifest missing; defaults assumed"}
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "pipeline_config": manifest.get("config", {}),
        "pipeline_dropped_sensors": manifest.get("dropped_sensors", []),
        "pipeline_regimes": manifest.get("regimes", {}),
    }


def _validation_metrics(
    kind: str,
    model: Any,
    val_frame: pd.DataFrame,
    horizon: int,
    threshold: float,
) -> dict[str, Any]:
    """Metrics on the held-out validation engines (model selection input)."""
    label = f"failure_within_{horizon}"
    y_true = val_frame[label].to_numpy()
    if kind == DETECTOR_NAME:
        y_score = model.score(val_frame)
        y_pred = model.predict(val_frame)
        return anomaly_metrics(y_true, y_score, y_pred, frame=val_frame)
    y_score = model.predict_proba(val_frame)[:, 1]
    return classification_metrics(y_true, y_score, threshold=threshold)


def train(
    kind: str,
    train_frame: pd.DataFrame,
    val_frame: pd.DataFrame,
    *,
    horizon: int = 30,
    ablated: bool = False,
    seed: int = ENGINE_SPLIT_SEED,
    n_estimators: int | None = None,
    contamination: float | None = None,
    healthy_rul_min: int | None = None,
) -> Any:
    """Fit one model from scratch on the training engines only."""
    feature_columns = feature_columns_for(train_frame, horizon, ablated)
    if kind == DETECTOR_NAME:
        detector_config = AnomalyConfig(
            random_state=seed,
            n_estimators=n_estimators if n_estimators is not None else AnomalyConfig.n_estimators,
            contamination=contamination if contamination is not None else AnomalyConfig.contamination,
            healthy_rul_min=healthy_rul_min if healthy_rul_min is not None else AnomalyConfig.healthy_rul_min,
        )
        return IsolationForestDetector(detector_config, feature_columns).fit(train_frame)
    if kind == FOREST_NAME:
        forest_config = ForestConfig(random_state=seed, n_estimators=n_estimators if n_estimators else ForestConfig.n_estimators)
        return ForestFailureClassifier(forest_config, horizon=horizon, feature_columns=feature_columns).fit(train_frame)
    if kind == BOOST_NAME:
        boost_config = BoostConfig(random_state=seed, n_estimators=n_estimators if n_estimators else BoostConfig.n_estimators)
        return BoostFailureClassifier(boost_config, horizon=horizon, feature_columns=feature_columns).fit(
            train_frame,
            eval_frame=val_frame,
        )
    raise ValueError(f"unknown model kind '{kind}'")


def load_or_train(
    dataset_id: str,
    kind: str,
    *,
    horizon: int = 30,
    ablated: bool = False,
    seed: int = ENGINE_SPLIT_SEED,
    force: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[Any, dict[str, Any]]:
    """Artifact-backed accessor: load when consistent, train+persist otherwise.

    Loaded classifiers must match the requested ``horizon`` (recorded in their
    manifest); otherwise they are retrained so evaluation can not operate on a
    stale label definition.
    """
    name = model_name(kind, ablated)
    if not force:
        try:
            existing_manifest = read_manifest(dataset_id, name)
            artifact = load_artifact(dataset_id, name)
            if kind != DETECTOR_NAME and existing_manifest.get("failure_horizon") != horizon:
                raise RuntimeError("horizon mismatch - retraining")
            val_metrics = existing_manifest.get("validation_metrics")
            if isinstance(val_metrics, dict) and val_metrics:
                return artifact, val_metrics
        except (FileNotFoundError, RuntimeError, KeyError):
            pass
    train_frame = load_split(dataset_id, "train")
    val_frame = load_split(dataset_id, "val")
    model = train(kind, train_frame, val_frame, horizon=horizon, ablated=ablated, seed=seed)
    val_metrics = _validation_metrics(kind, model, val_frame, horizon, threshold)
    save_artifact(model, dataset_id, name)
    manifest = {
        **model.describe(),
        "dataset_id": dataset_id,
        "artifact": name,
        "dataset_version": dataset_version(dataset_id),
        "feature_config": _pipeline_feature_config(dataset_id),
        "feature_ablation": {"sensors": ["s10", "s16"]} if ablated else None,
        "split_seed": seed,
        "validation_metrics": val_metrics,
        "environment": environment_versions(),
        "caveat": (
            "C-MAPSS degradation is simulated: 'failure' is the end of a run-out "
            "trajectory, not a discrete physical event."
        ),
    }
    write_manifest(manifest, dataset_id, name)
    return model, val_metrics
