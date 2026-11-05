# Phase 2.2–2.5 — Models: anomaly detection, failure classification, evaluation

This document describes the model layers added on top of the completed Phase 2.1
preprocessing (engineered feature parquet tables + per-dataset manifests under
`data/processed/`). Phase 1 (raw data loaders, EDA) and Phase 2.1 code were not
modified.

```
src/predictive_maintenance/models/
  __init__.py        public API
  datasets.py        feature/label loading, official-test label attachment,
                     ablation, dataset versioning (SHA-256 of raw files)
  anomalies.py       Phase 2.2: Isolation Forest anomaly detector
  forest.py          Phase 2.3: RandomForest failure classifier
  boost.py           Phase 2.4: XGBoost failure classifier
  persistence.py     joblib + JSON artifact manifests
  training.py        shared fit/load/persist + validation metrics
  evaluation.py      Phase 2.5: metrics, plots, JSON/CSV reports
scripts/
  train_anomaly_detector.py   CLI: Phase 2.2
  train_classifiers.py        CLI: Phase 2.3/2.4
  evaluate_models.py          CLI: Phase 2.5
```

Artifacts (reproducible, not committed to git — see `.gitignore`):

```
models/<FD00X>/
  isolation_forest.joblib/.json   anomaly detector (+ manifest)
  random_forest.joblib/.json      RF failure classifier (+ manifest)
  xgboost.joblib/.json            XGB failure classifier (+ manifest)
  *_no_s10_s16.joblib/.json       ablated variants (FD002/FD004 only)
```

Reports/figures:

```
reports/evaluation/
  eval_FD00{1..4}.json           per-subset machine-readable report
  evaluation_summary.csv         flat metric table (all subsets/splits/models)
reports/figures/phase2/
  confusion_<subset>_<validation|test>.png
  anomaly_scores_<subset>.png
  feature_importance_<subset>.png
  model_comparison_validation.png
```

## Phase 2.2 — Isolation Forest anomaly detection

`models/anomalies.py` — `IsolationForestDetector(AnomalyConfig)`.

**Healthy-only fit.** The detector is fitted exclusively on *healthy* training
observations: rows whose uncapped remaining life `rul_raw >= healthy_rul_min`
(default 50 cycles), i.e. before degradation onset contaminates the nominal
baseline. Degraded training rows are ignored at fit time; every row can be
scored at inference.

**Configuration (defaults):**

- `n_estimators=300`, `contamination=0.05`, `healthy_rul_min=50`,
  `random_state=42`, `n_jobs=-1`.
- `contamination` and `random_state` are user-configurable (CLI flags
  `--contamination`, `--healthy-rul`, `--n-estimators`, `--seed`).

**Scores and predictions.** Score = `-decision_function(X)` (higher = more
anomalous). Binary predictions come from the contamination-calibrated
`IsolationForest.predict()` (`-1` → anomaly), so the operating point is fixed at
fit time on healthy training data — never tuned on validation/test rows.

**Simulation caveat (read before interpreting scores).** C-MAPSS degradation is
*simulated*: "failure" is the end of a run-out trajectory chosen by the dataset
designers, not a discrete physical event such as a bearing crack. Anomaly scores
are therefore **degradation/health indicators**, not crash detectors. The
manifest's `caveat` field carries this warning; so does this document.

## Phase 2.3 — Random Forest failure classifier

`models/forest.py` — `ForestFailureClassifier(ForestConfig)`.

Answers per engine-cycle: *"will this engine fail within `failure_horizon`
cycles (default 30)?"* using the Phase 2.1 `failure_within_<h>` labels on
uncapped truth.

- Engine-level train/validation split only (`preprocessing.engine_group_split`,
  seed 42, 20% holdout) — never row-level random splits; training, validation
  and test engines are strictly disjoint.
- Configurable class weights (`class_weight="balanced"` default), `n_estimators`,
  `max_depth`, `min_samples_leaf`, `random_state`, `n_jobs`.
- Emits binary predictions plus calibrated class probabilities
  (`predict_proba` columns `[healthy, failure]`).
- Saves model + manifest (parameters, feature columns, class counts, dataset
  version, split seed, validation metrics).

## Phase 2.4 — XGBoost failure classifier

`models/boost.py` — `BoostFailureClassifier(BoostConfig)`.

Identical dataset splits, feature definitions, horizon and labels as the Random
Forest — apples-to-apples comparison in Phase 2.5.

- Configurable hyperparameters (`n_estimators=400`, `learning_rate=0.05`,
  `max_depth=6`, `subsample=0.8`, `colsample_bytree=0.8`, `min_child_weight=5`,
  `reg_lambda=1.0`, `tree_method="hist"`).
- **Class imbalance:** `scale_pos_weight` auto-computed as
  `n_negatives / n_positives` of the training labels (configurable override).
- **Early stopping:** `early_stopping_rounds=50` against the held-out
  *validation engines* (`eval_metric="logloss"`). The official NASA test
  engines are never part of any fit or early-stopping set. `best_iteration_` is
  recorded in the manifest.
- Dependency declared in `pyproject.toml` `[ml]` extra (`xgboost>=2.0`) and
  installed in the venv (`pip install -e ".[ml]"` → xgboost 3.2.0).

## Phase 2.5 — Unified evaluation

`models/evaluation.py` — metrics, figures, JSON/CSV reports; orchestrated by
`scripts/evaluate_models.py`.

### Metrics

Classification (per split/model): precision, recall, F1, macro-F1, ROC-AUC,
PR-AUC, confusion matrix (TN/FP/FN/TP counts), false-negative and false-positive
counts, positive-class support.

Anomaly detection (Isolation Forest, contamination-calibrated operating point):
precision/recall/F1/AUCs computed against `predict()` labels plus
healthy-cycle FPR, degraded-cycle recall, anomaly score quantiles, and
**detection lead time** — for every failing engine, remaining life
(`rul_raw`) at its first alert; mean/median/count reported over detected
engines ("where meaningful": engines with no degraded rows contribute to FPR,
not lead time).

### Splits and model-selection discipline

- FD001–FD004 evaluated separately.
- Models are compared on **validation engines only** (the Phase 2.1 hold-out).
- Test metrics are produced **once per run** purely for reporting — never used
  to choose hyperparameters, thresholds, or models.
- XGBoost early stopping uses validation engines only.
- The official NASA test engines (`test_FD00X.txt`) receive true labels from
  `RUL_FD00X.txt`: `rul_true(c) = RUL_file[u] + (last_cycle − c)`, giving a
  label for every row of every truncated test trajectory. Preprocessing
  statistics stay exactly those fitted on training engines.

### Ablation

FD002/FD004 models are additionally trained/evaluated without the `s10`/`s16`
sensor features (`ablate_features` drops `s10_*`/`s16_*` columns at the model
layer — zero preprocessing changes), saved as `<kind>_no_s10_s16` artifacts.

### Reports

Per subset: `reports/evaluation/eval_FD00X.json` (validation + test metrics per
model variant, feature importances, data statistics, dataset version,
environment versions, caveat) and a flattened row set in
`reports/evaluation/evaluation_summary.csv`. Figures: per-split confusion
matrices per model, anomaly score distributions, feature importances, and a
cross-subset model comparison (validation F1 / ROC-AUC).

### Manifests

Every artifact manifest records: dataset version (SHA-256 of the raw
`train/test/RUL` files), feature configuration (Phase 2.1 pipeline config +
dropped sensors/regimes), model hyperparameters, split seed, environment
library versions, validation metrics, and — after evaluation — test metrics
(under `evaluation`).

## Usage

```powershell
# Phase 2.2
python scripts\train_anomaly_detector.py --dataset all --healthy-rul 50

# Phase 2.3 + 2.4 (same splits/labels as 2.2's features)
python scripts\train_classifiers.py --dataset all --horizon 30 --seed 42

# Phase 2.5 (loads/trains models as needed; official test engines scored once)
python scripts\evaluate_models.py --dataset all --threshold 0.5
```

Python 3.10 compatible; run tests with `.venv\Scripts\python.exe -m pytest tests -q`
(108 tests, ~35 s).
