# Phase 4 — IoT Sensor Simulator

The simulator generates **synthetic** engine-cycle sensor readings and sends them
to the existing FastAPI backend (`POST /readings` / `POST /readings/batch`).

> **Important:** The simulator produces *synthetic* data for testing and
> demonstration. All readings are clearly marked with `is_simulated=true` and
> must not be interpreted as validated physical industrial measurements. No
> physical sensor-to-C-MAPSS mappings are claimed as scientifically validated.

## Architecture

```
src/predictive_maintenance/simulator/
  __init__.py     package exports
  config.py       environment-driven settings (SIMULATOR_* env vars)
  scenarios.py    7 scenario generators
  machine.py      per-machine state + reading generation
  client.py       HTTP client (POST /readings/batch)
  simulator.py    orchestrator (start/stop/scenario/status)
  cli.py          command-line interface
scripts/
  run_simulator.py   CLI entry point
```

## Configuration

All settings are environment-variable driven (prefix `SIMULATOR_`):

| Variable | Default | Description |
|---|---|---|
| `SIMULATOR_API_URL` | `http://127.0.0.1:8000` | FastAPI backend base URL |
| `SIMULATOR_MACHINE_COUNT` | `3` | Number of independent machines |
| `SIMULATOR_INTERVAL_SECONDS` | `1.0` | Seconds between sampling rounds |
| `SIMULATOR_DURATION_SECONDS` | `60` | Total run time (0 = run until stopped) |
| `SIMULATOR_SEED` | `42` | Random seed (each machine gets `seed + index`) |
| `SIMULATOR_SCENARIO` | `normal` | Scenario name (see below) |
| `SIMULATOR_BATCH_SIZE` | `10` | Readings per batch request |
| `SIMULATOR_DATASET_ID` | `FD001` | C-MAPSS subset whose models are used |

## Scenarios

Seven scenarios are available. Each generates values for sensors `s1`–`s21`
plus the three operating settings. Sensor groupings are *conceptual only* and
not scientifically validated mappings.

| Scenario | Behaviour |
|---|---|
| `normal` | All sensors near baseline with small Gaussian noise |
| `developing_degradation` | Temperature & vibration sensors drift upward over cycles; RPM declines slightly |
| `abnormal_vibration` | Intermittent spikes on fan/core speed sensors (s8, s9) every 7 cycles |
| `abnormal_temperature` | Sustained elevated temperature readings (s2, s3, s4, s7) |
| `sensor_failure` | Sensor s15 stuck at 0.0 or 9999.0 alternating |
| `sudden_anomaly` | Multi-sensor anomaly spike at cycles 30–45, then return toward baseline |
| `recovery` | Starts anomalous (cycles 1–20), gradually recovers to baseline (21–40) |

## CLI

```powershell
# Start simulation in background
python scripts/run_simulator.py start

# Check status
python scripts/run_simulator.py status

# Check backend health
python scripts/run_simulator.py health

# Change scenario
python scripts/run_simulator.py scenario abnormal_vibration

# Stop simulation
python scripts/run_simulator.py stop

# Start in foreground (runs until duration or Ctrl-C)
python scripts/run_simulator.py start --blocking

# Start with overrides
python scripts/run_simulator.py start --machines 5 --scenario developing_degradation --interval 0.5 --duration 30
```

## API Integration

The simulator submits readings via `POST /readings/batch`. Each reading:

* Is validated against the C-MAPSS schema (unit, cycle, settings, s1–s21)
* Is deduplicated by `(machine_id, cycle)` — re-submitting the same reading returns the existing entry
* Must have strictly increasing cycles per machine — out-of-order cycles are rejected with `409`
* Is scored by the Phase 2 models (Isolation Forest + Random Forest/XGBoost)
* Is stored with `is_simulated=true`
* May trigger alerts (anomaly_detected, elevated_failure_risk, critical_failure_risk)

## Example: Live Demo

```powershell
# 1. Start the API backend
.venv\Scripts\python.exe -m uvicorn predictive_maintenance.api.main:app --app-dir src

# 2. In another terminal, start the simulator
python scripts/run_simulator.py start --machines 3 --scenario developing_degradation --duration 30

# 3. Check monitoring
.venv\Scripts\python.exe -c "import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/machines').read()),indent=1))"

# 4. Check alerts
.venv\Scripts\python.exe -c "import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:8000/alerts/summary').read()),indent=1))"

# 5. Stop
python scripts/run_simulator.py stop
```

## Testing

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_simulator.py tests/unit/test_simulator_integration.py -q
```

## Limitations

* Simulator values are synthetic — not physically validated sensor data
* Sensor groupings (temperature/vibration/pressure/RPM) are conceptual only
* SQLite database only; no multi-user concurrency controls beyond SQLAlchemy
* Alert delivery is not implemented (alerts are persisted; notifications deferred to a later phase)
* No authentication or rate limiting on ingestion endpoints
