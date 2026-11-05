"""Build the Phase 2.1 engineered feature tables (parquet) + build manifest.

Run from the repository root (venv active)::

    python scripts/build_features.py --dataset all
    python scripts/build_features.py --dataset FD001 --window 5 --horizon 30

Outputs (``data/processed/``):

* ``features_FD00X_train.parquet`` / ``features_FD00X_val.parquet`` -
  the engineered frames (train = 80% of engines by ``engine_group_split``,
  val = the held-out engines; preprocessing statistics fitted on train only);
* ``manifest_FD00X.json`` - every knob, learned statistic and dropped sensor
  needed to reproduce the build.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from predictive_maintenance import config  # noqa: E402
from predictive_maintenance.data.cmapss import load_cmapss  # noqa: E402
from predictive_maintenance.preprocessing import (  # noqa: E402
    PreprocessingConfig,
    PreprocessingPipeline,
    engine_group_split,
    validate_cmapss_dataset,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--dataset", default="all", choices=[*config.DATASET_IDS, "all"], help="C-MAPSS subset to build")
    parser.add_argument("--window", type=int, default=5, help="trailing rolling window in cycles")
    parser.add_argument("--horizon", type=int, default=30, help="failure-within-horizon label horizon in cycles")
    parser.add_argument("--cap", type=int, default=config.RUL_CAP, help="RUL regression cap (0 = uncapped)")
    parser.add_argument("--seed", type=int, default=42, help="engine split seed (deterministic)")
    parser.add_argument("--test-fraction", type=float, default=0.2, help="fraction of engines held out as validation")
    parser.add_argument("--no-condition-normalization", action="store_true", help="disable per-regime level normalization")
    return parser.parse_args(argv)


def build_dataset(dataset_id: str, args: argparse.Namespace) -> dict[str, object]:
    train_raw = load_cmapss(dataset_id, "train")
    validate_cmapss_dataset({dataset_id: train_raw})
    train_part, val_part = engine_group_split(train_raw, test_fraction=args.test_fraction, seed=args.seed)

    pipeline_config = PreprocessingConfig(
        rolling_window=args.window,
        rul_cap=args.cap or None,
        failure_horizon=args.horizon,
        condition_normalization=not args.no_condition_normalization,
    )
    pipeline = PreprocessingPipeline(pipeline_config)
    train_features = pipeline.fit_transform(train_part)
    val_features = pipeline.transform(val_part)

    train_path = config.PROCESSED_DATA_DIR / f"features_{dataset_id}_train.parquet"
    val_path = config.PROCESSED_DATA_DIR / f"features_{dataset_id}_val.parquet"
    train_features.to_parquet(train_path, index=False)
    val_features.to_parquet(val_path, index=False)

    summary = pipeline.describe()
    manifest = {
        "dataset_id": dataset_id,
        "inputs": {"train_rows": len(train_raw), "splits": {"train_engines": train_part["unit"].nunique(), "val_engines": val_part["unit"].nunique()}, "seed": args.seed, "test_fraction": args.test_fraction},
        "outputs": {"train_parquet": train_path.name, "val_parquet": val_path.name, "train_rows": len(train_features), "val_rows": len(val_features), "train_columns": len(train_features.columns)},
        "label_summary": {
            "positive_ratio_train": float(train_features[f"failure_within_{args.horizon}"].mean()),
            "positive_rows_train": int(train_features[f"failure_within_{args.horizon}"].sum()),
        },
        **summary,
    }
    manifest_path = config.PROCESSED_DATA_DIR / f"manifest_{dataset_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    datasets = list(config.DATASET_IDS) if args.dataset == "all" else [args.dataset]
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for dataset_id in datasets:
        manifest = build_dataset(dataset_id, args)
        print(
            f"{dataset_id}: {manifest['outputs']['train_rows']} train / {manifest['outputs']['val_rows']} val rows, "
            f"{manifest['n_features']} features, {manifest['regimes']['n_regimes']} regimes, "
            f"dropped {','.join(manifest['dropped_sensors']) or '-'} -> {manifest['outputs']['train_parquet']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
