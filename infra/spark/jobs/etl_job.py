from __future__ import annotations

import argparse
import os
import pathlib
import shutil
from datetime import datetime

import boto3
import pandas as pd
from imblearn.over_sampling import SMOTE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-root", default="/workspace/data_lake/features")
    return parser.parse_args()


def upload_dir_to_minio(local_dir: pathlib.Path, bucket: str, prefix: str) -> None:
    endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://minio:9000")
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "minio")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    for file in local_dir.rglob("*"):
        if file.is_file():
            relative = file.relative_to(local_dir).as_posix()
            s3_key = f"{prefix}/{relative}"
            s3.upload_file(str(file), bucket, s3_key)


SENSOR_COLS = [
    "te301020", "pdt31008", "pdt31001", "pdt31007",
    "fq31050", "lt301031", "lic31012_pv", "lic31002_pv", "fic31011_pv",
]
WINDOW_SIZE = 12
HORIZONS    = [1, 3, 6]


def _build_window_parquets(df_pd: pd.DataFrame, output_dir: pathlib.Path) -> None:
    """Write sliding-window parquets with the same feature layout as training.

    Each row = flattened raw window (WINDOW_SIZE × n_sensors) +
               per-sensor mean, std, trend (last minus first).
    Mirrors _create_windows() in train_job.py and create_sliding_windows()
    in 02_models.ipynb so any downstream consumer sees a consistent schema.
    """
    sensor_cols = [c for c in SENSOR_COLS if c in df_pd.columns]
    if not sensor_cols or "anomaly_label" not in df_pd.columns:
        return

    df_sorted = (
        df_pd.sort_values("timestamp").reset_index(drop=True)
        if "timestamp" in df_pd.columns
        else df_pd.reset_index(drop=True)
    )

    arr    = df_sorted[sensor_cols].to_numpy(dtype="float32")
    labels = df_sorted["anomaly_label"].to_numpy(dtype="int32")

    raw_col_names  = [f"{s}_t{-(WINDOW_SIZE - 1 - j)}"
                      for j in range(WINDOW_SIZE) for s in sensor_cols]
    stat_col_names = ([f"{s}_wmean"  for s in sensor_cols] +
                      [f"{s}_wstd"   for s in sensor_cols] +
                      [f"{s}_wtrend" for s in sensor_cols])
    all_col_names  = raw_col_names + stat_col_names + ["anomaly_label"]

    for h in HORIZONS:
        rows = []
        for i in range(WINDOW_SIZE, len(df_sorted) - h + 1):
            window  = arr[i - WINDOW_SIZE : i]      # (WINDOW_SIZE, n_sensors)
            flat    = window.flatten().tolist()
            w_mean  = window.mean(axis=0).tolist()
            w_std   = window.std(axis=0).tolist()
            w_trend = (window[-1] - window[0]).tolist()   # directional change
            target  = int(labels[i + h - 1])
            rows.append(flat + w_mean + w_std + w_trend + [target])

        win_df = pd.DataFrame(rows, columns=all_col_names)
        out_path = output_dir / f"windows_{h}h.parquet"
        win_df.to_parquet(out_path, index=False)


def main() -> None:
    args = parse_args()
    input_path = args.input_path
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    df = pd.read_csv(input_path)

    # Normalize column names.
    df.columns = [c.strip().lower() for c in df.columns]

    if "timestamp" not in df.columns:
        raise ValueError("Input file must contain a timestamp column")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    # Cast non-timestamp columns to float.
    for col in df.columns:
        if col == "timestamp":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Deduplicate by timestamp, keeping last occurrence.
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    df = df.reset_index(drop=True)

    # Fill nulls in numeric columns with zero for consistent modeling input.
    num_cols = [c for c in df.columns if c != "timestamp"]
    df[num_cols] = df[num_cols].fillna(0.0)

    # --- Controller deviations (SP − PV, matching 02_models.ipynb convention) ─
    # Must be computed AFTER the null-fill so SP/PV columns exist.
    # LIC31012 SP is physically constant at 80 %; the null-fill above may have
    # zeroed it — restore the physical constant before computing deviation.
    if "lic31012_sp" in df.columns:
        df["lic31012_sp"] = df["lic31012_sp"].mask(df["lic31012_sp"] == 0.0, 80.0)

    for ctrl in ["lic31012", "lic31002", "fic31011"]:
        pv_col, sp_col, dev_col = f"{ctrl}_pv", f"{ctrl}_sp", f"{ctrl}_deviation"
        if pv_col in df.columns and sp_col in df.columns and dev_col not in df.columns:
            df[dev_col] = df[sp_col] - df[pv_col]

    # --- Time features (required by POINT_FEATURES in train_job.py) ─────────
    if "hour_of_day" not in df.columns:
        df["hour_of_day"] = df["timestamp"].dt.hour.astype("float32")
    if "day_of_week" not in df.columns:
        df["day_of_week"] = df["timestamp"].dt.dayofweek.astype("float32")

    # Rolling 3-hour proxy (12-row window) on key sensors when present.
    rolling_sources = [
        c for c in ["pdt31008", "lic31002_pv", "fic31011_pv", "te301020"]
        if c in df.columns
    ]
    for c in rolling_sources:
        df[f"{c}_roll_mean"] = df[c].rolling(window=13, min_periods=1).mean()
        df[f"{c}_roll_std"]  = df[c].rolling(window=13, min_periods=1).std().fillna(0.0)

    # Failure frequency feature from labels.
    if "anomaly_label" not in df.columns:
        df["anomaly_label"] = 0.0
    df["failure_frequency_48"] = df["anomaly_label"].rolling(window=49, min_periods=1).sum()

    # Temporal 80/20 train / validation split.
    df = df.sort_values("timestamp").reset_index(drop=True)
    split_index = int(len(df) * 0.8)
    train_df = df.iloc[:split_index].copy()
    valid_df  = df.iloc[split_index:].copy()

    output_root = pathlib.Path(args.output_root)
    latest_dir  = output_root / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)

    train_dir = latest_dir / "train"
    valid_dir = latest_dir / "valid"
    train_dir.mkdir()
    valid_dir.mkdir()
    train_df.to_parquet(train_dir / "part-0.parquet", index=False)
    valid_df.to_parquet(valid_dir  / "part-0.parquet", index=False)

    # SMOTE oversampling on the training split only.
    train_no_ts = train_df.drop(columns=["timestamp"])
    y = train_no_ts["anomaly_label"].astype(int)
    X = train_no_ts.drop(columns=["anomaly_label"])

    if y.nunique() > 1 and y.value_counts().min() >= 2:
        smote = SMOTE(random_state=42)
        X_smote, y_smote = smote.fit_resample(X, y)
        train_smote = pd.concat(
            [X_smote, pd.Series(y_smote, name="anomaly_label")], axis=1
        )
    else:
        train_smote = pd.concat([X, y.rename("anomaly_label")], axis=1)

    train_smote.to_parquet(latest_dir / "train_smote.parquet", index=False)

    # Sliding-window parquets for forecaster training.
    _build_window_parquets(train_no_ts, latest_dir)

    # Upload artifacts to MinIO for downstream training jobs.
    upload_dir_to_minio(latest_dir, "features", f"runs/{run_id}")
    upload_dir_to_minio(latest_dir, "features", "latest")

    print(f"ETL complete — {len(train_df)} train rows, {len(valid_df)} valid rows.")


if __name__ == "__main__":
    main()
