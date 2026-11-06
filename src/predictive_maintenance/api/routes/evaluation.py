"""Phase 5 (documented backend addition): read-only evaluation report routes.

The Phase 2.5 unified-evaluation step writes one JSON report per C-MAPSS
subset to ``reports/evaluation/eval_<id>.json``. The Phase 5 dashboard needs
those benchmark metrics through the same API it uses for every other data
source, so this module exposes them read-only:

* ``GET /evaluation``             -> per-dataset summary (best-model metrics)
* ``GET /evaluation/{dataset}``   -> the full report for one dataset

No ML pipeline, training or simulator behaviour is modified: the reports are
static files committed with the repository. ``EVALUATION_REPORTS_DIR`` is a
module constant so tests can point it at a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Path as FPath

from predictive_maintenance import config

router = APIRouter(tags=["evaluation"])

# Reports root, deferrable for tests that monkeypatch this constant.
EVALUATION_REPORTS_DIR: Path = config.ROOT / "reports" / "evaluation"

DATASET_IDS: tuple[str, ...] = config.DATASET_IDS
_SUPERVISED = ("random_forest", "xgboost")


def _report_path(dataset_id: str) -> Path:
    return EVALUATION_REPORTS_DIR / f"eval_{dataset_id}.json"


def _load_report(dataset_id: str) -> dict[str, Any]:
    path = _report_path(dataset_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "evaluation_report_missing",
                "message": f"no evaluation report for {dataset_id!r} at {path.name}",
            },
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500,
            detail={"error": "evaluation_report_invalid", "message": str(exc)},
        ) from exc


@router.get("/evaluation", status_code=200)
def evaluation_index() -> dict[str, Any]:
    """Available dataset reports with the best-model validation summary each.

    ``default_model`` mirrors the Phase 2/3 convention: the supervised model
    with the highest validation F1 (isolation forest is never the default).
    """
    datasets: list[str] = []
    summary: dict[str, Any] = {}
    by_dataset: dict[str, Any] = {}

    for dataset_id in DATASET_IDS:
        if not _report_path(dataset_id).exists():
            continue
        report = _load_report(dataset_id)
        datasets.append(dataset_id)
        validation = {
            name: model.get("validation", {})
            for name, model in (report.get("models", {}) or {}).items()
        }
        best_name: str | None = None
        best_f1 = -1.0
        # Default = best supervised model on validation F1 (matches Phase 3);
        # isolation forest never becomes the ingestion default model.
        for name in _SUPERVISED:
            f1 = (validation.get(name) or {}).get("f1")
            if isinstance(f1, (int, float)) and f1 > best_f1:
                best_f1 = f1
                best_name = name
        # Fall back to isolation forest when no supervised model has metrics.
        if best_name is None:
            for name in ("isolation_forest",):
                f1 = (validation.get(name) or {}).get("f1")
                if isinstance(f1, (int, float)):
                    best_name = name
                    break
        metrics = (validation.get(best_name) or {}) if best_name else {}
        by_dataset[dataset_id] = {
            "default_model": best_name,
            "metrics": metrics,
        }

    summary["datasets"] = datasets
    summary["by_dataset"] = by_dataset
    return summary


@router.get("/evaluation/{dataset_id}", status_code=200)
def evaluation_report(dataset_id: str = FPath(..., description="C-MAPSS subset id, e.g. FD001")) -> dict[str, Any]:
    """Full Phase 2.5 evaluation report for one dataset (static benchmark)."""
    if dataset_id not in DATASET_IDS:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_dataset", "message": f"{dataset_id!r} is not one of {list(DATASET_IDS)}"},
        )
    return _load_report(dataset_id)
