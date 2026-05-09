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
8. [Docker / Podman Interchangeability](#8-docker--podman-interchangeability)
9. [Configuration Reference](#9-configuration-reference)
10. [Key Files](#10-key-files)

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
| ML Infra | `prometheus` / `grafana` | Prom + Grafana | Inference metrics dashboards |
| Frontend | `mock-sensor-api` | FastAPI | Simulated live plant sensor data |
| Frontend | `frontend-api` | FastAPI + SQLite | JWT auth, inference history, live bridge |
| Frontend | `inference-api` | FastAPI + MLflow | ML model serving (point-in-time + forecast) |
| Frontend | `svelte-ui` | Svelte 4 + Vite | Browser UI — dashboard, history, predict |

### Data models

Nine instruments across two process units:
`te301020` (°C) · `pdt31008` (mbar) · `pdt31001` (mbar) · `pdt31007` (mbar) ·
`fq31050` (m³/h) · `lt301031` (%) · `lic31012_pv` (%) · `lic31002_pv` (%) · `fic31011_pv` (m³/h)

---

## 2. Quick Start

### Prerequisites

- Docker or Podman (see [§8](#8-docker--podman-interchangeability) for differences)
- `docker compose` v2 **or** `podman-compose` ≥ 1.0 (`pip install podman-compose`)
- 8 GB RAM available (Spark + Airflow are the heavy hitters)
- For notebooks only (no containers): Python ≥ 3.11

### Option A — Full ML stack + frontend (recommended)

```bash
# 1. Copy env template
cp infra/.env.example infra/.env       # bash/mac
# or
Copy-Item infra/.env.example infra/.env   # PowerShell

# 2. Start the frontend demo stack (no heavy infra required)
docker compose -f infra/compose.frontend.yml up -d
# → Svelte UI: http://localhost:5173
# → frontend-api: http://localhost:7501
# → mock-sensor-api: http://localhost:7500
# → inference-api: http://localhost:7502  (models load when MLflow is reachable)

# 3. Start the ML infrastructure (postgres, minio, mlflow, airflow, spark)
docker compose --env-file infra/.env -f infra/compose.yml up -d \
    postgres minio minio_bootstrap mlflow \
    airflow-init airflow-webserver airflow-scheduler \
    spark-master spark-worker file-watcher \
    prometheus grafana
```

### Option B — Notebooks only (no containers)

```bash
pip install mlflow xgboost lightgbm scikit-learn imbalanced-learn pandas numpy
# Open notebooks in order: 01_eda → 02_models → 03_validation
```

### Makefile shortcuts (Docker / Podman switchable)

```bash
make init            # copy .env.example → infra/.env
make up              # start full stack (docker)
make up ENGINE=podman   # start full stack (podman-compose)
make down
make logs
make ps
```

---

## 3. Service URLs

### ML Infrastructure stack

| Service | URL | Default credentials |
|---------|-----|---------------------|
| MLflow | http://localhost:5000 | — |
| Airflow | http://localhost:8080 | `admin` / `admin` |
| MinIO Console | http://localhost:9001 | `minio` / `minio123` |
| Grafana | http://localhost:3000 | `admin` / `admin` |
| Prometheus | http://localhost:9090 | — |
| Spark Master UI | http://localhost:8081 | — |

> **Windows / Hyper-V note:** Ports 7914–8813 are reserved by Hyper-V on most Windows 10/11
> machines. If Airflow (8080) or Spark UI (8081) are inaccessible, use the CLI instead of the
> browser. See [§8](#8-docker--podman-interchangeability) for details.

### Frontend stack

| Service | URL | Notes |
|---------|-----|-------|
| Svelte UI | http://localhost:5173 | Main browser UI |
| Frontend API | http://localhost:7501 | Auth + history + inference bridge |
| Mock Sensor API | http://localhost:7500 | Simulated live sensor data |
| Inference API | http://localhost:7502 | ML model endpoints |

> Port range 7500–7502 is used specifically to avoid the Hyper-V exclusion zone on Windows.

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
of the heavy ML infrastructure. It brings up four services:

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
| `GET /models` | Lists all expected models and their load status |
| `GET /metrics` | Prometheus metrics |

Set `MLFLOW_TRACKING_URI` in `infra/compose.frontend.yml` (or `infra/.env`) to point the
inference-api at a running MLflow instance. When MLflow is unreachable the API still starts
and returns `503` for model-dependent endpoints — the UI shows the error gracefully.

### Svelte UI (`ui/svelte/`) — port 5173

Four pages, auth-gated (JWT stored in `localStorage`):

| Page | Description |
|------|-------------|
| **Dashboard** | Live 9-sensor grid (2 s poll), scenario switcher, auto-inference toggle, real-time risk chart |
| **History** | Table + SVG risk-over-time chart of all past inferences, filterable by type |
| **Predict** | Manual point-in-time prediction form (normal + high-risk presets) |
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

## 8. Docker / Podman Interchangeability

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

### Internet access for containers (rootful Podman on WSL2)

In rootful Podman mode on WSL2, newly created bridge networks may not have a masquerade
(NAT) rule for outbound internet traffic. Symptom: `pip install` inside a container fails
with `Network is unreachable`.

Diagnosis and fix:
```bash
# Check masquerade rules inside WSL2
podman machine ssh -- "nft list chain ip nat POSTROUTING"

# Add the missing rule if absent (replace 10.89.1.0/24 with your bridge subnet)
podman machine ssh -- "nft add rule ip nat POSTROUTING ip saddr 10.89.1.0/24 oifname eth0 masquerade"
```

In **rootless** mode this does not occur — outbound traffic is handled via `pasta`
(user-space networking) which always has internet access.

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

## 9. Configuration Reference

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

## 10. Key Files

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
│   ├── compose.frontend.yml          Lightweight frontend demo (4 services)
│   ├── .env.example                  Environment variable template
│   ├── airflow/dags/
│   │   ├── ingest_etl_dag.py         File-drop → validation → PySpark ETL
│   │   └── train_dag.py              Manual training trigger
│   ├── spark/jobs/
│   │   ├── etl_job.py                SMOTE + rolling features + MinIO upload
│   │   └── train_job.py              Train 8 models, register in MLflow
│   ├── great_expectations/           Data quality gate (6 expectations)
│   ├── grafana/                      Provisioned "Plant Alarm Risk Overview" dashboard
│   ├── prometheus/prometheus.yml     Scrape config (inference-api every 15 s)
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
