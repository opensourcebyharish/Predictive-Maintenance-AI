"""Train the Phase 2.2 Isolation Forest anomaly detector (healthy-cycle baseline).

Run from the repository root (venv active)::

    python scripts/train_anomaly_detector.py --dataset all
    python scripts/train_anomaly_detector.py --dataset FD001 --healthy-rul 50 --contamination 0.05

Fits on healthy TRAINING rows only (``rul_raw >= --healthy-rul``), saves the
detector + manifest under ``models/<dataset>/`` and prints the validation
metrics (held-out engines; never official test engines).
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
    parser.add_argument("--healthy-rul", type=int, default=50, help="healthy = remaining life >= this")
    parser.add_argument("--contamination", type=float, default=0.05, help="expected anomaly share of healthy rows")
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    datasets = list(config.DATASET_IDS) if args.dataset == "all" else [args.dataset]
    for dataset_id in datasets:
        _, val_metrics = training.load_or_train(
            dataset_id,
            training.DETECTOR_NAME,
            seed=args.seed,
            force=True,
            n_estimators=args.n_estimators,
            contamination=args.contamination,
            healthy_rul_min=args.healthy_rul_min,
        )
        lead = val_metrics.get("detection_lead_time", {})
        print(
            f"{dataset_id}: fitted on healthy training rows, "
            f"recall={val_metrics['recall']:.3f} f1={val_metrics['f1']:.3f} "
            f"roc_auc={val_metrics.get('roc_auc'):.3f} healthy_fpr={val_metrics['healthy_cycle_fpr']:.4f} "
            f"lead_mean={lead.get('mean_lead_cycles')} cycles"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
