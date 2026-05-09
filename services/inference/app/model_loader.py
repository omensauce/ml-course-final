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


def predict_risk(features: dict[str, float]) -> dict[str, float]:
    """Point-in-time risk prediction from a flat feature dict.

    Missing features are filled with 0 so partial payloads don't crash;
    extra keys are silently ignored.
    """
    model = load_champion_model()
    expected = _expected_feature_names(model)
    if expected is not None:
        row = {col: float(features.get(col, 0.0)) for col in expected}
        frame = pd.DataFrame([row], columns=expected)
    else:
        frame = pd.DataFrame([features])
    pred = model.predict(frame)

    if hasattr(pred, "tolist"):
        pred_val = float(pred.tolist()[0])
    else:
        pred_val = float(pred[0])

    risk_score = max(0.0, min(1.0, pred_val))
    return {"risk_score": risk_score, "alarm": 1 if risk_score >= 0.5 else 0}


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

    prob_raw = fc_model.predict(frame)
    if hasattr(prob_raw, "tolist"):
        prob = float(prob_raw.tolist()[0])
    else:
        prob = float(prob_raw[0])

    prob = max(0.0, min(1.0, prob))
    return {
        "anomaly_probability": prob,
        "alarm": 1 if prob >= 0.5 else 0,
        "horizon_hours": horizon,
        "n_observations": len(recent_observations),
    }
