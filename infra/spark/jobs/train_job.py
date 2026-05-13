from __future__ import annotations

import json
import os
import pathlib
from tempfile import TemporaryDirectory

import boto3
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import PCA
from sklearn.ensemble import (GradientBoostingClassifier, IsolationForest,
                               RandomForestClassifier)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, f1_score, precision_score, recall_score,
                              roc_auc_score, brier_score_loss,
                              mean_absolute_error, r2_score)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline as SKPipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


# ── S3 / MinIO helpers ────────────────────────────────────────────────────────

def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minio"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minio123"),
    )


def _download_feature_file(s3_key: str, target_path: pathlib.Path) -> pathlib.Path:
    _s3_client().download_file("features", s3_key, str(target_path))
    return target_path


def _download_first_matching(prefix: str, suffix: str, target_path: pathlib.Path) -> pathlib.Path:
    s3 = _s3_client()
    resp = s3.list_objects_v2(Bucket="features", Prefix=prefix)
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if key.endswith(suffix):
            s3.download_file("features", key, str(target_path))
            return target_path
    raise FileNotFoundError(f"No file found under s3://features/{prefix} ending with {suffix}")


def _maybe_promote_alias(
    model_name: str, new_version: str, metric_name: str, metric_value: float
) -> None:
    mode = os.getenv("MODEL_PROMOTION_MODE", "manual").lower()
    client = MlflowClient()

    if mode != "auto":
        print(f"MODEL_PROMOTION_MODE={mode}, skipping alias promotion")
        return

    best = None
    for mv in client.search_model_versions(f"name='{model_name}'"):
        run = client.get_run(mv.run_id)
        m = run.data.metrics.get(metric_name)
        if m is not None and (best is None or m > best[0]):
            best = (m, mv.version)

    if best is None or metric_value >= best[0]:
        client.set_registered_model_alias(model_name, "champion", new_version)
        print(f"Promoted version {new_version} to @champion ({model_name})")


# ── Sliding window helper ─────────────────────────────────────────────────────

def _create_windows(df_in: pd.DataFrame, feature_cols: list[str],
                    label_col: str, window_size: int = 12,
                    horizon: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Flattened window + per-sensor mean, std, and trend (last minus first).

    All statistics are derived from past data only — no pre-aggregated _max or
    _roll columns needed.  Training and inference use exactly the same feature
    construction path (mirrors create_sliding_windows in 02_models.ipynb).
    """
    arr    = df_in[feature_cols].to_numpy(dtype=np.float32)
    labels = df_in[label_col].to_numpy(dtype=np.int32)
    X, y = [], []
    for i in range(window_size, len(df_in) - horizon + 1):
        window  = arr[i - window_size : i]          # (window_size, n_sensors)
        flat    = window.flatten()
        w_mean  = window.mean(axis=0)
        w_std   = window.std(axis=0)
        w_trend = window[-1] - window[0]            # directional change over window
        X.append(np.concatenate([flat, w_mean, w_std, w_trend]))
        y.append(labels[i + horizon - 1])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def _log_clf_metrics(y_true, y_pred, y_score) -> dict:
    f1     = f1_score(y_true, y_pred, zero_division=0)
    prec   = precision_score(y_true, y_pred, zero_division=0)
    rec    = recall_score(y_true, y_pred, zero_division=0)
    auc    = roc_auc_score(y_true, y_score) if len(np.unique(y_true)) > 1 else 0.5
    brier  = brier_score_loss(y_true, np.clip(y_score, 0, 1)) if len(np.unique(y_true)) > 1 else 0.5
    mlflow.log_metrics({
        "f1_anomaly":        float(f1),
        "precision_anomaly": float(prec),
        "recall_anomaly":    float(rec),
        "roc_auc_anomaly":   float(auc),
        "brier_score":       float(brier),
    })
    return {"f1_anomaly": f1, "precision_anomaly": prec,
            "recall_anomaly": rec, "roc_auc_anomaly": auc, "brier_score": brier}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("plant_alarm_training")

    model_name    = os.getenv("MODEL_NAME", "plant_alarm_champion")
    promote_metric = os.getenv("MODEL_PROMOTION_METRIC", "f1_anomaly")

    SENSOR_COLS = [
        "te301020", "pdt31008", "pdt31001", "pdt31007",
        "fq31050", "lt301031", "lic31012_pv", "lic31002_pv", "fic31011_pv",
    ]

    # Point-in-time features: instantaneous sensor readings only.
    # failure_frequency_48 excluded: it is a rolling sum of past anomaly_labels
    # and so strongly correlated with the target that it dominates all other
    # features, making the model insensitive to current sensor values.
    # Excluded: _max/_min (intra-hour aggregates unavailable at inference),
    # _roll* from original CSV (unknown computation window).
    POINT_FEATURES = [
        "te301020", "pdt31008", "pdt31001", "pdt31007",
        "fq31050", "lt301031", "lic31012_pv", "lic31002_pv", "fic31011_pv",
        "lic31012_op", "lic31002_op", "fic31011_op",
        "lic31012_deviation", "lic31002_deviation", "fic31011_deviation",
        "hour_of_day", "day_of_week",
    ]

    with TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        train_file = _download_feature_file("latest/train_smote.parquet", tmp / "train_smote.parquet")
        valid_file = _download_first_matching("latest/valid/", ".parquet", tmp / "valid.parquet")

        train_df = pd.read_parquet(train_file)
        valid_df = pd.read_parquet(valid_file)

        if "timestamp" in train_df.columns:
            train_df = train_df.drop(columns=["timestamp"])
        if "timestamp" in valid_df.columns:
            valid_df = valid_df.drop(columns=["timestamp"])

        y_train = train_df["anomaly_label"].astype(int)
        y_valid = valid_df["anomaly_label"].astype(int)
        available = [c for c in POINT_FEATURES if c in train_df.columns]
        X_train = train_df[available]
        X_valid = valid_df[available]

        # ── Dataset registration ──────────────────────────────────────────────
        combined_df = pd.concat([train_df, valid_df], ignore_index=True)
        dataset_ref = mlflow.data.from_pandas(
            combined_df,
            name="plant_alarm_features",
            source="s3://features/latest",
        )

        # ── 1. Isolation Forest ───────────────────────────────────────────────
        iso = IsolationForest(
            n_estimators=300,
            contamination=float(y_train.mean()),
            random_state=42,
        )
        with mlflow.start_run(run_name="isolation_forest"):
            mlflow.log_input(dataset_ref, context="training")
            mlflow.log_params({"model_type": "isolation_forest",
                               "n_estimators": 300,
                               "contamination": float(round(y_train.mean(), 4))})
            iso.fit(X_train)
            pred   = (iso.predict(X_valid) == -1).astype(int)
            scores = -iso.decision_function(X_valid)
            metrics = _log_clf_metrics(y_valid, pred, scores)
            mlflow.sklearn.log_model(iso, artifact_path="model",
                                     registered_model_name="plant_alarm_isolation_forest")
            _report(tmp, "isolation_forest", metrics)
            _maybe_promote_alias("plant_alarm_isolation_forest",
                                 _latest_version("plant_alarm_isolation_forest"),
                                 promote_metric, float(metrics[promote_metric]))

        # ── 2. Gradient Boosting champion candidate ───────────────────────────
        # Shallow trees (max_depth=3) + min_samples_leaf=10 prevent leaf
        # memorisation. GBM's additive structure produces smooth sigmoid-like
        # probability curves without a separate calibration step, avoiding the
        # 0%/100% binary jumps that deep Random Forests produce.
        gb_pipe = SKPipeline([
            ("scaler", StandardScaler()),
            ("gb", GradientBoostingClassifier(
                n_estimators=150,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.8,
                min_samples_leaf=10,
                random_state=42,
            )),
        ])
        with mlflow.start_run(run_name="gradient_boosting"):
            mlflow.log_input(dataset_ref, context="training")
            mlflow.log_params({"model_type": "gradient_boosting",
                               "n_estimators": 150, "max_depth": 3,
                               "learning_rate": 0.05, "min_samples_leaf": 10,
                               "feature_count": len(available)})
            gb_pipe.fit(X_train, y_train)
            pred   = gb_pipe.predict(X_valid)
            scores = gb_pipe.predict_proba(X_valid)[:, 1]
            metrics = _log_clf_metrics(y_valid, pred, scores)
            mlflow.sklearn.log_model(gb_pipe, artifact_path="model",
                                     registered_model_name=model_name)
            _report(tmp, "gradient_boosting", metrics)
            _maybe_promote_alias(model_name, _latest_version(model_name),
                                 promote_metric, float(metrics[promote_metric]))

        # ── 3. Calibrated XGBoost champion candidate ──────────────────────────
        # Shallow trees (max_depth=3) + min_child_weight=10 prevent leaf-level
        # memorisation. Sigmoid calibration via TimeSeriesSplit corrects the
        # well-known XGBoost extreme-probability bias on small datasets.
        xgb_cal = SKPipeline([
            ("scaler", StandardScaler()),
            ("xgb_cal", CalibratedClassifierCV(
                XGBClassifier(
                    n_estimators=200, max_depth=3, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    min_child_weight=10,
                    eval_metric="logloss", random_state=42,
                ),
                method="sigmoid",
                cv=TimeSeriesSplit(n_splits=3),
            )),
        ])
        with mlflow.start_run(run_name="xgboost_calibrated"):
            mlflow.log_input(dataset_ref, context="training")
            mlflow.log_params({"model_type": "xgboost_calibrated",
                               "n_estimators": 200, "max_depth": 3,
                               "calibration": "sigmoid",
                               "feature_count": len(available)})
            xgb_cal.fit(X_train, y_train)
            pred   = xgb_cal.predict(X_valid)
            scores = xgb_cal.predict_proba(X_valid)[:, 1]
            metrics = _log_clf_metrics(y_valid, pred, scores)
            mlflow.sklearn.log_model(xgb_cal, artifact_path="model",
                                     registered_model_name=model_name)
            _report(tmp, "xgboost_calibrated", metrics)
            _maybe_promote_alias(model_name, _latest_version(model_name),
                                 promote_metric, float(metrics[promote_metric]))

        # ── 3b. LR soft alarm (binary, calibrated via sigmoid) ───────────────
        # sklearn Pipeline bundles StandardScaler so inference receives raw
        # features and scaling is applied transparently inside the model.
        # Replaces uncalibrated XGBoost which produces 0%/100% probabilities
        # on this small dataset (673 rows, max_depth=5 → tiny leaves).
        lr_alarm = SKPipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(
                C=0.5, solver="lbfgs", max_iter=2000,
                class_weight="balanced", random_state=42,
            )),
        ])
        with mlflow.start_run(run_name="lr_soft_alarm"):
            mlflow.log_input(dataset_ref, context="training")
            mlflow.log_params({"model_type": "lr_soft_alarm", "C": 0.5,
                               "class_weight": "balanced",
                               "feature_count": len(available)})
            lr_alarm.fit(X_train, y_train)
            pred_lr   = lr_alarm.predict(X_valid)
            scores_lr = lr_alarm.predict_proba(X_valid)[:, 1]
            metrics_lr = _log_clf_metrics(y_valid, pred_lr, scores_lr)
            mlflow.sklearn.log_model(lr_alarm, artifact_path="model",
                                     registered_model_name="plant_alarm_lr_soft_alarm")
            _report(tmp, "lr_soft_alarm", metrics_lr)

        # ── 3c. Calibrated RF soft alarm (isotonic calibration) ───────────────
        # CalibratedClassifierCV(isotonic) rescales RF leaf-proportion
        # probabilities using held-out time-series folds, removing the
        # extreme-probability bias.  Bundled with scaler in a Pipeline.
        rf_alarm = SKPipeline([
            ("scaler", StandardScaler()),
            ("rf_cal", CalibratedClassifierCV(
                RandomForestClassifier(
                    n_estimators=300, max_depth=5, min_samples_leaf=8,
                    class_weight="balanced", random_state=42, n_jobs=-1,
                ),
                method="isotonic",
                cv=TimeSeriesSplit(n_splits=3),
            )),
        ])
        with mlflow.start_run(run_name="rf_soft_alarm"):
            mlflow.log_input(dataset_ref, context="training")
            mlflow.log_params({"model_type": "rf_soft_alarm_calibrated",
                               "n_estimators": 300, "max_depth": 5,
                               "min_samples_leaf": 8, "calibration": "isotonic",
                               "feature_count": len(available)})
            rf_alarm.fit(X_train, y_train)
            pred_rf   = rf_alarm.predict(X_valid)
            scores_rf = rf_alarm.predict_proba(X_valid)[:, 1]
            metrics_rf = _log_clf_metrics(y_valid, pred_rf, scores_rf)
            mlflow.sklearn.log_model(rf_alarm, artifact_path="model",
                                     registered_model_name="plant_alarm_rf_soft_alarm")
            _report(tmp, "rf_soft_alarm", metrics_rf)
            # Also compete for the champion slot — calibrated RF often wins on AUC
            mlflow.sklearn.log_model(rf_alarm, artifact_path="model_champion_copy",
                                     registered_model_name=model_name)
            _maybe_promote_alias(model_name, _latest_version(model_name),
                                 promote_metric, float(metrics_rf[promote_metric]))

        # ── 3d. LR multinomial regime classifier ──────────────────────────────
        # 3-class: Normal=0 / Transition=1 / Alarm=2.
        # LR with sigmoid boundary gives smooth, calibrated class probabilities —
        # avoids the extreme 0%/100% outputs of XGBoost on this dataset size.
        # SMOTE may produce fractional regime labels via interpolation; round to
        # the nearest integer class before training.
        if "regime" in train_df.columns and "regime" in valid_df.columns:
            y_train_r = train_df["regime"].round().astype(int).values
            y_valid_r  = valid_df["regime"].round().astype(int).values
            lr_regime = SKPipeline([
                ("scaler", StandardScaler()),
                ("lr", LogisticRegression(
                    C=1.0, multi_class="multinomial", solver="lbfgs",
                    max_iter=2000, class_weight="balanced", random_state=42,
                )),
            ])
            with mlflow.start_run(run_name="regime_classifier"):
                mlflow.log_input(dataset_ref, context="training")
                mlflow.log_params({"model_type": "lr_multinomial", "C": 1.0,
                                   "class_weight": "balanced",
                                   "feature_count": len(available)})
                lr_regime.fit(X_train, y_train_r)
                pred_r   = lr_regime.predict(X_valid)
                f1_r     = f1_score(y_valid_r, pred_r, average="macro", zero_division=0)
                acc_r    = accuracy_score(y_valid_r, pred_r)
                mlflow.log_metrics({"f1_macro": float(f1_r), "accuracy": float(acc_r)})
                mlflow.sklearn.log_model(lr_regime, artifact_path="model",
                                         registered_model_name="plant_alarm_regime_classifier")
                _report(tmp, "regime_classifier", {"f1_macro": f1_r, "accuracy": acc_r})

        # ── 4. Ridge deviation forecaster (t+1h) ──────────────────────────────
        # Target: lic31002_deviation shifted by -1 = next hour's instantaneous
        # SP-PV deviation.  No intra-hour aggregate leakage; Ridge is well-suited
        # to this small dataset size.
        all_df = pd.concat([train_df, valid_df], ignore_index=True)
        reg_feats = [c for c in POINT_FEATURES if c in all_df.columns]
        if "lic31002_deviation" in all_df.columns and len(reg_feats) > 0:
            target_dev  = all_df["lic31002_deviation"].shift(-1).dropna()
            valid_rows  = target_dev.index
            X_reg_all   = all_df.loc[valid_rows, reg_feats].values
            y_reg_all   = target_dev.values

            split_n     = int(len(y_reg_all) * 0.75)
            scaler_reg  = StandardScaler()
            X_reg_tr_s  = scaler_reg.fit_transform(X_reg_all[:split_n])
            X_reg_te_s  = scaler_reg.transform(X_reg_all[split_n:])
            y_reg_tr    = y_reg_all[:split_n]
            y_reg_te    = y_reg_all[split_n:]

            regressor = Ridge(alpha=1.0)
            with mlflow.start_run(run_name="deviation_predictor"):
                mlflow.log_input(dataset_ref, context="training")
                mlflow.log_params({"model_type": "ridge", "alpha": 1.0,
                                   "target": "lic31002_deviation_t_plus_1h",
                                   "feature_count": len(reg_feats)})
                regressor.fit(X_reg_tr_s, y_reg_tr)
                y_pred_reg = regressor.predict(X_reg_te_s)
                mlflow.log_metrics({
                    "mae": float(mean_absolute_error(y_reg_te, y_pred_reg)),
                    "r2":  float(r2_score(y_reg_te, y_pred_reg)),
                })
                mlflow.sklearn.log_model(regressor, artifact_path="model",
                                         registered_model_name="plant_alarm_deviation_predictor")

        # ── 5. PCA (process correlation) ──────────────────────────────────────
        sensor_cols_present = [c for c in SENSOR_COLS if c in all_df.columns]
        if sensor_cols_present:
            scaler_pca = StandardScaler()
            X_pca = scaler_pca.fit_transform(all_df[sensor_cols_present].values)
            pca = PCA(n_components=len(sensor_cols_present), random_state=42)
            pca.fit(X_pca)
            explained   = pca.explained_variance_ratio_
            cumulative  = np.cumsum(explained)
            n_90        = int(np.argmax(cumulative >= 0.90) + 1)

            with mlflow.start_run(run_name="pca_correlation"):
                mlflow.log_input(dataset_ref, context="training")
                mlflow.log_params({"model_type": "pca",
                                   "n_sensors": len(sensor_cols_present),
                                   "n_components_90pct": n_90})
                mlflow.log_metrics({f"explained_var_pc{i+1}": float(v)
                                    for i, v in enumerate(explained)})
                mlflow.sklearn.log_model(pca, artifact_path="model",
                                         registered_model_name="plant_alarm_pca")
                loadings_path = tmp / "pca_loadings.json"
                loadings_path.write_text(
                    json.dumps({"sensor_cols": sensor_cols_present,
                                "components": pca.components_.tolist()}, indent=2)
                )
                mlflow.log_artifact(str(loadings_path), artifact_path="reports")

        # ── 6. Sliding-window forecasters (calibrated) ────────────────────────
        # max_depth=3 + min_child_weight=10 prevent leaf-level memorisation.
        # CalibratedClassifierCV(isotonic) rescales leaf probabilities using
        # held-out folds — eliminates the 0%/100% extreme-probability bias.
        window_df = all_df.copy()
        for h in [1, 3, 6]:
            sensor_present = [c for c in SENSOR_COLS if c in window_df.columns]
            if not sensor_present:
                continue
            X_w, y_w = _create_windows(window_df, sensor_present, "anomaly_label",
                                        window_size=12, horizon=h)
            split_w = int(len(X_w) * 0.8)
            X_tr_w, X_te_w = X_w[:split_w], X_w[split_w:]
            y_tr_w, y_te_w = y_w[:split_w], y_w[split_w:]

            base = XGBClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.7, min_child_weight=10,
                scale_pos_weight=float(max(1, (y_tr_w == 0).sum()) /
                                       max(1, (y_tr_w == 1).sum())),
                eval_metric="logloss", random_state=42,
            )
            fc = CalibratedClassifierCV(base, method="isotonic",
                                        cv=TimeSeriesSplit(n_splits=3))
            fc_name = f"plant_alarm_forecaster_{h}h"
            with mlflow.start_run(run_name=f"forecaster_{h}h"):
                mlflow.log_input(dataset_ref, context="training")
                mlflow.log_params({
                    "model_type":       "xgboost_calibrated",
                    "window_size_hours": 12,
                    "horizon_hours":    h,
                    "max_depth":        3,
                    "min_child_weight": 10,
                    "calibration":      "isotonic",
                    "n_window_sensors": len(sensor_present),
                    "n_window_features": X_w.shape[1],
                    "window_stats":     "mean,std,trend",
                })
                fc.fit(X_tr_w, y_tr_w)
                pred_w   = fc.predict(X_te_w)
                scores_w = fc.predict_proba(X_te_w)[:, 1]
                fc_metrics = _log_clf_metrics(y_te_w, pred_w, scores_w)
                mlflow.sklearn.log_model(fc, artifact_path="model",
                                         registered_model_name=fc_name)
                feat_path = tmp / f"forecaster_{h}h_features.json"
                feat_path.write_text(json.dumps({
                    "window_size": 12,
                    "horizon": h,
                    "sensor_cols": sensor_present,
                    "window_stats": "mean,std,trend",
                }, indent=2))
                mlflow.log_artifact(str(feat_path), artifact_path="reports")
                _maybe_promote_alias(fc_name, _latest_version(fc_name),
                                     promote_metric, float(fc_metrics[promote_metric]))

        print("Training complete — all models registered in MLflow.")


def _latest_version(model_name: str) -> str:
    client = MlflowClient()
    versions = client.get_latest_versions(model_name)
    if not versions:
        return "1"
    return max(versions, key=lambda v: int(v.version)).version


def _report(tmp: pathlib.Path, name: str, metrics: dict) -> None:
    p = tmp / f"{name}_metrics.json"
    p.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    mlflow.log_artifact(str(p), artifact_path="reports")


if __name__ == "__main__":
    main()
