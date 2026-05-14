from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

# Sensors required by the forecaster window models (must match ETL/training)
SENSOR_COLS = [
    "te301020", "pdt31008", "pdt31001", "pdt31007",
    "fq31050", "lt301031", "lic31012_pv", "lic31002_pv", "fic31011_pv",
]

# Decision threshold for converting risk_score → alarm flag.
# Override with ALARM_THRESHOLD env var (e.g. set to the val-set optimal value
# logged by train_job.py as mlflow metric "optimal_threshold").
_ALARM_THRESHOLD = float(os.getenv("ALARM_THRESHOLD", "0.5"))

# For rolling-mean features: when the caller does not supply the rolling stat,
# fall back to the corresponding instantaneous sensor reading (a reasonable
# approximation for a "stable" single-point snapshot).
_ROLL_MEAN_FALLBACK: dict[str, str] = {
    "pdt31008_roll_mean":   "pdt31008",
    "lt301031_roll_mean":   "lt301031",
    "lic31002_pv_roll_mean":"lic31002_pv",
    "fic31011_pv_roll_mean":"fic31011_pv",
    "te301020_roll_mean":   "te301020",
}
WINDOW_SIZE = 12


def _load_model(registry_name: str) -> Any:
    """Try @champion then /latest for a named registered model."""
    last_err = None
    for uri in [f"models:/{registry_name}@champion",
                f"models:/{registry_name}/latest"]:
        try:
            return mlflow.pyfunc.load_model(uri)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Could not load {registry_name}: {last_err}")


@lru_cache(maxsize=1)
def load_champion_model() -> Any:
    """Load the primary anomaly-detection champion (backward-compatible)."""
    model_name = os.getenv("MODEL_NAME", "plant_alarm_champion")
    return _load_model(model_name)


@lru_cache(maxsize=8)
def load_named_model(name: str) -> Any:
    """Load any registered model by name (cached per unique name)."""
    return _load_model(name)


def _expected_feature_names(model) -> list[str] | None:
    """Return the ordered feature list the model was trained on, or None."""
    # MLflow signature (most reliable)
    try:
        sig = model.metadata.signature
        if sig and sig.inputs:
            return [inp.name for inp in sig.inputs]
    except Exception:
        pass
    # sklearn / XGBoost feature_names_in_ stored on the underlying estimator
    try:
        impl = model._model_impl
        for attr in ("sklearn_model", "xgb_model", "_model"):
            underlying = getattr(impl, attr, None)
            if underlying is not None and hasattr(underlying, "feature_names_in_"):
                return list(underlying.feature_names_in_)
    except Exception:
        pass
    return None


def _score_from_model(model, frame: pd.DataFrame) -> float:
    """Extract a continuous [0, 1] probability from an MLflow pyfunc model.

    MLflow's pyfunc predict() for sklearn classifiers returns the class label
    (0 or 1), not a probability. We try predict_proba on the underlying
    sklearn object first; if unavailable, fall back to predict() which may
    still return a calibrated float for custom pyfunc flavors.

    Forecaster models were trained on unnamed numpy arrays, so if predict_proba
    fails with a named DataFrame (feature-name mismatch in XGBoost), we retry
    with frame.values to strip column names.
    """
    try:
        impl = model._model_impl
        for attr in ("sklearn_model", "xgb_model", "_model"):
            underlying = getattr(impl, attr, None)
            if underlying is not None and hasattr(underlying, "predict_proba"):
                try:
                    proba = underlying.predict_proba(frame)
                except Exception:
                    proba = underlying.predict_proba(frame.values)
                # proba shape: (n_samples, n_classes) — column 1 is P(alarm)
                return float(np.clip(proba[0, 1], 0.0, 1.0))
    except Exception:
        pass
    # Fallback: pyfunc predict — may be a calibrated float or 0/1
    pred = model.predict(frame)
    val = float(pred.tolist()[0]) if hasattr(pred, "tolist") else float(pred[0])
    return float(np.clip(val, 0.0, 1.0))


def _fill_feature_row(features: dict[str, float], expected: list[str]) -> dict[str, float]:
    """Build a feature dict with smart defaults for rolling/delta columns.

    - roll_mean features: default to the corresponding raw sensor reading
      (reasonable approximation when recent history is unavailable).
    - roll_std / delta features: default to 0.0 (assume stable / no change).
    - All other missing features: 0.0.
    """
    row: dict[str, float] = {}
    for col in expected:
        if col in features:
            row[col] = float(features[col])
        elif col in _ROLL_MEAN_FALLBACK:
            row[col] = float(features.get(_ROLL_MEAN_FALLBACK[col], 0.0))
        else:
            row[col] = 0.0
    return row


def _unwrap_tree_estimator(model) -> tuple:
    """Extract (preprocessor | None, final_tree_estimator | None) from any MLflow/sklearn wrapper.

    Handles:
      MLflow pyfunc → sklearn_model / xgb_model / _model attribute
      CalibratedClassifierCV → .calibrated_classifiers_[0].estimator
      sklearn Pipeline → split into [:-1] preprocessor and [-1] final step
    """
    impl = model._model_impl
    for attr in ("sklearn_model", "xgb_model", "_model"):
        underlying = getattr(impl, attr, None)
        if underlying is None:
            continue

        # Unwrap CalibratedClassifierCV
        if hasattr(underlying, "calibrated_classifiers_"):
            underlying = underlying.calibrated_classifiers_[0].estimator

        # Unwrap sklearn Pipeline
        if hasattr(underlying, "steps"):
            preprocessor = underlying[:-1]  # all steps except last
            final = underlying[-1]
        else:
            preprocessor = None
            final = underlying

        # Unwrap CalibratedClassifierCV that may be the Pipeline's final step
        if hasattr(final, "calibrated_classifiers_"):
            final = final.calibrated_classifiers_[0].estimator

        if hasattr(final, "feature_importances_") or hasattr(final, "predict"):
            return preprocessor, final

    return None, None


def get_global_importance() -> dict:
    """Return global feature importances from the champion model's feature_importances_ attribute."""
    try:
        model = load_champion_model()
        expected = _expected_feature_names(model)
        _, final = _unwrap_tree_estimator(model)
        if final is None or not hasattr(final, "feature_importances_"):
            return {"importances": [], "method": "unavailable"}

        importances = final.feature_importances_
        if expected and len(expected) == len(importances):
            names = expected
        else:
            names = [f"feature_{i}" for i in range(len(importances))]

        pairs = sorted(zip(names, importances.tolist()), key=lambda x: x[1], reverse=True)
        return {
            "importances": [{"feature": f, "importance": round(v, 6)} for f, v in pairs],
            "method": "feature_importances",
        }
    except Exception:
        return {"importances": [], "method": "unavailable"}


def explain_local(features: dict[str, float]) -> dict:
    """Compute local SHAP values for one prediction using the champion model.

    Uses TreeExplainer on the underlying tree estimator. If the model has a
    preprocessing Pipeline (e.g. StandardScaler), the input is transformed
    before SHAP computation so values are in the model's own feature space.
    Feature names are preserved throughout.
    """
    try:
        import shap as _shap  # deferred import — only needed for /explain calls
    except ImportError:
        return {"local_importance": [], "method": "unavailable", "error": "shap not installed"}

    try:
        model = load_champion_model()
        expected = _expected_feature_names(model)
        if expected is not None:
            row = _fill_feature_row(features, expected)
            frame = pd.DataFrame([row], columns=expected)
        else:
            frame = pd.DataFrame([features])

        preprocessor, final = _unwrap_tree_estimator(model)
        if final is None or not hasattr(final, "feature_importances_"):
            return {"local_importance": [], "method": "unavailable"}

        if preprocessor is not None:
            transformed = preprocessor.transform(frame)
            input_df = pd.DataFrame(transformed, columns=frame.columns)
        else:
            input_df = frame

        explainer = _shap.TreeExplainer(final)
        shap_raw = explainer.shap_values(input_df)
        base_raw = explainer.expected_value

        # SHAP 0.46+ returns ndarray (n_samples, n_features, n_classes) for classifiers.
        # Older SHAP returned list [neg_array, pos_array] each (n_samples, n_features).
        if isinstance(shap_raw, list):
            # Legacy list format — take P(alarm) class
            shap_row = np.asarray(shap_raw[1])[0]
            base_val = float(np.asarray(base_raw).flat[1])
        elif isinstance(shap_raw, np.ndarray) and shap_raw.ndim == 3:
            # New 3-D format: (n_samples, n_features, n_classes)
            shap_row = shap_raw[0, :, 1]
            base_val = float(np.asarray(base_raw).flat[1])
        else:
            # Regression / single-output: (n_samples, n_features)
            shap_row = np.asarray(shap_raw)[0]
            base_val = float(np.asarray(base_raw).flat[0])

        feature_names = list(frame.columns)
        feature_values = frame.iloc[0].tolist()
        items = [
            {"feature": fn, "value": round(float(fv), 4), "shap_value": round(float(sv), 6)}
            for fn, fv, sv in zip(feature_names, feature_values, shap_row)
        ]
        items.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

        return {"local_importance": items, "base_value": round(base_val, 6), "method": "shap_tree"}
    except Exception as exc:
        return {"local_importance": [], "method": "unavailable", "error": str(exc)}


def predict_risk(features: dict[str, float]) -> dict[str, float]:
    """Point-in-time risk prediction from a flat feature dict.

    Missing features use smart defaults (see _fill_feature_row); extra keys
    are silently ignored.
    """
    model = load_champion_model()
    expected = _expected_feature_names(model)
    if expected is not None:
        row = _fill_feature_row(features, expected)
        frame = pd.DataFrame([row], columns=expected)
    else:
        frame = pd.DataFrame([features])

    risk_score = _score_from_model(model, frame)
    return {"risk_score": risk_score, "alarm": 1 if risk_score >= _ALARM_THRESHOLD else 0}


def predict_forecast(
    recent_observations: list[dict[str, float]],
    horizon: int = 1,
) -> dict:
    """
    Sliding-window forecast: accepts the last WINDOW_SIZE rows of sensor readings
    and returns the anomaly probability at t+horizon.

    Args:
        recent_observations: list of dicts with sensor readings, oldest first.
                             Exactly WINDOW_SIZE entries required.
        horizon: 1, 3, or 6 (hours ahead).

    Returns:
        dict with anomaly_probability, alarm, horizon_hours, n_observations.
    """
    if len(recent_observations) < WINDOW_SIZE:
        raise ValueError(
            f"predict_forecast requires at least {WINDOW_SIZE} observations, "
            f"got {len(recent_observations)}."
        )

    # Take the most recent WINDOW_SIZE rows
    window_rows = recent_observations[-WINDOW_SIZE:]
    model_name = f"plant_alarm_forecaster_{horizon}h"
    fc_model = load_named_model(model_name)

    # Build flattened window feature vector + horizon-local stats per sensor.
    # Must mirror create_sliding_windows() in 02_models.ipynb / train_job.py:
    #   [raw flattened (WINDOW_SIZE × n_sensors)] + [mean, std, trend per sensor]
    # trend = last row minus first row in window (directional change)
    window_arr = np.zeros((WINDOW_SIZE, len(SENSOR_COLS)), dtype=np.float32)
    for t, row in enumerate(window_rows):
        for j, col in enumerate(SENSOR_COLS):
            window_arr[t, j] = float(row.get(col, 0.0))

    raw_flat = window_arr.flatten()
    w_mean   = window_arr.mean(axis=0)
    w_std    = window_arr.std(axis=0)
    w_trend  = window_arr[-1] - window_arr[0]   # directional change over window
    features = np.concatenate([raw_flat, w_mean, w_std, w_trend]).reshape(1, -1)

    raw_cols  = [f"{s}_t{-(WINDOW_SIZE - 1 - j)}"
                 for j in range(WINDOW_SIZE) for s in SENSOR_COLS]
    stat_cols = ([f"{s}_wmean"  for s in SENSOR_COLS] +
                 [f"{s}_wstd"   for s in SENSOR_COLS] +
                 [f"{s}_wtrend" for s in SENSOR_COLS])
    frame = pd.DataFrame(features, columns=raw_cols + stat_cols)

    prob = _score_from_model(fc_model, frame)
    return {
        "anomaly_probability": prob,
        "alarm": 1 if prob >= _ALARM_THRESHOLD else 0,
        "horizon_hours": horizon,
        "n_observations": len(recent_observations),
    }
