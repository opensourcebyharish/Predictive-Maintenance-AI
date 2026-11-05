# Predictive Maintenance AI

An end-to-end industrial AI system that monitors machine sensor data, detects
abnormal behaviour, and predicts equipment failures **before** they happen.

- **Domain:** Industrial AI / IoT
- **Output:** health score (0–100), anomaly detection, failure risk, remaining useful life (RUL)
- **Stack:** pandas / NumPy · scikit-learn + XGBoost · FastAPI · IoT simulator
- **Dataset:** [NASA C-MAPSS turbofan degradation](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) (FD001–FD004)

## Status

| Phase | Scope | State |
|---|---|---|
| 1 — Data & setup | dataset download, loaders, EDA report, IoT simulator | ✅ |
| 2 — Machine learning | **2.1 preprocessing ✅** · **2.2 Isolation Forest anomaly detection ✅** · **2.3/2.4 Random Forest + XGBoost classifiers ✅** · **2.5 unified evaluation ✅** | ✅ |
| 3 — Backend | **3.1 FastAPI foundation ✅** · **3.2 Model loading + prediction service ✅** · 3.3 (storage/ingestion) ⬜ | 🚧 |
| 4 — IoT simulation | streaming readings, alerts | ⬜ (simulator core done in Phase 1) |
| 5 — Dashboard | live charts, health status, alert history | ⬜ |
| 6 — Deployment | Docker, tests, docs | ⬜ |

## Repository layout

```
scripts/                       command-line entry points
  download_data.py             fetch the 13 C-MAPSS files into data/raw/CMAPSSData
  run_eda.py                   regenerate reports/eda_summary.md + figures
  build_features.py            Phase-2.1 feature build -> data/processed/*.parquet + manifest
  train_anomaly_detector.py    Phase 2.2: Isolation Forest anomaly detector
  train_classifiers.py         Phase 2.3/2.4: Random Forest + XGBoost failure classifiers
  evaluate_models.py           Phase 2.5: unified evaluation -> reports/evaluation + figures
src/predictive_maintenance/    installable package
  api/                         Phase 3: FastAPI backend (config, schemas, service, routes)
  config.py                    paths, dataset metadata, sensor names
  data/cmapss.py               C-MAPSS readers + RUL labelling
  data/download.py             dataset fetch (mirror fallback logic)
  data/simulator.py            synthetic machine IoT simulator (fleet of 3)
  eda/report.py                Phase-1 EDA figure + markdown generation
  preprocessing/               Phase-2.1 pipeline: validation, features, regimes, splits
docs/preprocessing.md          preprocessing workflow, guarantees and assumptions
docs/models.md                 Phase 2.2-2.5: anomaly detection, failure classifiers, unified evaluation
```

## Setup & run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .

python scripts\download_data.py   # ~45 MB of C-MAPSS text data
python scripts\run_eda.py         # writes reports/eda_summary.md and figures
python scripts\build_features.py  # Phase 2.1: engineered feature parquet + manifest
python scripts\train_anomaly_detector.py  # Phase 2.2: isolation forest detector -> models/*/*.joblib
python scripts\train_classifiers.py       # Phase 2.3/2.4: RF + XGB classifiers -> models/*/*.joblib
python scripts\evaluate_models.py         # Phase 2.5: unified evaluation -> reports/evaluation/* + reports/figures/phase2/*
.venv\Scripts\python.exe -m uvicorn predictive_maintenance.api.main:app --app-dir src  # Phase 3: API on http://127.0.0.1:8000
```

See `docs/preprocessing.md` for the feature workflow, its guarantees and the
dataset assumptions.

## Notes

- ChatGPT-sourced project brief; development follows its 6-phase roadmap.
- Anomaly detection (unsupervised) and failure prediction (supervised) are kept
  as separate tasks by design; an unusual reading does not imply a certain failure.
- C-MAPSS degradation is *simulated* — the "failure" is the end of a run-out
  trajectory chosen by the dataset designers, not a discrete physical event such
  as a bearing crack. Model outputs are therefore degradation/health indicators,
  not crash predictors.
