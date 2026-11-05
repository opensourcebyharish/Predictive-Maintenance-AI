# Preprocessing & feature engineering (Phase 2.1)

This document describes the ML preprocessing pipeline in
`src/predictive_maintenance/preprocessing/` - what it produces, why each stage
exists, which guarantees hold, and which assumptions about the NASA C-MAPSS
data we make. Everything is reproducible via
`scripts/build_features.py` (`--dataset all` builds FD001-FD004).

## Stage order

The same stage sequence runs in `fit` and `transform`, so both always emit the
same schema:

| # | Stage | Where |
|---|---|---|
| 1 | validate frame + canonical `(unit, cycle)` order + targets | `validation.py`, `features.py` |
| 2 | operating-regime encoding (`condition_id`) | `regimes.py` |
| 3 | missing-value repair | `pipeline.py` |
| 4 | per-regime sensor level normalization | `pipeline.py` |
| 5 | constant-sensor removal | `pipeline.py` |
| 6 | trailing rolling features (mean / std / trend slope) | `features.py` |
| 7 | global feature standardization | `pipeline.py` |

Inputs: one row per engine-cycle with `unit`, `cycle`, the 3 `setting_*`
columns and the 21 `s*` sensor columns (the layout of the raw files).

Output schema: `unit`, `cycle`, `condition_id`, the raw settings, `rul_raw`
(uncapped remaining cycles), `RUL` (capped target), `failure_within_<h>` (the
binary label), then the feature block.

### Targets

- `rul_raw` - remaining life as `lifespan(engine) - cycle`. Not a feature, only
  label truth.
- `RUL` - piecewise-linear (clipped) regression target, `min(rul_raw, 130)`.
  The cap $130$ is the literature-standard choice for C-MAPSS; it softens the
  "healthy" plateau where RUL is not observable from the sensors.
- `failure_within_<h>` - binary label, 1 when the engine fails within `h`
  more cycles (`rul_raw <= h`, inclusive at the boundary). Default horizon
  `h = 30` cycles. The label is computed from the **uncapped** `rul_raw`, so
  the cap cannot censor it; the config rejects `h > cap` combinations where
  censoring would begin.

### Operating regimes

FD002/FD004 simulate six flight conditions by appointing `setting_1`
(altitude) centers `{0, 10, 20, 25, 35, 42}` with `setting_2` (Mach) centers
`{0, 0.25, 0.62, 0.7, 0.84}`; everything is contaminated with |noise| < 0.005,
and `setting_3` (TRA) is a constant 100.

Raw settings cannot be categorical keys (the noise makes ~500 unique values),
and naive rounding splits a regime at the noise floor. The `RegimeEncoder`
therefore **learns** the actual centers from training rows only: sorted unique
values collapse into one center while the gap to the previous center stays
within a tolerance (altitude 2.0, Mach 0.02). Every row is then assigned to
its nearest learned center pair, giving a small integer `condition_id`
(1 regime for FD001/FD003, 6 for FD002/FD004). Unseen pairs map to the nearest
learned pair so the serving layer never errors on novel readings.

### Level normalization and rolling features

Sensors mean different things in different flight conditions (the EDA shows
sensor-vs-RUL spread collapses once conditions are separated). Each kept
sensor's *level* is thus z-scored **within its regime**:

```
s_lvl = (s - mean(s | condition_id, train)) / std(s | condition_id, train)
```

On that normalized level the pipeline computes **history-only** features per
engine with a trailing window `W` (default 5 cycles):

- `s_rmW` - trailing mean
- `s_rsW` - trailing std (a single sample counts as spread 0)
- `s_slW` - slope of the linear regression over the trailing W points
  (closed-form OLS; prefix rows regress over the partial history)

Finally the whole feature block is standardized with **train** mean/std.
Trivia: partial windows never reach into the future or into other engines, and
columns such as `s4_lvl` recover the raw sensor as `s4_lvl * std + mean`
whenever the raw value is needed.

### Missing values & constant sensors

C-MAPSS contains no NaNs; the repairs exist so the pipeline is safe for the
simulator and later serving data:

- **Missing** - forward-fill within the engine's own trajectory; leading gaps
  fall back to the train-time per-regime median. Never future rows, never
  other engines.
- **Constant** - a sensor whose *post-normalization* train-level variance is
  below `constant_tolerance` (default 1e-6) is dropped. This catches both a
  globally constant sensor (FD001: `s1, s5, s10, s16, s18, s19`) and one that
  only carries the regime offset (FD002/FD004 drop `s1, s5, s18, s19`).
  The decision is stored in the fitted state, so `transform` drops the same
  columns everywhere.

## Leakage guarantees

1. **Splitting** - `engine_group_split` allocates *whole engines* to
   train/validation with a seeded permutation. Consecutive cycles of one
   engine are near-duplicates; a random row split would leak future cycles
   into validation and inflate metrics. Engine ids are disjoint and cover the
   input exactly; the same seed reproduces the same partition.
2. **Chronology** - frames are validated to strictly increase `cycle` within
   every engine, and re-ordered into canonical `(unit, cycle)` order. Rolling
   features look strictly backwards (trailing windows).
3. **Fit/transform separation** - regimes, per-regime medians/means/stds and
   the final feature scaler are all learned in `fit` on training rows only;
   `transform` never updates them. A fitted pipeline is picklable
   (plain dataclass + numpy + pandas state) and ready for Phase 2.3 artefacts.

## Reproduce

```powershell
.venv\Scripts\activate
python scripts\build_features.py --dataset all          # default knobs
python scripts\build_features.py --dataset FD001 --window 5 --horizon 30 --cap 130
```

Outputs land in `data/processed/`:
`features_FD00X_{train,val}.parquet` + `manifest_FD00X.json` (every knob,
learned regime summary, dropped sensors, split sizes and label counts).

Result summary (default config, seed 42):

| dataset | regimes | dropped sensors | features | train/val engines | train/val rows | label-positive ratio |
|---|---|---|---|---|---|---|
| FD001 | 1 | s1,s5,s10,s16,s18,s19 | 60 | 80/20 | 16 779/3 852 | 14.8% |
| FD002 | 6 | s1,s5,s18,s19 | 68 | 208/52 | 43 083/10 676 | - |
| FD003 | 1 | s1,s5,s16,s18,s19 | 64 | 80/20 | 20 074/4 646 | - |
| FD004 | 6 | s1,s5,s18,s19 | 68 | 199/50 | 48 731/12 518 | - |

## Assumptions & caveats

- **One row = one engine-cycle**; `unit` is the engine id (kept unrenamed -
  the project's key everywhere is `(unit, cycle)`).
- **Training frames know the full trajectory**, so `rul_raw` is exact there.
  For unseen engines (e.g. the `test_FD00X.txt` half-trajectories) `rul_raw`
  counts cycles since the first *observed* row - it is NOT true remaining
  life. The serving layer transforms such frames for features and ignores the
  label columns; true evaluation uses `RUL_FD00X.txt`.
- The `condition_id` on unseen data comes from the nearest learned regime
  pair, not a novel cluster.
- Engine id contiguity (`1..N`) and `cycle = 1..lifespan` without gaps are
  properties of the *raw file layout* (`validate_cmapss_dataset`); the lenient
  `validate_engine_frame` only demands monotone cycles for any other frame.
- Sensors that were dropped as constant can be re-created from the fitted
  statistics; they are simply uninformative for the models.
- Label class balance depends on the horizon: shorter horizons give fewer
  positives. FD001 with `h=30` is ~15% positive, which is a healthy ratio for
  Phase 2.3's precision/recall work.
