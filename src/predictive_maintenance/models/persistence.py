"""Model-artifact persistence for Phase 2: joblib models + JSON manifests.

Layout under ``models/`` (one directory per C-MAPSS subset)::

    models/FD001/isolation_forest.joblib
    models/FD001/isolation_forest.json     <- manifest for the detector
    models/FD001/random_forest.joblib
    models/FD001/random_forest.json
    models/FD001/xgboost.joblib
    models/FD001/xgboost.json
    models/FD002/xgboost_no_s10_s16.joblib # <- ablation variants use a suffix

A manifest carries everything needed to re-explain a training run: dataset
version (raw-file SHA-256s), feature configuration, model hyper-parameters,
split seed, and validation metrics observed at training time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib

from predictive_maintenance import config


def model_dir(dataset_id: str) -> Path:
    return config.MODELS_DIR / dataset_id


def artifact_stem(dataset_id: str, name: str) -> str:
    """File stem for one model, e.g. ``xgboost_no_s10_s16``."""
    return name


def save_artifact(model: Any, dataset_id: str, name: str) -> Path:
    """Pickle a fitted wrapper to ``models/<dataset>/<name>.joblib``."""
    directory = model_dir(dataset_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.joblib"
    joblib.dump(model, path)
    return path


def load_artifact(dataset_id: str, name: str) -> Any:
    """Restore a fitted wrapper saved by :func:`save_artifact`."""
    path = model_dir(dataset_id) / f"{name}.joblib"
    if not path.is_file():
        raise FileNotFoundError(f"no such model artifact: {path}")
    return joblib.load(path)


def manifest_path(dataset_id: str, name: str) -> Path:
    return model_dir(dataset_id) / f"{name}.json"


def write_manifest(manifest: dict[str, Any], dataset_id: str, name: str) -> Path:
    path = manifest_path(dataset_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def read_manifest(dataset_id: str, name: str) -> dict[str, Any]:
    path = manifest_path(dataset_id, name)
    if not path.is_file():
        raise FileNotFoundError(f"no manifest {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def environment_versions() -> dict[str, str]:
    """Library versions recorded in every manifest (reproducibility hints)."""
    import numpy
    import pandas
    import sklearn

    versions = {"numpy": numpy.__version__, "pandas": pandas.__version__, "sklearn": sklearn.__version__}
    try:
        import xgboost

        versions["xgboost"] = xgboost.__version__
    except ImportError:  # pragma: no cover - only when xy extra is missing
        versions["xgboost"] = "not-installed"
    return versions
