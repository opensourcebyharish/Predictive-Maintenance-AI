"""Phase 2.5: unified evaluation of anomaly detection and failure classifiers.

Metrics, plots and machine-readable reports, shared by the training scripts
(manifest sections) and ``scripts/evaluate_models.py`` (the full Phase 2.5
run). Everything operates on *engine-level, already-transformed* feature
frames; the official NASA test engines are consumed only here, for reporting,
never for model selection or fitting.

Model-selection discipline:
* models are compared with **validation** metrics only;
* the *test* numbers are produced once per run and written to the reports -
  they are never fed back into a choice of hyper-parameters or thresholds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless figure generation, no display needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from predictive_maintenance import config
from predictive_maintenance.models.anomalies import AnomalyConfig, IsolationForestDetector
from predictive_maintenance.models.boost import BoostConfig, BoostFailureClassifier
from predictive_maintenance.models.datasets import (
    ablate_features,
    dataset_version,
    load_split,
    load_test_features,
    select_feature_columns,
)
from predictive_maintenance.models.forest import ForestConfig, ForestFailureClassifier
from predictive_maintenance.models.persistence import (
    environment_versions,
    load_artifact,
    save_artifact,
    write_manifest,
)

ABLATION_SENSORS: list[str] = ["s10", "s16"]  # Phase 2.5 ablation on FD002/FD004
DEFAULT_HORIZON: int = 30
DEFAULT_THRESHOLD: float = 0.5

EVALUATION_DIR = config.REPORTS_DIR / "evaluation"
PHASE2_FIGURES_DIR = config.FIGURES_DIR / "phase2"


# ---------------------------------------------------------------------- metrics


def classification_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
    y_pred: np.ndarray | None = None,
) -> dict[str, Any]:
    """Positive-class + macro metrics for one split/model.

    ``y_score`` is a risk score (higher = more anomalous / more failure-prone);
    ``threshold`` is only applied to build ``y_pred`` for the confusion-matrix
    class of metrics. ROC/PR AUCs are threshold-free. ``y_pred`` may be passed
    explicitly (e.g. the detector's contamination-calibrated labels) so every
    metric block describes the SAME operating point. Rows of one engine split
    are implicitly engine-disjoint because the caller passes engine-disjoint
    frames (the Phase 2.1 engine split guarantees this).
    """
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    if y_pred is None:
        y_pred = (y_score >= threshold).astype(int)
    else:
        y_pred = np.asarray(y_pred, dtype=int)
    both_classes = {0, 1}.issubset(set(np.unique(y_true)))

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(precision_score(y_true, y_pred, zero_division=0.0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0.0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0.0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0.0)),
        "roc_auc": float(roc_auc_score(y_true, y_score)) if both_classes else None,
        "pr_auc": float(average_precision_score(y_true, y_score)) if both_classes else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "false_negatives": int(fn),
        "false_positives": int(fp),
        "n_rows": int(len(y_true)),
        "n_positives": int(y_true.sum()),
    }


def healthy_false_positive_rate(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    """Fraction of healthy cycles (label 0) incorrectly flagged anomalous."""
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    healthy = y_true == 0
    if not healthy.any():
        return None
    return float((y_pred[healthy] == 1).mean())


def detection_lead_time(frame: pd.DataFrame, y_pred: np.ndarray, y_true: np.ndarray) -> dict[str, Any]:
    """How early - in remaining cycles - failing engines first get flagged.

    For every engine that eventually fails within the horizon (has label-1
    rows) the "lead" is the remaining life (``rul_raw``) at its first alert;
    larger = more warning time. Engines without degraded rows are excluded
    (their alerts belong to the healthy-FPR statistics); failing engines with
    no alert count into ``detection_rate`` but contribute no lead.
    """
    frame = frame.reset_index(drop=True)
    y_pred = np.asarray(y_pred, dtype=int)
    y_true = np.asarray(y_true, dtype=int)
    leads: list[float] = []
    engines_with_degradation = 0
    for _, rows in frame.groupby("unit", sort=True):
        positions = rows.index.to_numpy()
        if not (y_true[positions] == 1).any():
            continue
        engines_with_degradation += 1
        flagged = positions[y_pred[positions] == 1]
        if len(flagged):
            first = int(flagged[0])
            leads.append(float(frame.loc[first, "rul_raw"]))
    detected = len(leads)
    return {
        "engines_with_degradation": engines_with_degradation,
        "engines_detected": detected,
        "detection_rate": (detected / engines_with_degradation) if engines_with_degradation else None,
        "mean_lead_cycles": float(np.mean(leads)) if leads else None,
        "median_lead_cycles": float(np.median(leads)) if leads else None,
        "leads": leads,
    }


def anomaly_metrics(
    y_true: np.ndarray,
    y_score: np.ndarray,
    y_pred: np.ndarray,
    frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Anomaly-specific metrics: healthy FPR, degraded recall, lead time.

    Everything is computed against the detector's own contamination-calibrated
    ``y_pred`` (an Isolation Forest scores anomalies, it does not emit
    probabilities), so precision/recall/F1/AUCs all describe one operating
    point.
    """
    metrics = classification_metrics(y_true, y_score, y_pred=y_pred)
    y_pred = np.asarray(y_pred, dtype=int)
    metrics.update(
        {
            "healthy_cycle_fpr": healthy_false_positive_rate(y_true, y_pred),
            "degraded_cycle_recall": float(recall_score(y_true, y_pred, zero_division=0.0)),
            "anomaly_score_quantiles": score_quantiles(y_score, y_true),
        }
    )
    if frame is not None:
        metrics["detection_lead_time"] = detection_lead_time(frame, y_pred, y_true)
    return metrics


def score_quantiles(y_score: np.ndarray, y_true: np.ndarray) -> dict[str, Any]:
    """Score distribution summaries per class (for the JSON reports)."""
    result: dict[str, Any] = {}
    for name, mask in (("healthy", np.asarray(y_true, dtype=int) == 0), ("degraded", np.asarray(y_true, dtype=int) == 1)):
        scores = np.asarray(y_score, dtype=float)[mask]
        if not len(scores):
            continue
        result[name] = {
            "n": int(len(scores)),
            "p05": float(np.quantile(scores, 0.05)),
            "median": float(np.median(scores)),
            "p95": float(np.quantile(scores, 0.95)),
            "mean": float(scores.mean()),
        }
    return result


def anomaly_score_distribution_plot(healthy: np.ndarray, degraded: np.ndarray, path: Path, title: str) -> Path:
    """Histogram of anomaly scores for healthy vs degraded cycles."""
    fig, axis = plt.subplots(figsize=(7, 4))
    axis.hist(
        [np.asarray(healthy, dtype=float), np.asarray(degraded, dtype=float)],
        bins=40,
        stacked=False,
        label=["healthy (label 0)", "degraded (label 1)"],
        color=["#2a9d8f", "#e76f51"],
        alpha=0.75,
    )
    axis.set_xlabel("anomaly score (- decision function)")
    axis.set_ylabel("cycles")
    axis.set_title(title)
    axis.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --------------------------------------------------------------------- plots


def confusion_plot(
    matrices: list[tuple[str, "np.ndarray"]],  # (model, 2x2 matrix)
    path: Path,
    title: str,
) -> Path:
    """One panel per model: raw confusion counts + row-normalised percentage."""
    panels = len(matrices)
    fig, axes = plt.subplots(1, panels, figsize=(3.4 * panels, 3.4))
    axes = np.atleast_1d(axes)
    for axis, (name, matrix) in zip(axes, matrices):
        matrix = np.asarray(matrix, dtype=float)
        axis.imshow(matrix, cmap="Blues", vmin=0)
        axis.set_xticks([0, 1], labels=["healthy", "failure"])
        axis.set_yticks([0, 1], labels=["healthy", "failure"])
        axis.set_title(f"{name}\n(TN={int(matrix[0, 0])} FP={int(matrix[0, 1])} FN={int(matrix[1, 0])} TP={int(matrix[1, 1])})")
        total = matrix.sum()
        for (row, column), value in np.ndenumerate(matrix):
            share = value / total if total else 0.0
            axis.text(column, row, f"{int(value)}\n{share:4.0%}", ha="center", va="center",
                      color="white" if matrix[row, column] > matrix.max() / 2 else "black")
    fig.suptitle(title)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def model_comparison_plot(rows: list[dict[str, Any]], metrics: list[str], path: Path, title: str) -> Path:
    """Grouped bars: x = datasets, one bar per (model, metric) combination."""
    datasets = sorted({row["dataset_id"] for row in rows})
    models = sorted({row["model"] for row in rows})
    bar_count = len(models) * len(metrics)
    bar_width = 0.8 / max(bar_count, 1)
    centers = np.arange(len(datasets))
    palette = {"xgboost": "#264653", "random_forest": "#2a9d8f", "isolation_forest": "#e9c46a"}
    fig, axis = plt.subplots(figsize=(max(9.0, 1.7 * len(datasets)), 4.2))
    labelled: set[str] = set()
    bar_index = 0
    for model in models:
        for metric in metrics:
            values = []
            for dataset_id in datasets:
                row = next((item for item in rows if item["dataset_id"] == dataset_id and item["model"] == model), None)
                value = row.get(metric) if row is not None else None
                values.append(float(value) if isinstance(value, (int, float)) else 0.0)
            label = f"{model} ({metric})"
            legend_label = label if label not in labelled else "_nolegend_"
            labelled.add(label)
            axis.bar(
                centers + 0.4 - bar_count * bar_width / 2 + bar_index * bar_width,
                values,
                width=bar_width * 0.9,
                color=palette.get(model, "#a8a8a8"),
                label=legend_label,
            )
            bar_index += 1
    axis.set_xticks(centers, datasets)
    axis.set_ylabel("metric value")
    axis.set_ylim(0.0, 1.05)
    axis.set_title(title)
    axis.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def feature_importance_plot(
    importances: dict[str, pd.Series],
    path: Path,
    title: str,
    top: int = 15,
) -> Path:
    """Horizontal top-N bars next to each other, one lane per model."""
    names = list(importances)
    fig, axes = plt.subplots(1, len(names), figsize=(5.2 * len(names), 0.3 * top + 1.4))
    axes = np.atleast_1d(axes)
    for axis, (name, series) in zip(axes, importances.items()):
        head = series.head(top)[::-1]
        axis.barh(list(head.index), list(head.values), color="#264653")
        axis.set_title(name)
        axis.tick_params(axis="y", labelsize=7)
    fig.suptitle(title)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# ------------------------------------------------------------- orchestration


def _model_metrics(
    kind: str,
    model: Any,
    frame: pd.DataFrame,
    horizon: int,
    threshold: float,
) -> dict[str, Any]:
    """Full metric block for one (model kind, split) pair."""
    label = f"failure_within_{horizon}"
    y_true = frame[label].to_numpy()
    if kind == "isolation_forest":
        y_score = model.score(frame)
        y_pred = model.predict(frame)
        return anomaly_metrics(y_true, y_score, y_pred, frame=frame)
    y_score = model.predict_proba(frame)[:, 1]
    y_pred = model.predict(frame)
    return classification_metrics(y_true, y_score, threshold=threshold)


def _summary_row(dataset_id: str, model: str, split: str, metrics: dict[str, Any]) -> dict[str, Any]:
    """Flatten one metric block into a CSV/plot-friendly record."""
    row: dict[str, Any] = {
        "dataset_id": dataset_id,
        "model": model,
        "split": split,
        "threshold": metrics["threshold"],
        "n_rows": metrics["n_rows"],
        "n_positives": metrics["n_positives"],
    }
    for key in ("precision", "recall", "f1", "macro_f1", "roc_auc", "pr_auc"):
        row[key] = metrics.get(key)
    confusion = metrics.get("confusion_matrix", {})
    for key in ("tn", "fp", "fn", "tp"):
        row[key] = confusion.get(key)
    if "healthy_cycle_fpr" in metrics:
        row["healthy_cycle_fpr"] = metrics.get("healthy_cycle_fpr")
        row["degraded_cycle_recall"] = metrics.get("degraded_cycle_recall")
        lead = metrics.get("detection_lead_time", {})
        row["lead_mean_cycles"] = lead.get("mean_lead_cycles")
        row["lead_median_cycles"] = lead.get("median_lead_cycles")
        row["detection_rate"] = lead.get("detection_rate")
    return row


def _record_evaluation_in_manifest(dataset_id: str, name: str, evaluation: dict[str, Any]) -> None:
    """Persist validation/test metrics into the model's own manifest."""
    from predictive_maintenance.models.persistence import read_manifest

    manifest = read_manifest(dataset_id, name)
    manifest["evaluation"] = evaluation
    write_manifest(manifest, dataset_id, name)


def evaluate_dataset(
    dataset_id: str,
    horizon: int = DEFAULT_HORIZON,
    threshold: float = DEFAULT_THRESHOLD,
    seed: int = 42,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate every Phase 2 model variant on one subset; write its reports.

    Model selection uses validation metrics; official test numbers are
    produced only for the reports (never fed back into any choice).
    """
    from predictive_maintenance.models import training

    train_frame = load_split(dataset_id, "train")
    val_frame = load_split(dataset_id, "val")
    test_frame = load_test_features(dataset_id, rul_cap=config.RUL_CAP, horizon=horizon)
    label = f"failure_within_{horizon}"

    models: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    importances: dict[str, pd.Series] = {}
    detector: IsolationForestDetector | None = None

    for kind in ("isolation_forest", "random_forest", "xgboost"):
        model, _ = training.load_or_train(
            dataset_id, kind, horizon=horizon, seed=seed, force=False, threshold=threshold
        )
        name = training.model_name(kind, ablated=False)
        val_metrics = _model_metrics(kind, model, val_frame, horizon, threshold)
        test_metrics = _model_metrics(kind, model, test_frame, horizon, threshold)
        models[name] = {"validation": val_metrics, "test": test_metrics}
        rows.append(_summary_row(dataset_id, name, "validation", val_metrics))
        rows.append(_summary_row(dataset_id, name, "test", test_metrics))
        _record_evaluation_in_manifest(dataset_id, name, {"validation": val_metrics, "test": test_metrics})
        if kind == "isolation_forest":
            detector = model
        elif kind == "random_forest":
            importances["random_forest"] = model.feature_importances()

    if training.ablation_applies(dataset_id):
        for kind in ("isolation_forest", "random_forest", "xgboost"):
            model, _ = training.load_or_train(
                dataset_id, kind, horizon=horizon, seed=seed, force=True, threshold=threshold, ablated=True
            )
            name = training.model_name(kind, ablated=True)
            val_metrics = _model_metrics(kind, model, val_frame,horizon, threshold)
            test_metrics = _model_metrics(kind, model, test_frame, horizon, threshold)
            models[name] = {"validation": val_metrics, "test": test_metrics}
            rows.append(_summary_row(dataset_id, name, "validation", val_metrics))
            rows.append(_summary_row(dataset_id, name, "test", test_metrics))
            _record_evaluation_in_manifest(dataset_id, name, {"validation": val_metrics, "test": test_metrics})
            if kind == "random_forest":
                importances["random_forest (no s10/s16)"] = model.feature_importances()

    _write_dataset_figures(dataset_id, models, importances, val_frame, detector, horizon, threshold)

    healthy_config = detector.config if detector is not None else AnomalyConfig()
    models_clean: dict[str, Any] = {}
    for name, block in models.items():
        models_clean[name] = {
            split: {key: _jsonifiable(value) for key, value in block[split].items()}
            for split in ("validation", "test")
        }

    report: dict[str, Any] = {
        "dataset_id": dataset_id,
        "label_config": {
            "failure_horizon": horizon,
            "rul_cap": config.RUL_CAP,
            "healthy_rul_min": healthy_config.healthy_rul_min,
            "classification_threshold": threshold,
            "label_definition": f"failure_within_{horizon}: engine fails within {horizon} cycles (uncapped truth)",
        },
        "data": {
            "train_rows": int(len(train_frame)),
            "train_engines": int(train_frame["unit"].nunique()),
            "validation_rows": int(len(val_frame)),
            "validation_engines": int(val_frame["unit"].nunique()),
            "validation_positive_ratio": float(val_frame[label].mean()),
            "official_test_rows": int(len(test_frame)),
            "official_test_engines": int(test_frame["unit"].nunique()),
            "official_test_positive_ratio": float(test_frame[label].mean()),
            "test_source": "test_<id>.txt engines with truth from RUL_<id>.txt (preprocessing fitted on train engines only)",
        },
        "models": models_clean,
        "feature_importance": {
            name: {column: float(value) for column, value in series.items()}
            for name, series in importances.items()
        },
        "dataset_version": dataset_version(dataset_id),
        "environment": environment_versions(),
        "caveat": (
            "C-MAPSS degradation is simulated: 'failure' is the end of a run-out "
            "trajectory chosen by the dataset designers, not a discrete physical event."
        ),
    }
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    (EVALUATION_DIR / f"eval_{dataset_id}.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report, rows


def _jsonifiable(value: Any) -> Any:
    """Recursively convert numpy scalars/arrays into plain JSON types."""
    if isinstance(value, dict):
        return {str(key): _jsonifiable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonifiable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def _write_dataset_figures(
    dataset_id: str,
    models: dict[str, Any],
    importances: dict[str, pd.Series],
    val_frame: pd.DataFrame,
    detector: IsolationForestDetector | None,
    horizon: int,
    threshold: float,
) -> None:
    """Confusion matrices, anomaly score distributions, feature importance."""
    base_order = ("isolation_forest", "random_forest", "xgboost")
    for split in ("validation", "test"):
        panels = []
        for kind in base_order:
            block = models.get(kind)
            if block is None:
                continue
            confusion = block[split]["confusion_matrix"]
            matrix = np.array([[confusion["tn"], confusion["fp"]], [confusion["fn"], confusion["tp"]]])
            panels.append((kind, matrix))
        if panels:
            confusion_plot(
                panels,
                PHASE2_FIGURES_DIR / f"confusion_{dataset_id}_{split}.png",
                f"{dataset_id} {split} confusion matrices (horizon {horizon}, threshold {threshold})",
            )

    if detector is not None:
        label = f"failure_within_{horizon}"
        y_true = val_frame[label].to_numpy()
        scores = detector.score(val_frame)
        anomaly_score_distribution_plot(
            scores[y_true == 0],
            scores[y_true == 1],
            PHASE2_FIGURES_DIR / f"anomaly_scores_{dataset_id}.png",
            f"{dataset_id} anomaly score distribution (validation engines)",
        )

    if importances:
        feature_importance_plot(
            importances,
            PHASE2_FIGURES_DIR / f"feature_importance_{dataset_id}.png",
            f"{dataset_id} feature importance (top 15)",
        )


def run_evaluation(
    dataset_ids: tuple[str, ...] | list[str],
    horizon: int = DEFAULT_HORIZON,
    threshold: float = DEFAULT_THRESHOLD,
    seed: int = 42,
) -> dict[str, Any]:
    """Full Phase 2.5 run: per-dataset reports + cross-dataset comparison."""
    rows: list[dict[str, Any]] = []
    reports: dict[str, Any] = {}
    for dataset_id in dataset_ids:
        report, dataset_rows = evaluate_dataset(dataset_id, horizon=horizon, threshold=threshold, seed=seed)
        reports[dataset_id] = report
        rows.extend(dataset_rows)

    comparison_rows = [
        row
        for row in rows
        if row["split"] == "validation" and row["model"] in ("isolation_forest", "random_forest", "xgboost")
    ]
    if comparison_rows:
        model_comparison_plot(
            comparison_rows,
            ["f1", "roc_auc"],
            PHASE2_FIGURES_DIR / "model_comparison_validation.png",
            f"Phase 2 model comparison on validation engines (horizon {horizon})",
        )

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = EVALUATION_DIR / "evaluation_summary.csv"
    pd.DataFrame(rows).to_csv(summary_path, index=False)
    return {
        "reports": reports,
        "summary_csv": str(summary_path),
        "figures_dir": str(PHASE2_FIGURES_DIR),
        "n_rows": len(rows),
    }

