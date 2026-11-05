"""Train the Phase 2.3/2.4 failure classifiers: Random Forest and XGBoost.

Run from the repository root (venv active)::

    python scripts/train_classifiers.py --dataset all
    python scripts/train_classifiers.py --dataset FD001 --horizon 30 --seed 42

Both models consume exactly the same engineered feature tables and
``failure_within_<horizon>`` labels; the engine-level train/hold-out split is
the Phase 2.1 one (whole engines, seeded). XGBoost early-stops against the
held-out validation engines - never the official test split. Artifacts +
manifests land under ``models/<dataset>/``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from predictive_maintenance import config  # noqa: E402
from predictive_maintenance.models import training  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--dataset", default="all", choices=[*config.DATASET_IDS, "all"])
    parser.add_argument("--horizon", type=int, default=30, help="failure horizon in cycles")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true", help="retrain even when artifacts exist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    datasets = list(config.DATASET_IDS) if args.dataset == "all" else [args.dataset]
    for dataset_id in datasets:
        for kind in (training.FOREST_NAME, training.BOOST_NAME):
            _, val_metrics = training.load_or_train(
                dataset_id,
                kind,
                horizon=args.horizon,
                seed=args.seed,
                force=args.force,
            )
            best = val_metrics.get("best_iteration")
            note = f" best_iteration={best}" if best is not None else ""
            print(
                f"{dataset_id} {kind}: f1={val_metrics['f1']:.3f} recall={val_metrics['recall']:.3f} "
                f"precision={val_metrics['precision']:.3f} roc_auc={val_metrics.get('roc_auc'):.3f} "
                f"pr_auc={val_metrics.get('pr_auc'):.3f}{note}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
