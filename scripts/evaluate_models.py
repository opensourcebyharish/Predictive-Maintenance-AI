"""Run the Phase 2.5 unified evaluation over all Phase 2 models.

Run from the repository root (venv active)::

    python scripts/evaluate_models.py --dataset all
    python scripts/evaluate_models.py --dataset FD001 --threshold 0.5

For each subset: inspects Isolation Forest / Random Forest / XGBoost on the
held-out validation engines AND on the official NASA test engines (with true
labels from ``RUL_<id>.txt``; official test engines are never used for
fitting or model selection). On FD002/FD004 it additionally trains+evaluates
variants without the s10/s16 features. Outputs:

* ``reports/evaluation/eval_FD00X.json`` - per-subset machine-readable report
* ``reports/evaluation/evaluation_summary.csv`` - flat metric table
* ``reports/figures/phase2/`` - confusion matrices, model comparison,
  anomaly score distribution and feature-importance figures
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from predictive_maintenance import config  # noqa: E402
from predictive_maintenance.models.evaluation import run_evaluation  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--dataset", default="all", choices=[*config.DATASET_IDS, "all"])
    parser.add_argument("--horizon", type=int, default=30, help="failure horizon used by the classifiers")
    parser.add_argument("--threshold", type=float, default=0.5, help="classifier probability threshold")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    datasets = list(config.DATASET_IDS) if args.dataset == "all" else [args.dataset]
    result = run_evaluation(datasets, horizon=args.horizon, threshold=args.threshold, seed=args.seed)
    for dataset_id, report in result["reports"].items():
        validations = {name: block["validation"].get("f1") for name, block in report["models"].items()}
        ranked = sorted(validations.items(), key=lambda item: item[1] if item[1] is not None else -1.0)
        best = ranked[-1][0] if ranked else "-"
        print(
            f"{dataset_id}: validation F1 ranking -> "
            + ", ".join(f"{name}={value:.3f}" if value is not None else f"{name}=n/a" for name, value in ranked)
            + f" | best (validation) = {best}"
        )
    print(f"summary CSV: {result['summary_csv']}")
    print(f"figures:     {result['figures_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
