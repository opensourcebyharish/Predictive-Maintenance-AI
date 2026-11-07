# Production Deployment Guide — predictive-maintenance-ai

Phase 6.1 deliverable. Everything in this document reflects the state of the
repository on **2026-11-07** and was verified against the live stack (see
§11 "Verification report"). Commands shown for PowerShell; POSIX equivalents
are given where they differ.

---

## 1. What ships

| Component | Stack | Entry point |
| --- | --- | --- |
| Backend API | Python 3.10, FastAPI 0.162, uvicorn 0.54, SQLAlchemy 2.0 | `predictive_maintenance.api.main:app` |
| Database | SQLite (file-based, single-writer) | `data/predictive_maintenance.db` |
| Models | Isolation Forest, Random Forest, XGBoost (joblib) + preprocessing pipeline | `models/<FD001..FD004>/` |
| Dashboard | React 19 + TypeScript + Vite (static build) | `frontend/dist/` |
| Data simulator | `scripts/run_simulator.py` → batch `POST /readings/batch` | CLI |

Runtime dependencies are pinned by `pyproject.toml` (extras `ml`, `api`,
`dev`). `requirements.txt` mirrors the full runtime surface as of Phase 6.1
(it used to list only the Phase 1 core deps — a fresh `pip install -r
requirements.txt` would previously have produced an API that could not boot).

---

## 2. Configuration profile: development vs production

All backend configuration is environment-driven (`API_*` prefix), read by
`src/predictive_maintenance/api/config.py`. Full reference: `.env.example`
in the repository root.

| Variable | Default (dev) | Production guidance |
| --- | --- | --- |
| `API_ENV` | `development` | `production` — enables the fail-fast CORS guard |
| `API_HOST` | `127.0.0.1` | `0.0.0.0` behind a reverse proxy |
| `API_PORT` | `8000` | whatever the orchestrator assigns |
| `API_CORS_ORIGINS` | `*` | **required**, comma-separated explicit origins |
| `API_DATABASE_URL` | `sqlite:///./data/predictive_maintenance.db` | absolute URL (`sqlite:////var/lib/pma/app.db`) until §8 upgrade |
| `API_MODEL_DIR` | `models` | mounted artifact volume path |
| `API_LOG_LEVEL` | `info` | `info` (or `warning` for quieter ops) |
| `API_APP_NAME` / `API_APP_VERSION` | fixed | optional overrides shown by `/health` |
| `API_ALERT_ELEVATED_FAILURE` | `0.5` | tuning only |
| `API_ALERT_CRITICAL_FAILURE` | `0.8` | tuning only |
| `API_ALERT_ANOMALY_ENABLED` | `true` | tuning only |

**Production CORS fail-fast.** Starting the app with `API_ENV=production` and
no `API_CORS_ORIGINS` aborts at startup with a `ValueError` (message tells
the operator exactly what to set). Explicitly supplying `*` boots but emits a
loud `UserWarning` in the log — allowed as an escape hatch, never silent.
Development behavior is unchanged (wildcard default, no warning).

Simulator configuration uses the same pattern with the `SIMULATOR_` prefix
(`SIMULATOR_API_URL`, `SIMULATOR_MACHINE_COUNT`, `SIMULATOR_INTERVAL_SECONDS`,
`SIMULATOR_DURATION_SECONDS`, `SIMULATOR_SEED`, `SIMULATOR_SCENARIO`,
`SIMULATOR_BATCH_SIZE`, `SIMULATOR_DATASET_ID`).

Frontend: `VITE_API_BASE_URL` is baked into the bundle at build time
(`frontend/.env.production`); the Settings page can still retarget a built
bundle at runtime (persisted in localStorage).

---

## 3. Files the git checkout does NOT contain

These are intentionally untracked (see `.gitignore`) and must be produced by
the build pipeline or attached volumes. **A fresh `git clone` alone cannot
serve traffic.**

| Path | Size | How to produce | Shipping method |
| --- | --- | --- | --- |
| `models/` | **212.1 MB**, 45 files | `scripts/train_anomaly_detector.py`, `scripts/train_classifiers.py` (+ `scripts/build_features.py` prerequisites) | artifact volume / build cache |
| `data/raw/`, `data/processed/` | several hundred MB | `scripts/download_data.py`, `scripts/build_features.py` | training-time only; API does **not** need them |
| `data/predictive_maintenance.db` | ~108 KB | created automatically on first write | persistent volume |
| `data/test_phase3.db` | small | leftover Phase 3 local test file | ignore / archive |

Model artifact inventory actually loaded by the API (surfaces in `/ready`):
per dataset `FD001`–`FD004`: `preprocessing_pipeline.joblib` +
`{isolation_forest, random_forest, xgboost}.{joblib,json}` with a manifest
feature-contract check on load. Additional files present (`*_no_s10_s16.*`
variants, `models/FD000`, `models/FD001X`) are Phase 2 experiment leftovers —
**not loaded, not served, safe to exclude** from a serving image (excluding
them trims the volume to ~180 MB).

Integrity note: manifests pin `dataset_version.train_sha256` — the same
checksum appears in `model_version` of every prediction (e.g.
`FD001:random_forest@ab12cd34ef56`). Verifying manifests count == the 4×3
expected pairs before rollout is part of the startup checklist (§4).

---

## 4. Production startup procedure

```powershell
# 0) Get the code + models volume in place (see §3).
cd C:\path\to\predictive-maintenance-ai

# 1) Virtual environment + full runtime deps
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ml,api]"

# 2) Configuration (no secrets exist in this project; everything is non-secret)
$env:API_ENV            = "production"
$env:API_HOST           = "0.0.0.0"
$env:API_PORT           = "8000"
$env:API_CORS_ORIGINS   = "https://dashboard.internal.example.com"
$env:API_DATABASE_URL   = "sqlite:////srv/pma/data/predictive_maintenance.db"
$env:API_MODEL_DIR      = "models"

# 3) Smoke-verify settings/profile BEFORE binding 0.0.0.0
.\.venv\Scripts\python.exe -c "from predictive_maintenance.api.config import get_settings; s=get_settings(); print(s.env, s.is_production, s.cors_origin_list)"

# 4) Start (no --reload in production!)
.\.venv\Scripts\python.exe -m uvicorn predictive_maintenance.api.main:app \
  --app-dir src --host $env:API_HOST --port $env:API_PORT --log-level info

# 5) Verify
curl.exe http://127.0.0.1:8000/health    # {"status":"ok",...}
curl.exe http://127.0.0.1:8000/ready     # ready must be true before going live
```

POSIX: `set -a; source .env; set +a;` then the same uvicorn command with
`python3 -m uvicorn`.

Worker/process guidance for SQLite (§8): one uvicorn **process** (default
`workers=1`) is the supported topology. The pool is 5 + 10 overflow with a
30 s checkout timeout; multiple in-process threads are fine, multiple
machines writing the same SQLite file concurrently is the single most
dangerous scaling step and would need the §8 upgrade first.

**Graceful stop (Windows):**

```powershell
# Find the listener AND any child it may have spawned
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'uvicorn|spawn_main' } |
  Select-Object ProcessId, CommandLine
Stop-Process -Id <PID> -Force
```

uvicorn handles `SIGINT`/`SIGTERM` gracefully on POSIX (`systemd`/compose
`stop_grace_period` work fine). On Windows, `Stop-Process` is a hard kill;
there is no long-running state inside uvicorn (SQLite commits are per-request
and the model cache is read-only), so it is acceptable — see §6. Historical
note from this very project: **an orphaned `multiprocessing.spawn_main`
child (from an earlier `--reload` usage) held port 8000 and kept the old app
answering while operators believed it was killed.** Always hunt children and
re-probe `/health` after a restart (the shipped `app_version` + stdin-free
process list is the tell).

---

## 5. Application lifecycle (startup/shutdown safety)

Phase 6.1 migrated the deprecated `@app.on_event("startup")` hook to a
proper **lifespan context manager** (`main.py::_lifespan`):

* **startup** — loads all model artifacts best-effort. Per-dataset failures
  are captured and surfaced by `GET /ready` (`ready:false` + per-dataset
  `error`), never a crash loop. The SQLite schema is *lazily* initialized on
  the first session, so `API_DATABASE_URL` overrides (tests, ephemeral
  containers) are safe.
* **shutdown** — `db.shutdown_engine()` disposes the SQLAlchemy pool so
  connections do not dangle on process exit. It is idempotent, safe if the
  process never touched the DB, and deliberately does **not** reset engine
  globals (a disposed engine transparently reopens connections — same
  restart-safe pattern the persistence tests rely on).
* **path safety** — `init_db` now creates the SQLite parent directory
  (SQLite creates files, never folders → "unable to open database file" on a
  fresh volume is fixed), and the URL normalizer passes absolute URLs through
  untouched: `sqlite:///:memory:`, POSIX `sqlite:////abs/dir/app.db`, and
  Windows drive-letter paths (`sqlite:///C:/data/app.db`) are never
  project-relative-resolved (drive-letter resolution bug fix).

---

## 6. Health & readiness endpoints

`GET /health` (liveness — answer "process is up"):

```json
{ "status": "ok", "app": "predictive-maintenance-ai",
  "version": "0.2.0", "service_loaded": true }
```

`GET /ready` (readiness — answer "models can serve"). Phase 6.1 added one
**additive** field, `database`; all pre-existing keys are unchanged, so the
frontend contract (`frontend/src/api/types.ts`) is unaffected:

```json
{ "ready": true, "datasets": { "...": {} },
  "database": {
    "driver": "sqlite",
    "initialized": true,
    "file": "C:\\...\\data\\predictive_maintenance.db",
    "file_exists": true
  } }
```

Semantics of `database` (side-effect free; it never creates the engine or
schema): `driver` from the URL only; `initialized` true once this process has
created its engine; `file`/`file_exists` the resolved SQLite path and its
presence — distinguishing "configured but never used" from "reachable".
`ready` itself concerns **model** artifacts only, exactly as before.

`/ready` is the container/compose `healthcheck` target; `/health` doubles as
the `livenessProbe`. Both are unauthenticated by design (§9).

---

## 7. Runtime limitations (known, documented — not speculatively "fixed")

### 7.1 SQLite single-writer

The engine pool is 5 base + 10 overflow connections, `timeout=30 s`. SQLite
serializes writes; concurrent writers queue. Consequences:

* Ingest bursts from multiple simulators hammering the same file can hit
  queueing (measured in Phase 5.3: with the session-leak fix, 24 concurrent
  mixed requests complete in ~0.3 s; the pre-6.1 risk was leaked sessions,
  not SQLite itself).
* Never run two **server processes** against the same DB file.
* No automated migration was executed as part of 6.1 (constraint: document
  first). Postgres migration implications and path are in §12.

### 7.2 Simulator CLI `stop`/`status` are process-local

`python scripts/run_simulator.py` and its `stop`/`status` verbs share state
in-memory in the *same* process; from another shell they cannot see the
running simulation. Operationally: run it as a background job/process and
stop it by stopping that process; the backend has no stop control (shutdown
is a client-side decision only). For 6.2 the recommendation is to run the
simulator as its own container with a supervisor timeout instead of the CLI
stop/status flow.

### 7.3 Synthetic simulator calibration

Simulator trajectories are **synthetic** and flag as anomalous ~100% of the
time against the real-data-calibrated detectors; therefore the
`machine_recovered` transition cannot fire on synthetic data (covered by
calibrated synthetic models in unit tests). In the current dev database all
three `DEMO-*` machines show health `anomalous` — expected behavior, not a
defect. Feeding real sensor data for the same C-MAPSS feature columns
restores calibrated behavior (healthy false-positive rate ≈ 5.6%,
FD001 eval — see `docs/models.md`). There is **no production mock data**
anywhere in this stack; the simulator must be explicitly started by an
operator.

### 7.4 Existing audit data (IMPORTANT — do not delete)

`data/predictive_maintenance.db` currently contains Phase 2.6/5.3 audit
sessions and must be preserved:

* **7 machines** — `DEMO-NORMAL`, `DEMO-DEVELOPING_DEGRADATION`,
  `DEMO-ABNORMAL_VIBRATION` (synthetic), `REAL-001` (1 reading),
  `REAL-002` (2), `SIM-001` (12), `SIM-002` (12)
* **57 readings / 57 predictions / 7 alerts** — 6 active
  (`anomaly_detected`) + 1 acknowledged (`DEMO-NORMAL`, the Phase 5.3
  integration-test acknowledgment)

`Base.metadata.create_all` never drops or alters existing tables, so a
routine restart is data-safe. If an operator *wants* a clean production file
instead, the documented (not executed) command is to move the file aside:
`Move-Item data\predictive_maintenance.db data\archive\pma-2026-11-07.db` —
create_all then builds a fresh DB. Purging individual audit rows is a
per-row SQL decision for the operator, out of scope here.

---

## 8. Security risks (ranked)

1. **No authentication, no rate limiting.** Every endpoint — including
   ingestion and alert acknowledgment — is open. Acceptable only behind a
   trusted network boundary. Recommendation for 6.2: reverse-proxy TLS +
   IP allowlist now; app-level auth token is a feature request (would be a
   new contract — deliberately not added in 6.1).
2. **CORS wildcard default.** Dev-only by design now, enforced by the §2
   fail-fast. Still a risk if operators set `API_ENV=production` but
   explicitly pass `*` (they get a loud warning, not an abort).
3. **Verbose error bodies.** 404/409/500 handlers return `str(exc)` — useful
   in this closed pilot, leaks internals (feature-contract details) on
   public exposure. Mitigate at the proxy or in a post-6.1 hardening pass.
4. **Docs endpoints exposed.** `/docs`, `/redoc`, `/openapi.json` are open;
   gate them at the proxy for production.
5. **Artifact integrity.** Joblibs load with arbitrary code execution on
   unpickling. `models/` must ship only from the trusted build (no operator
   uploads), surfaced by manifest checksums in `model_version`.
6. **Simulator write amplification.** `POST /readings/batch` accepts
   unbounded multi-MB bodies and the DB grows per cycle; a runaway
   `SIMULATOR_DURATION_SECONDS=0` fills disk. Cap at the proxy (body-size +
   rate limit).
7. **SQLite file permissions.** The DB is world-readable by default on
   shared hosts; put it on a volume with the service user as owner.
8. **No secrets exist today.** The stack is fully config-by-env with no
   credentials; keep it that way (no secrets in `.env` committed — the file
   is gitignored; see `.env.example`).

---

## 9. Deployment artifact checklist

- [ ] `models/` volume attached with 4× (`preprocessing_pipeline.joblib` +
      3 model kinds × joblib/json) = **28 artifact files minimum**
- [ ] `API_ENV=production`, `API_CORS_ORIGINS` explicit, `API_HOST=0.0.0.0`
- [ ] DB directory exists & writable by the service user (auto-created on
      first write since 6.1)
- [ ] `/health` → `service_loaded:true`, `/ready` → `ready:true`
- [ ] Frontend bundle built with the correct `VITE_API_BASE_URL`
- [ ] Reverse proxy: TLS, CORS headers pass-through, body-size cap,
      `/docs` gated
- [ ] DB file + `models/` included in backup plan (SQLite file copy while
      the API is quiescent)

---

## 10. Rolling back

State is tiny: the SQLite file and the `models/` directory. Pin model
rollback by keeping the previous `models/` volume empty-dir swap; app image
rollback is `git checkout <tag>` + pip install (no schema migrations exist —
schema is versioned in code and `create_all`-only).

---

## 11. Verification report (what backs the claims in this document)

All checks below were executed in this session ("pass" statements are not
assertions — they are run logs):

| Check | Result |
| --- | --- |
| Backend test suite `pytest tests -q` | **220 passed**, 0 failed (incl. 20 new Phase 6.1 tests), ~187 s |
| Artifacts actually load | live `/ready` → `ready:true`, all 4 datasets × 3 models `loaded`, no errors |
| `/ready` additive `database` block | unit test asserts shape + side-effect-freeness; **live**: `initialized:false` before first DB request → `true` after (distinguishes configured vs reachable), `file_exists:true` |
| Production CORS fail-fast | unit `ValueError` test + **live**: uvicorn with `API_ENV=production`, no `API_CORS_ORIGINS` → `ValueError: API_CORS_ORIGINS must list explicit origins when API_ENV=production …`, exit code 1, never bound |
| Wildcard-in-production warning | unit test + **live**: `UserWarning: API_CORS_ORIGINS contains '*' while API_ENV=production …` on stderr, process then boots (intentional escape hatch) |
| CORS origin enforcement (production profile) | **live**: allowed origin echoes `access-control-allow-origin: <origin>`; disallowed origin gets no ACAO header |
| Restart data preservation | **live**: production-profile restart returned all 7 audit machines (REAL-001/002, SIM-001/002, 3 DEMO) unchanged |
| SQLite parent-dir creation | unit test creating `nested/deep/app.db` |
| Drive-letter / `:memory:` / 4-slash URL handling | unit tests pass-through |
| Lifespan migration | all 7 `with TestClient(app)` integration test groups still pass (lifespan now executes) |
| Engine disposal on shutdown | unit test proves dispose + continued usability of engine globals |
| `requirements.txt` now boot-sufficient | mirrors `pyproject.toml` `ml`+`api` extras (runtime install path verified against installed venv: fastapi 0.162.0, uvicorn 0.54.0, sklearn 1.7.2, xgboost 3.2.0, numpy 2.2.6, pandas 2.3.3, SQLAlchemy 2.0.57) |
| Frontend suite — not re-run in 6.1 | frozen by constraint; 147/147 green as of Phase 5.3 audit |

Deployment readiness: **backend deployable as a single-process uvicorn with
the documented limitations (§7)**. The single most load-bearing WIP item for
6.2 is the Docker packaging below.

---

## 12. Recommended Docker architecture for Phase 6.2

```
compose services
├── api            build: python:3.10-slim image that pip-installs the project,
│                  COPY models/ into image OR mount read-only volume
│                  env: API_*=  (from compose environment / secret files)
│                  volumes:
│                    - models_volume:/app/models:ro
│                    - data_volume:/app/data          # SQLite lives here
│                  ports: ["8080:8000"]
│                  healthcheck: curl -f http://localhost:8000/ready
│                  command: uvicorn predictive_maintenance.api.main:app
│                            --app-dir src --host 0.0.0.0 --port 8000
├── dashboard      build: multi-stage node:20-alpine → nginx:alpine
│                  static: dist/ served by nginx; SPA fallback to index.html
│                  env (build arg): VITE_API_BASE_URL=http://<host>:8080
│                  proxy: /api/* → api:8000 (avoids CORS entirely — then
│                  API_CORS_ORIGINS lists only the dashboard origin)
├── simulator      same python image as api (different command):
│                  python scripts/run_simulator.py start
│                  env: SIMULATOR_*; duration bounded by a supervisor sidecar
│                  or SIMULATOR_DURATION_SECONDS; restart: on-failure
└── volumes: models_volume (ro for api), data_volume (SQLite; backup with
   compose stop-then-copy, sqlite .backup, or litestream if 24/7 uptime)
```

Deliberate choices:

* **No database container.** SQLite-as-file on a volume is consistent with
  §8; introducing a DB container now would be an unverified migration.
* **No Write-anywhere-shared volumes**: `models/` is mounted `:ro`.
* **The simulator is optional** and off in the baseline profile (§7.3/7.4).
* **TLS termination** happens at an outer reverse proxy (compose publishes
  plain HTTP inside the private network only).

Postgres migration implications (pre-work for 6.2 decision, **not executed**):

* URL swap (`postgresql+psycopg://...`) — the code path already tolerates
  non-SQLite URLs (`connect_args` is URL-conditional; `init_db` skip
  normalizer is a no-op for it).
* Datatypes are all portable (`Integer/String/DateTime/Boolean/Text`); the
  `machines.machine_id` + `readings (machine_id, cycle)` unique indexes are
  the dedup contract and survive.
* Risks: SQLite row-attr JSON in `readings.s_values` is TEXT — schema
  unchanged but write-collision semantics disappear; the `30 s pool timeout`
  tuning moves to `pool_size`/`max_overflow`; **SQLite→Postgres data copy is
  an offline one-shot** (`insert from SELECT` per table, FKs recomputed) and
  would freeze ingestion during the copy window.
* The no-migration constraint: schema is `create_all`-only, so moving to
  Postgres needs `create_all` against an empty Postgres DB plus
  history-preserving copy — plan data preservation first (§7.4 audit data),
  and DO NOT let the change be silent: require the rollout doc to list the
  copy procedure and its freeze window.
