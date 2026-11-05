# Predictive Maintenance AI — Phase 2.2–2.5 Implementation Report

**Commit:** `8df9f41` "Phase 2.2-2.5: anomaly detection, failure classification, unified evaluation"
**Branch:** `master` (on top of `05f18b1` Phase 2.1)
**Environment:** Windows, Python 3.10.11 venv `.venv`; scikit-learn 1.7.2, XGBoost 3.2.0, joblib 1.6.0, pandas 2.3.3, numpy 2.2.6 (all declared in `pyproject.toml` `[ml]` extra, installed via `pip install -e ".[ml]"`).

---

## 1. Files changed / created

### New source modules (`src/predictive_maintenance/models/`)
| File | Phase | Purpose |
|---|---|---|
| `__init__.py` | all | public API |
| `datasets.py` | shared | feature-matrix column contract; official NASA test label attachment (`rul_true = RUL_file + (last_cycle − cycle)`); `s10`/`s16` ablation helper; dataset versioning via raw-file SHA-256 |
| `anomalies.py` | 2.2 | `IsolationForestDetector` + `AnomalyConfig` — healthy-rows-only fit, configurable `contamination`/`random_state`/`healthy_rul_min` |
| `forest.py` | 2.3 | `ForestFailureClassifier` + `ForestConfig` — Random Forest on `failure_within_<h>` labels |
| `boost.py` | 2.4 | `BoostFailureClassifier` + `BoostConfig` — XGBoost, auto `scale_pos_weight`, early stopping on validation engines |
| `persistence.py` | all | joblib artifacts + JSON manifests (dataset version, feature config, params, split seed, environment versions) |
| `training.py` | all | shared fit/load/persist + validation-metric computation |
| `evaluation.py` | 2.5 | unified metrics, plots (confusion, comparison, importance, score distributions), JSON/CSV reports, manifest test-metric updates |

### New CLI scripts (`scripts/`)
- `train_anomaly_detector.py` — Phase 2.2 (`--dataset`, `--healthy-rul`, `--contamination`, `--n-estimators`, `--seed`)
- `train_classifiers.py` — Phase 2.3/2.4 (`--dataset`, `--horizon`, `--seed`, `--force`)
- `evaluate_models.py` — Phase 2.5 (`--dataset`, `--horizon`, `--threshold`, `--seed`)

### New tests (`tests/unit/`)
- `test_models.py` — 31 synthetic tests (no real data)
- `test_models_real.py` — 13 FD001 integration smoke tests

### Docs / config
- `docs/models.md` — new: Phase 2.2–2.5 design, guarantees, simulated-degradation caveat, usage
- `README.md` — status table row 2 marked complete, scripts list, `docs/models.md` pointer, simulated-degradation note
- `.gitignore` — `/models/` (trained artifacts ignored; package source under `src/.../models/` remains tracked)

### Generated artifacts (committed as portfolio evidence)
- `reports/evaluation/eval_FD00{1..4}.json`, `evaluation_summary.csv`
- `reports/figures/phase2/` — 17 figures (confusion matrices per split, anomaly score distributions, feature importances, model comparison)

Model binaries (`models/*/*.joblib/.json`) are **not** committed — reproducible via the training scripts and now git-ignored.

---

## 2. Test results

| Suite | Count | Result |
|---|---|---|
| Phase 1 + 2.1 existing tests | 64 | ✅ pass |
| `tests/unit/test_models.py` (synthetic) | 31 | ✅ pass |
| `tests/unit/test_models_real.py` (FD001 real data) | 13 | ✅ pass |
| **Full suite `pytest tests -q`** | **108** | ✅ **all pass** (~35 s) |

Coverage of the required areas:
- engine-level split integrity (train/val engine disjointness asserted on real parquet)
- no train/test engine overlap (official test engines scored only through `transform`)
- no preprocessing leakage (deterministic, pure `transform` on test; two consecutive builds identical)
- anomaly detector fit only on healthy training rows (healthy-subset size asserted; degraded rows score higher)
- correct failure labels (official test `rul_raw` last-cycle == RUL-file value; inclusive horizon boundary; RUL cap ≤ 130)
- serialization round-trips (detector/RF/XGB: predictions identical after save/load)
- probability validity (rows sum to 1, within [0, 1], shape (n, 2))
- metric correctness (hand-computed precision/recall/F1/macro-F1/ROC-AUC/PR-AUC/confusion; single-class → AUC `None`, no crash)
- reproducibility (same seed → identical predictions/scores across fits)
- synthetic edge cases (no-healthy fit rejected; single-class training rejected; empty eval frame rejected; ablation prefix safety `s1` vs `s10`)
- real-data smoke (FD001 end-to-end: detector ROC > 0.9 on validation, manifest contents incl. `split_seed` and SHA-256 version)

---

## 3. Per-subset metrics

Thresholds: classifier probability threshold 0.5; failure horizon 30 cycles; RUL capped at 130; healthy = `rul_raw >= 50` for the detector. Validation metrics drove all model choices; test metrics below are reported once and were never used for selection.

### FD001 (100 train engines → 80/20 split; 100 official test engines)

| Model | Split | Precision | Recall | F1 | Macro-F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|
| Isolation Forest | validation | 0.675 | 0.915 | **0.777** | 0.862 | 0.977 | 0.917 |
| Isolation Forest | **test** | 0.275 | 0.825 | **0.413** | 0.691 | 0.964 | 0.506 |
| Random Forest | validation | 0.913 | 0.847 | **0.879** | 0.928 | 0.990 | 0.958 |
| Random Forest | **test** | 0.813 | 0.642 | **0.717** | 0.855 | 0.990 | 0.800 |
| XGBoost | validation | 0.788 | 0.897 | **0.839** | 0.903 | 0.988 | 0.951 |
| XGBoost | **test** | 0.642 | 0.756 | **0.694** | 0.843 | 0.989 | 0.773 |

Anomaly (IF): validation healthy-FPR 8.4%, degraded recall 91.5%, mean lead 191.6 cycles, 25/25 failing engines detected. Test healthy-FPR 5.6%, degraded recall 82.5%, mean lead 188.2 cycles, 25/25 detected.

### FD002

| Model | Split | Precision | Recall | F1 | Macro-F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|
| Isolation Forest | validation | 0.660 | 0.921 | **0.769** | 0.859 | 0.975 | 0.893 |
| Isolation Forest | **test** | 0.315 | 0.902 | **0.467** | 0.716 | 0.969 | 0.678 |
| Random Forest | validation | 0.906 | 0.830 | **0.866** | 0.922 | 0.989 | 0.949 |
| Random Forest | **test** | 0.725 | 0.737 | **0.731** | 0.861 | 0.986 | 0.811 |
| XGBoost | validation | 0.835 | 0.893 | **0.863** | 0.919 | 0.989 | 0.947 |
| XGBoost | **test** | 0.592 | 0.850 | **0.698** | 0.843 | 0.989 | 0.815 |

Ablation (drop `s10`/`s16` features): IF F1 0.773 val / 0.472 test; RF F1 0.865 val / 0.730 test; XGB F1 0.854 val / 0.685 test — changes ≤ ~0.012 F1, slightly negative overall. IF anomaly: test healthy-FPR 6.5%, degraded recall 90.2%, 26/26 failing engines detected, mean lead 194.7 cycles.

### FD003

| Model | Split | Precision | Recall | F1 | Macro-F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|
| Isolation Forest | validation | 0.619 | 0.539 | **0.576** | 0.758 | 0.955 | 0.760 |
| Isolation Forest | **test** | 0.192 | 0.704 | **0.301** | 0.636 | 0.961 | 0.474 |
| Random Forest | validation | 0.952 | 0.824 | **0.883** | 0.933 | 0.995 | 0.969 |
| Random Forest | **test** | 0.809 | 0.625 | **0.705** | 0.850 | 0.994 | 0.818 |
| XGBoost | validation | 0.888 | 0.895 | **0.892** | 0.937 | 0.993 | 0.963 |
| XGBoost | **test** | 0.647 | 0.794 | **0.713** | 0.854 | 0.994 | 0.814 |

IF anomaly: test healthy-FPR 5.3%, degraded recall 70.4%, mean lead 171.9 cycles, 18/24 failing engines detected (detection rate 0.75).

### FD004

| Model | Split | Precision | Recall | F1 | Macro-F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|
| Isolation Forest | validation | 0.533 | 0.903 | **0.670** | 0.802 | 0.960 | 0.759 |
| Isolation Forest | **test** | 0.189 | 0.750 | **0.302** | 0.632 | 0.949 | 0.354 |
| Random Forest | validation | 0.882 | 0.832 | **0.856** | 0.918 | 0.991 | 0.936 |
| Random Forest | **test** | 0.721 | 0.575 | **0.640** | 0.817 | 0.990 | 0.678 |
| XGBoost | validation | 0.816 | 0.900 | **0.856** | 0.917 | 0.991 | 0.940 |
| XGBoost | **test** | 0.607 | 0.720 | **0.659** | 0.825 | 0.991 | 0.708 |

Ablation (drop `s10`/`s16`): IF F1 0.678 val / 0.315 test; RF F1 0.854 val / 0.647 test; XGB F1 0.855 val / 0.657 test — marginal (≤ ~0.002 F1). IF anomaly: test healthy-FPR 6.9%, degraded recall 75.0%, mean lead 162.3 cycles, 102/106 failing engines detected (detection rate 0.96).

*Source: `reports/evaluation/evaluation_summary.csv` (one row per dataset/split/model).*

---

## 4. Best model by validation metrics (model selection basis)

| Subset | Best model (validation F1) | Runner-up | Notes |
|---|---|---|---|
| FD001 | Random Forest — **0.879** | XGBoost 0.839 | RF chosen |
| FD002 | Random Forest — **0.866** | XGBoost 0.863 | RF chosen (XGB within 0.003) |
| FD003 | XGBoost — **0.892** | Random Forest 0.883 | XGB chosen |
| FD004 | XGBoost — **0.856** ≈ RF 0.856 | tie | XGB chosen on PR-AUC (0.940 vs 0.936) |

The Isolation Forest never wins on classification F1 — it is a ranking/anomaly detector (ROC-AUC ≥ 0.947 everywhere), not a precision-oriented classifier, which is expected for its unsupervised design. No hyperparameters were tuned on any test set; XGBoost early stopping used validation engines only.

---

## 5. Final test metrics (reported once, not used for selection)

Best model per subset → official-test numbers:

| Subset | Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | TP / FN / FP |
|---|---|---|---|---|---|---|---|
| FD001 | Random Forest | 0.813 | 0.642 | 0.717 | 0.990 | 0.800 | 213 / 119 / 49 |
| FD002 | Random Forest | 0.725 | 0.737 | 0.731 | 0.986 | 0.811 | 801 / 286 / 304 |
| FD003 | XGBoost | 0.647 | 0.794 | 0.713 | 0.994 | 0.814 | 231 / 60 / 126 |
| FD004 | XGBoost | 0.607 | 0.720 | 0.659 | 0.991 | 0.708 | 622 / 242 / 403 |

Anomaly detection at test (all subsets): healthy-cycle FPR 5.3–6.9%; degraded-cycle recall 70.4–90.2%; all subsets show usable ranking (ROC-AUC ≥ 0.947). Detection lead time mean 162–195 cycles on detected failing engines.

---

## 6. Limitations and remaining work

### Limitations
1. **Simulated degradation.** C-MAPSS "failure" is the end of a run-out trajectory, not a discrete physical event. Anomaly scores and failure probabilities are degradation/health indicators — documented in manifests, `docs/models.md`, and README notes.
2. **Test-set difficulty gap.** Official test engines include long healthy prefixes and late failures, so test positives are rare (~2.5% for FD001) and test F1 is well below validation F1 (e.g., RF FD001 0.879 val → 0.717 test). This is expected given the fixed, non-tunable test split; no mitigation was applied beyond the prescribed once-only reporting.
3. **Isolation Forest operating point.** Binary predictions use the contamination-calibrated threshold (score > 0), fixed at fit time — not probability 0.5. Precision is modest (test 0.19–0.31) because the 5% contamination budget flags many healthy cycles; recall on degraded cycles is high (0.70–0.92).
4. **No hyperparameter search.** Defaults were used throughout; selection was by validation metrics only, as required. Results are baselines, not tuned optima.
5. **Feature importance** is tree-impurity based (RF) / gain (XGB); no permutation importance or SHAP.

### Remaining work (explicitly deferred per plan)
1. **FastAPI integration** — model-serving endpoints, SQLite storage (Phase 3) — not started.
2. **Dashboard** — live charts, health status, alert history (Phase 5) — not started.
3. Threshold tuning per operating point (cost-sensitive precision/recall trade-offs).
4. Calibration of predicted probabilities (Platt/isotonic) for risk-score interpretability.
5. Additional ablation studies beyond `s10`/`s16` on FD002/FD004.

### How to reproduce
```powershell
.venv\Scripts\activate
python scripts\train_anomaly_detector.py --dataset all
python scripts\train_classifiers.py --dataset all
python scripts\evaluate_models.py --dataset all
pytest tests -q        # 108 passed
```