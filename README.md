# Industrial Sensor Alarm ML System

Anomaly detection and early-warning forecasting for a gas treatment process. 28 days of
1-hour sensor data → 8 registered MLflow models → FastAPI inference → user-facing Svelte UI
with live sensor simulation, session auth, and inference history.

```
Notebooks ──► Labeled dataset ──► Airflow ETL (PySpark + SMOTE)
                                        │
                                        ▼
                              MLflow Model Registry
                                   (8 models)
                                        │
              ┌─────────────────────────┤
              ▼                         ▼
     FastAPI inference API     Frontend API (JWT auth)
      /predict /forecast            /history /auto
              │                         │
              └────────────► Svelte UI (live dashboard)
                                  │
                          Mock Sensor API
                       (4 anomaly scenarios)
```

---

## Contents

1. [Architecture](#1-architecture)
2. [Quick Start](#2-quick-start)
3. [Service URLs](#3-service-urls)
4. [Notebook Workflow](#4-notebook-workflow)
5. [File-Drop ETL & Training Pipeline](#5-file-drop-etl--training-pipeline)
6. [Frontend Stack](#6-frontend-stack)
7. [Inference API Reference](#7-inference-api-reference)
8. [Interpretability](#8-interpretability)
9. [Docker / Podman Interchangeability](#9-docker--podman-interchangeability)
10. [Configuration Reference](#10-configuration-reference)
11. [Key Files](#11-key-files)

---

## 1. Architecture

### Services

| Stack | Service | Technology | Purpose |
|-------|---------|------------|---------|
| ML Infra | `postgres` | PostgreSQL 16 | Airflow + MLflow metadata |
| ML Infra | `minio` | MinIO | S3-compatible feature + artifact storage |
| ML Infra | `mlflow` | MLflow 2.17 | Experiment tracking + model registry |
| ML Infra | `airflow-webserver/scheduler` | Airflow 2.10 | ETL and training DAG orchestration |
| ML Infra | `spark-master/worker` | Spark 3.5 | PySpark ETL and model training |
| Frontend | `mock-sensor-api` | FastAPI | Simulated live plant sensor data |
| Frontend | `frontend-api` | FastAPI + SQLite | JWT auth, inference history, live bridge |
| Frontend | `inference-api` | FastAPI + MLflow | ML model serving (point-in-time + forecast) |
| Frontend | `svelte-ui` | Svelte 4 + Vite | Browser UI — dashboard, history, predict |
| Frontend | `prometheus` / `grafana` | Prom + Grafana | Inference + gateway metrics dashboards |
| ML Infra | `prometheus` / `grafana` | Prom + Grafana | Same dashboards, full-stack variant (ports 9090/3000) |

### Data models

Nine instruments across two process units:
`te301020` (°C) · `pdt31008` (mbar) · `pdt31001` (mbar) · `pdt31007` (mbar) ·
`fq31050` (m³/h) · `lt301031` (%) · `lic31012_pv` (%) · `lic31002_pv` (%) · `fic31011_pv` (m³/h)

---

## 2. Quick Start

### Prerequisites

- Podman + `podman-compose` ≥ 1.0 (`pip install podman-compose`)
- 8 GB RAM available (Spark + Airflow are the heavy hitters)

**Windows/WSL2 — verify DNS before starting** (services install packages at startup and
will exit silently if DNS is broken):
```powershell
podman machine ssh "getent hosts pypi.org"
```
If this returns an error instead of an IP address, follow the fix in
[§9 — DNS failure](#internet-access-for-containers-podman-on-wsl2) before proceeding.

### Step 1 — Frontend stack (self-contained, no ML infra required)

```powershell
podman-compose -f infra/compose.frontend.yml up -d
```

> If the ML infra stack (`compose.yml`) is already running on this machine, add
> `-p alarm-frontend` to avoid container-name collisions:
> ```powershell
> podman-compose -p alarm-frontend -f infra/compose.frontend.yml up -d
> ```

Services started: Svelte UI · Frontend API · Mock Sensor API · Inference API · Prometheus · Grafana

### Step 2 — ML infrastructure (needed for live model inference)

```powershell
Copy-Item infra/.env.example infra/.env   # first time only

podman-compose --env-file infra/.env -f infra/compose.yml up -d `
    postgres minio minio_bootstrap mlflow `
    airflow-init airflow-webserver airflow-scheduler `
    spark-master spark-worker file-watcher
```

### Step 3 — Notebooks only (no containers)

```bash
pip install mlflow xgboost lightgbm scikit-learn imbalanced-learn pandas numpy
# Open notebooks in order: 01_eda → 02_models → 03_validation
```

---

## 3. Service URLs

### Frontend stack

| Service | URL | Notes |
|---------|-----|-------|
| Svelte UI | http://localhost:5173 | Main browser UI |
| Grafana | http://localhost:7504 | Risk overview dashboard (no login) |
| Prometheus | http://localhost:7503 | Raw metrics + target health |
| Frontend API | http://localhost:7501 | Auth + history + inference bridge |
| Mock Sensor API | http://localhost:7500 | Simulated live sensor data |
| Inference API | http://localhost:7502 | ML model endpoints |

> Ports 7500–7504 are used to avoid the Hyper-V exclusion zone (7914–8813) on Windows.

### ML Infrastructure stack

| Service | URL | Default credentials |
|---------|-----|---------------------|
| MLflow | http://localhost:5000 | — |
| Airflow | http://localhost:8080 | `admin` / `admin` |
| MinIO Console | http://localhost:9001 | `minio` / `minio123` |
| Spark Master UI | http://localhost:8081 | — |

> **Windows / Hyper-V note:** Ports 8080 and 8081 fall inside the Hyper-V exclusion zone on
> many Windows 10/11 machines. If they are inaccessible, use the Airflow CLI instead of the
> browser. See [§9](#9-docker--podman-interchangeability) for details.

---

## 4. Notebook Workflow

Run the three notebooks in order. Each builds on the previous output.

### `01_eda.ipynb` — Exploratory Analysis & Labelling

```
cleaned_dataset.csv  →  labeled_dataset.csv  +  *.png visualisations
```

- Visualises 28-day sensor timeseries across two process units
- Identifies 6 known anomaly periods from operator logs
- Applies rule-based labelling (pressure spikes, level swings, controller deviations)
- Outputs `labeled_dataset.csv` (adds `anomaly_label` + `regime` columns)

### `02_models.ipynb` — Training + MLflow Registration

```
labeled_dataset.csv  →  7 registered MLflow models
```

Set `MLFLOW_TRACKING_URI=http://localhost:5000` if running against the Docker stack.

| # | Registry name | Algorithm | Task |
|---|--------------|-----------|------|
| 1 | `plant_alarm_champion` | Random Forest / XGBoost | Classification — alarm risk score |
| 2 | `plant_alarm_isolation_forest` | IsolationForest (300 trees) | Unsupervised anomaly detection |
| 3 | `plant_alarm_regime_classifier` | Logistic Regression | 3-class Normal/Transition/Alarm |
| 4 | `plant_alarm_lr_soft_alarm` | LR + isotonic calibration | Calibrated probability |
| 5 | `plant_alarm_rf_soft_alarm` | RF + isotonic calibration | Calibrated probability |
| 6 | `plant_alarm_deviation_predictor` | Ridge regression | Next-hour setpoint deviation |
| 7-9 | `plant_alarm_forecaster_{1,3,6}h` | XGBoost calibrated | Window → t+1/3/6h alarm prob |

### `03_validation.ipynb` — Validation Suite

```
MLflow registry  →  ROC/PR curves  +  walk-forward CV  +  horizon comparison
```

- 5-fold time-series walk-forward cross-validation (24 h gap)
- ROC/PR curves per model
- Forecaster horizon comparison (1h / 3h / 6h F1 / AUC)
- Logs to MLflow experiment `plant_alarm_validation`

---

## 5. File-Drop ETL & Training Pipeline

### ETL (automatic)

```bash
# Drop any CSV/XLS/XLSX into data_drop/ — file-watcher triggers the DAG automatically.
cp labeled_dataset.csv data_drop/

# Manual trigger if watcher is not running:
curl -u admin:admin -X POST http://localhost:8080/api/v1/dags/ingest_etl_local_drop/dagRuns \
    -H 'Content-Type: application/json' \
    -d '{"conf": {"source_path": "/workspace/data_drop/labeled_dataset.csv"}}'

# Or via Airflow CLI (Podman / Docker):
docker exec alarmstack-airflow-scheduler-1 \
    airflow dags trigger ingest_etl_local_drop \
    --conf '{"source_path":"/workspace/data_drop/labeled_dataset.csv"}'
```

> **Windows / inotify note:** The file-watcher uses `inotifywait` which does **not** receive
> events from Windows-filesystem-backed volume mounts (9P/virtio-fs). Trigger the DAG manually
> on Windows via the CLI or REST API above.

DAG `ingest_etl_local_drop` runs:
1. `resolve_source_path` — validates the conf path
2. `great_expectations_validation` — schema + nulls + label range check (rejects bad data early)
3. `etl` — PySpark ETL: normalise, deduplicate, rolling features, SMOTE, sliding-window parquets → MinIO

### Model training (manual trigger)

```bash
# After ETL completes and features are in MinIO:
docker exec alarmstack-airflow-scheduler-1 \
    airflow dags trigger train_models_local

# Promote the best version to @champion alias (MLflow UI or API):
curl -X POST http://localhost:5000/api/2.0/mlflow/registered-models/alias \
    -H 'Content-Type: application/json' \
    -d '{"name":"plant_alarm_champion","alias":"champion","version":"1"}'
```

---

## 6. Frontend Stack

The frontend stack (`infra/compose.frontend.yml`) is self-contained and runs independently
of the heavy ML infrastructure. It brings up six services:

### Mock Sensor API (`mock_sensor_api.py`) — port 7500

Simulates all 9 plant instruments with realistic noise. Ships four anomaly scenarios
switchable at runtime:

| Scenario | Description |
|----------|-------------|
| `normal` | All sensors within operating range |
| `pressure_rise` | PDT31008 linearly drifts toward 315 mbar (flooding risk) |
| `level_swing` | LT301031 oscillates ±28% (reboiler instability) |
| `multi_alarm` | Pressure + level + temperature all trending critical |

```bash
# Switch scenario
curl -X POST http://localhost:7500/scenarios/activate \
    -H 'Content-Type: application/json' -d '{"name":"multi_alarm"}'
```

### Frontend API (`services/frontend_api/app.py`) — port 7501

- **JWT authentication** — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- **Inference history** — every predict/forecast result stored per user in SQLite
- **Inference proxy** — `POST /infer/predict`, `POST /infer/forecast`
- **Auto-inference** — `POST /infer/auto` fetches 20 live readings from the sensor API,
  runs a 1-hour forecast, and persists the result
- **History CRUD** — `GET /history`, `DELETE /history/{id}`

### Inference API (`services/inference/`) — port 7502

FastAPI service that loads models from the MLflow registry:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `POST /predict` | Point-in-time risk score from flat feature vector |
| `POST /forecast` | Sliding-window early-warning (horizon 1/3/6 h) |
| `POST /recommend` | Rule-based maintenance recommendation |
| `POST /explain` | Local SHAP feature importance for one prediction |
| `GET /global_importance` | Global feature importances from the champion model |
| `GET /models` | Lists all expected models and their load status |
| `GET /metrics` | Prometheus metrics |

Set `MLFLOW_TRACKING_URI` in `infra/compose.frontend.yml` (or `infra/.env`) to point the
inference-api at a running MLflow instance. When MLflow is unreachable the API still starts
and returns `503` for model-dependent endpoints — the UI shows the error gracefully.

### Prometheus (`infra/prometheus/`) — port 7503

Scrapes three targets every 15 s:

| Job | Target | Key metrics |
|-----|--------|-------------|
| `inference-api` | `:8000/metrics` | `inference_requests_total`, `inference_last_risk_score`, `inference_latency_seconds` |
| `frontend-api` | `:8001/metrics` | `gateway_infer_total{type}`, `gateway_infer_latency_seconds{type}` |
| `mock-sensor-api` | `:8002/metrics` | `sensor_live_reads_total`, `sensor_scenario_activations_total{scenario}` |

### Grafana (`infra/grafana/`) — port 7504

Opens without login (anonymous admin). The provisioned **Plant Alarm Risk Overview** dashboard has 10 panels across three rows:

- **Row 1** — Last risk score (colour-coded gauge), inference request rate, high-risk alert rate
- **Row 2** — P95 latency (inference-api + gateway overlaid), cumulative request totals
- **Row 3** — Gateway infer rate by type (stacked), gateway P95 latency by type, sensor live/history read rates, scenario activation counts

### Svelte UI (`ui/svelte/`) — port 5173

Four pages, auth-gated (JWT stored in `localStorage`):

| Page | Description |
|------|-------------|
| **Dashboard** | Live 9-sensor grid (2 s poll), scenario switcher, auto-inference toggle, real-time risk chart, top-3 SHAP drivers after each auto-inference |
| **History** | Table + SVG risk-over-time chart of all past inferences, filterable by type |
| **Predict** | Manual point-in-time prediction form (normal + high-risk presets); local SHAP panel + collapsible global importance chart after each prediction |
| **Forecast** | Horizon forecast (+1/3/6 h) with pre-loaded escalating-pressure scenario |

```bash
# Dev server (auto-reloads on save)
cd ui/svelte && npm install && npm run dev
```

---

## 7. Inference API Reference

### `POST /predict`

```bash
curl -X POST http://localhost:7502/predict \
  -H 'Content-Type: application/json' \
  -d '{"features": {"failure_frequency_48": 9, "pdt31008_max": 340.0,
                    "lic31002_deviation": 20.5, "lt301031": 8.0}}'
# → {"risk_score": 1.0, "alarm": 1}
```

### `POST /forecast`

```bash
curl -X POST http://localhost:7502/forecast \
  -H 'Content-Type: application/json' \
  -d '{"horizon": 1, "recent_observations": [
        {"te301020":107.1,"pdt31008":220.0,"pdt31001":6.2,"pdt31007":53.0,
         "fq31050":84.0,"lt301031":47.0,"lic31012_pv":80.0,
         "lic31002_pv":70.0,"fic31011_pv":413.0},
        ... (12 rows minimum, oldest first)
      ]}'
# → {"anomaly_probability": 0.63, "alarm": 1, "horizon_hours": 1, "n_observations": 12}
```

---

## 8. Interpretability

The inference API exposes two endpoints that explain model predictions without requiring any additional client-side dependencies.

### `POST /explain` — local SHAP (per-prediction)

Returns SHAP values for a single feature vector, computed with `shap.TreeExplainer` on the champion model's underlying tree estimator. The endpoint handles all wrapper layers automatically:

```
MLflow pyfunc → _SklearnModelWrapper.sklearn_model
  → sklearn Pipeline (StandardScaler → CalibratedClassifierCV)
    → CalibratedClassifierCV.calibrated_classifiers_[0].estimator
      → RandomForestClassifier  ← TreeExplainer runs here
```

Input data is transformed through the Pipeline's preprocessor (StandardScaler) before SHAP computation so feature-space semantics are preserved.

**Request / response:**

```bash
curl -X POST http://localhost:7502/explain \
  -H 'Content-Type: application/json' \
  -d '{"features": {"te301020": 107.2, "pdt31008": 225.0, ...}}'
# → {
#     "local_importance": [
#       {"feature": "te301020_roll_mean", "value": 107.2,  "shap_value": -0.0897},
#       {"feature": "pdt31008_roll_std",  "value": 14.8,   "shap_value": -0.0691},
#       ...
#     ],
#     "base_value": 0.4987,
#     "method": "shap_tree"
#   }
```

Items are sorted by `|shap_value|` descending. Positive SHAP = pushes toward alarm; negative = pushes toward normal. `base_value` is the expected model output over the training set.

### `GET /global_importance` — model-level feature importance

Returns the champion model's `feature_importances_` (mean impurity decrease across all trees), sorted descending.

```bash
curl http://localhost:7502/global_importance
# → {
#     "importances": [
#       {"feature": "pdt31008_roll_std",  "importance": 0.1813},
#       {"feature": "te301020_roll_mean", "importance": 0.1709},
#       {"feature": "day_of_week",        "importance": 0.0980},
#       ...
#     ],
#     "method": "feature_importances"
#   }
```

Both endpoints return `{"method": "unavailable"}` when no champion model is loaded (e.g. the frontend-only stack without a running MLflow instance).

### Frontend proxy

The frontend API exposes authenticated proxies at:

| Frontend endpoint | Proxies to | Auth |
|---|---|---|
| `POST /infer/explain` | `POST /explain` | JWT required |
| `GET /infer/global_importance` | `GET /global_importance` | JWT required |

Neither call is written to the inference history (explain results are transient UI state).

### UI integration

**Predict page:**  after each prediction, `/infer/explain` fires in parallel with `/infer/predict`. The result is shown as a collapsible diverging bar chart (`FeatureImportanceBar.svelte`):
- **Red bars** extend right → feature pushes toward alarm
- **Green bars** extend left → feature pushes toward normal
- Actual sensor value shown alongside each bar

A second collapsible "Model Feature Importance (Global)" card lazy-loads on first expand using `/infer/global_importance`.

**Dashboard:**  after each auto-inference, the top-3 SHAP drivers from the returned `sensor_snapshot` are shown next to the risk gauge as coloured dots + sensor name + SHAP value.

### Observed results (fresh run, champion = RandomForest)

**Global importance — top 5:**

| Feature | Importance |
|---------|-----------|
| `pdt31008_roll_std` | 0.1813 |
| `te301020_roll_mean` | 0.1709 |
| `day_of_week` | 0.0980 |
| `pdt31001` | 0.0814 |
| `fic31011_op` | 0.0671 |

Pressure-differential volatility (`pdt31008_roll_std`) and amine-temperature trend (`te301020_roll_mean`) account for 35% of total impurity decrease — consistent with the two dominant anomaly patterns in the dataset (flooding-driven pressure spikes and temperature-driven absorption failures).

**Local SHAP — normal vs. high-risk:**

| Feature | Normal (shap) | High-risk (shap) |
|---------|-------------|-----------------|
| `te301020_roll_mean` | −0.090 | **+0.077** |
| `pdt31008_roll_std` | −0.069 | −0.054 |
| `day_of_week` | −0.040 | — |
| `lic31002_pv_roll_std` | — | −0.048 |
| `pdt31007` | — | +0.023 |

`te301020_roll_mean` flips sign between scenarios — negative (stabilising) at normal temperature 107.2 °C, positive (alarm-driving) at elevated temperature 109.5 °C — which matches the physical understanding that DEA absorber flooding is temperature-sensitive.

---

## 9. Docker / Podman Interchangeability


The compose files in this project work with **both Docker and Podman** with minimal changes.
This section documents the differences and how to handle each.

### CLI equivalences

| Task | Docker | Podman |
|------|--------|--------|
| Start stack | `docker compose -f ... up -d` | `podman-compose -f ... up -d` |
| Stop stack | `docker compose -f ... down` | `podman-compose -f ... down` |
| View logs | `docker compose -f ... logs -f` | `podman-compose -f ... logs -f` |
| Exec into container | `docker exec -it name cmd` | `podman exec -it name cmd` |
| Pull images | `docker pull image:tag` | `podman pull image:tag` |
| List containers | `docker ps` | `podman ps` |

The `Makefile` supports swapping via the `ENGINE` variable:
```bash
make up ENGINE=podman   # uses podman compose
make up                 # uses docker (default)
```

### Image name format

Docker Hub images can be referenced without a prefix in Docker but **require the full
`docker.io/` prefix in Podman**:

```yaml
# Works in both
image: docker.io/library/postgres:16

# Podman needs docker.io/ prefix; Docker works either way
image: postgres:16       # Docker only (Podman may fail or fall back silently)
```

All image references in this project already use fully-qualified names (`docker.io/...`,
`ghcr.io/...`) so they work in both runtimes.

### Rootless vs rootful (Podman on Linux/WSL2)

Podman defaults to **rootless** mode — containers run as your own user with no elevated
privileges. Docker Desktop runs a daemon as root.

| Aspect | Docker | Podman rootless | Podman rootful |
|--------|--------|-----------------|----------------|
| Daemon | Always root | No daemon | Root daemon |
| Ports < 1024 | Needs `--privileged` | Requires `net.ipv4.ip_unprivileged_port_start` sysctl | Works natively |
| Performance | Normal | Slight overhead (user namespaces) | Normal |
| SELinux volumes | `:z` not usually needed | `:z` fixes label issues | `:z` not usually needed |

For ports in the 7500–7502 range used by the frontend stack, **rootless works fine** and is
the recommended mode on Linux and Windows/WSL2.

### Windows + Hyper-V port exclusions

Windows reserves many TCP ports for Hyper-V, WSL2, and Windows services. Common excluded
ranges (inspect with `netsh interface ipv4 show excludedportrange protocol=tcp`):

| Range blocked (typical) | Affected service |
|-------------------------|-----------------|
| 7914 – 8013 | Includes 8000 (inference API default) |
| 8014 – 8113 | Includes 8080 (Airflow UI) |
| 9202 – 9801 | Partially overlaps Prometheus range |

**This is why the frontend compose maps to 7500–7502** instead of the usual 8000–8002 —
those ports are inside the Hyper-V exclusion zone on typical Windows 10/11 machines.

If you see `No connection could be made because the target machine actively refused it` on
Windows for any service, check if its port is excluded:
```powershell
netsh interface ipv4 show excludedportrange protocol=tcp | Select-String 'YOUR_PORT'
```

Fix by changing `ports:` in the compose file to an available range.

### Port forwarding on Windows / WSL2 (Podman)

In rootless Podman on Windows/WSL2, port forwarding is managed by `wslrelay.exe`. It
creates a relay from `127.0.0.1:PORT` on Windows to the WSL2 VM. Key behaviours:

- The relay is established **when the container starts**, not at machine start.
- If multiple containers start simultaneously on the same host port there can be relay
  conflicts — start containers sequentially if needed.
- WSL2 mirrored networking (`networkingMode=mirrored` in `~/.wslconfig`) automatically
  forwards all ports but requires **Windows 11 22H2 or later**. On Windows 10 the relay
  mechanism is used.
- In **rootful** mode (`podman machine set --rootful`) Podman uses `netavark` + iptables.
  A known issue in Podman 5.x is that `iptables: Chain already exists` errors can occur
  when containers sharing a network are restarted. If this happens, tear down fully and
  restart:
  ```powershell
  podman-compose -f infra/compose.frontend.yml down
  podman-compose -f infra/compose.frontend.yml up -d
  ```
  Rootless mode does not have this issue.

### Internet access for containers (Podman on WSL2)

#### DNS failure — rootless mode (Windows 10/11)

**Symptom:** `pip install` or `apk add` fails with `Temporary failure in name resolution`
even though `ping 8.8.8.8` works from inside the VM.

**Cause:** WSL2 auto-generates `/etc/resolv.conf` pointing to the WSL2 virtual gateway
(e.g. `172.24.192.1`). Windows Firewall blocks port 53 on that address from inside
containers, so DNS queries time out while raw IP traffic flows fine.

**Fix — override DNS before starting the stack:**
```powershell
# 1. Set public DNS servers in the Podman VM
podman machine ssh "sudo bash -c 'echo nameserver 8.8.8.8 > /etc/resolv.conf && echo nameserver 1.1.1.1 >> /etc/resolv.conf'"

# 2. Prevent WSL from regenerating resolv.conf on next boot
podman machine ssh "sudo bash -c 'printf \"[network]\ngenerateResolvConf = false\n\" >> /etc/wsl.conf'"

# 3. Verify — should print a pypi.org IP, not an error
podman machine ssh "getent hosts pypi.org"
```

Step 2 is persistent across machine restarts. If you ever reset the Podman VM you will
need to re-apply it.

If DNS was already broken when you tried to start the stack, some containers will have
exited. After applying the fix, restart the Podman machine and bring the stack up again:
```powershell
podman machine stop && podman machine start
podman-compose --env-file infra/.env -f infra/compose.yml up -d
```

#### No masquerade rule — rootful mode

In rootful Podman mode on WSL2, newly created bridge networks may not have a masquerade
(NAT) rule for outbound internet traffic. Symptom: `pip install` fails with
`Network is unreachable` (different from the DNS error above — raw IP also fails).

```bash
# Check masquerade rules inside WSL2
podman machine ssh -- "nft list chain ip nat POSTROUTING"

# Add the missing rule if absent (replace 10.89.1.0/24 with your bridge subnet)
podman machine ssh -- "nft add rule ip nat POSTROUTING ip saddr 10.89.1.0/24 oifname eth0 masquerade"
```

### Volume mounts

Both runtimes use the same compose `volumes:` syntax. On Windows/WSL2 with Podman,
volume paths are automatically translated between Windows paths and the WSL2 VM.

```yaml
volumes:
  - ../services/inference/app:/app/app   # relative to compose file — works in both
```

For bind-mounts of host files on SELinux-enabled systems (Fedora, RHEL, CentOS), append
`:z` (shared relabel) or `:Z` (private relabel) to prevent permission errors:
```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro,z
```

### Summary: which mode to use

| Host | Recommendation |
|------|----------------|
| Linux (non-SELinux) | Rootless Podman or Docker — both work cleanly |
| Linux (SELinux) | Rootless Podman with `:z` volume labels, or Docker |
| macOS | Docker Desktop or Podman Desktop (both use a Linux VM) |
| Windows 10/11 | **Rootless Podman** — avoid rootful due to iptables chain bug in Podman 5.x |
| Windows 11 22H2+ | Can enable `networkingMode=mirrored` in `~/.wslconfig` for easier port forwarding |
| CI/CD (GitHub Actions) | Docker (pre-installed). For Podman: `sudo apt install podman` |

---

## 10. Configuration Reference

All settings in `infra/.env` (copy from `infra/.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROMOTION_MODE` | `manual` | `auto` → promote best model to `@champion` after training |
| `MODEL_PROMOTION_METRIC` | `f1_anomaly` | Metric for auto-promotion (`roc_auc_anomaly` also valid) |
| `MODEL_NAME` | `plant_alarm_champion` | Registry name used by `/predict` |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Set to `http://localhost:5000` for notebooks |
| `MLFLOW_S3_ENDPOINT_URL` | `http://minio:9000` | MinIO S3 endpoint for MLflow artifacts |
| `AIRFLOW_ADMIN_USER` | `admin` | Airflow web UI username |
| `AIRFLOW_ADMIN_PASSWORD` | `admin` | Airflow web UI password |
| `MINIO_ROOT_USER` | `minio` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | `minio123` | MinIO secret key |
| `POSTGRES_USER` | `mlops` | Shared Postgres user |
| `UI_PORT` | `8088` | Host port for the nginx reverse proxy |
| `TZ` | `UTC` | Timezone for all containers |

### Frontend compose env (set in `infra/compose.frontend.yml` or `infra/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | `http://host.containers.internal:5000` | MLflow URI for inference-api |
| `JWT_SECRET` | `change-me-in-production` | Secret for signing JWT tokens |
| `VITE_FRONTEND_API_URL` | `http://localhost:7501` | Browser-facing frontend API URL |
| `VITE_SENSOR_API_URL` | `http://localhost:7500` | Browser-facing sensor API URL |

---

## 11. Key Files

```
submission/
├── pipeline.py                       Root data pipeline (Excel → cleaned_dataset.csv)
├── mock_sensor_api.py                Standalone mock sensor API (port 7500)
├── Makefile                          make init/up/down/logs ENGINE=podman|docker
├── labeled_dataset.csv               673 h × 54 cols including anomaly_label
├── cleaned_dataset.csv               673 h × 52 sensor + feature cols
├── model_results.csv                 Per-row model prediction comparison
├── 01_eda.ipynb                      EDA, anomaly labelling, sensor visualisations
├── 02_models.ipynb                   Train & register 8 models via MLflow
├── 03_validation.ipynb               Walk-forward CV, ROC/PR, horizon comparison
│
├── infra/
│   ├── compose.yml                   Full ML infrastructure (12 services)
│   ├── compose.frontend.yml          Self-contained frontend stack (6 services incl. Prometheus + Grafana)
│   ├── .env.example                  Environment variable template
│   ├── airflow/dags/
│   │   ├── ingest_etl_dag.py         File-drop → validation → PySpark ETL
│   │   └── train_dag.py              Manual training trigger
│   ├── spark/jobs/
│   │   ├── etl_job.py                SMOTE + rolling features + MinIO upload
│   │   └── train_job.py              Train 8 models, register in MLflow
│   ├── great_expectations/           Data quality gate (6 expectations)
│   ├── grafana/                      Provisioned "Plant Alarm Risk Overview" dashboard (10 panels)
│   ├── prometheus/prometheus.yml     Scrape config (inference-api, frontend-api, mock-sensor-api)
│   ├── nginx/nginx.conf              Reverse proxy (UI + /api/* routing)
│   └── watcher/watch-and-trigger.sh  inotifywait → Airflow REST API
│
├── services/
│   ├── inference/
│   │   ├── app/main.py               FastAPI: /predict /forecast /recommend /models /metrics
│   │   ├── app/model_loader.py       MLflow lazy loading + sliding-window inference
│   │   └── requirements.txt
│   └── frontend_api/
│       ├── app.py                    JWT auth + history + sensor/inference bridge
│       └── requirements.txt
│
└── ui/svelte/
    ├── src/App.svelte                Auth-gated router (hash-based, no extra deps)
    ├── src/lib/stores.js             Auth, page, live sensor, risk history stores
    ├── src/lib/api.js                All API calls (auth, sensor, inference, history)
    ├── src/components/               Navbar, SensorCard, RiskGauge (SVG), LineChart (SVG)
    ├── src/pages/                    Dashboard, History, Predict, Forecast, Login, Register
    ├── package.json                  Svelte 4 + Vite (no chart library dep — pure SVG)
    └── .env.example                  VITE_FRONTEND_API_URL / VITE_SENSOR_API_URL template
```
