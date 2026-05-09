#!/bin/sh
set -eu

WATCH_DIR=${WATCH_DIR:-/watch}
AIRFLOW_URL=${AIRFLOW_URL:-http://airflow-webserver:8080}
AIRFLOW_USER=${AIRFLOW_ADMIN_USER:-admin}
AIRFLOW_PASS=${AIRFLOW_ADMIN_PASSWORD:-admin}
DAG_ID=${INGEST_DAG_ID:-ingest_etl_local_drop}

echo "Watching $WATCH_DIR for new CSV/XLS/XLSX files..."
inotifywait -m -e close_write,create --format '%w%f' "$WATCH_DIR" | while read -r file; do
  case "$file" in
    *.csv|*.CSV|*.xls|*.xlsx)
      echo "Detected file: $file"
      # Translate /watch/ (watcher mount) to /workspace/data_drop/ (Airflow mount).
      af_path=$(echo "$file" | sed 's|^/watch/|/workspace/data_drop/|')
      payload=$(printf '{"conf":{"source_path":"%s"}}' "$af_path")
      curl -s -u "$AIRFLOW_USER:$AIRFLOW_PASS" \
        -H "Content-Type: application/json" \
        -X POST "$AIRFLOW_URL/api/v1/dags/$DAG_ID/dagRuns" \
        -d "$payload" || true
      ;;
    *)
      ;;
  esac
done