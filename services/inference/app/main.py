from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

from app.model_loader import predict_risk, predict_forecast, load_named_model, WINDOW_SIZE

app = FastAPI(title="Plant Alarm Inference API", version="0.2.0")

# CORS is disabled by default — nginx routes /api/* from the same origin so no
# browser preflight ever reaches this service in production.  Set CORS_ORIGINS
# (comma-separated) only when accessing the API directly (e.g. dev without compose).
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# ── Prometheus metrics ────────────────────────────────────────────────────────
REQ_COUNT      = Counter("inference_requests_total", "Total inference requests")
HIGH_RISK_COUNT = Counter("inference_high_risk_total", "Predictions with high risk score")
PRED_LATENCY   = Histogram("inference_latency_seconds", "Inference latency")
LAST_RISK      = Gauge("inference_last_risk_score", "Last predicted risk score")
FORECAST_COUNT = Counter("forecast_requests_total", "Total forecast requests", ["horizon"])


# ── Request / response schemas ────────────────────────────────────────────────

class PredictRequest(BaseModel):
    features: Dict[str, float] = Field(default_factory=dict)


class RecommendRequest(BaseModel):
    failure_frequency_48: float = 0.0
    risk_score: float = 0.0


class ObservationRow(BaseModel):
    """One hourly sensor reading (keys = lowercase sensor names)."""
    te301020:    Optional[float] = 0.0
    pdt31008:    Optional[float] = 0.0
    pdt31001:    Optional[float] = 0.0
    pdt31007:    Optional[float] = 0.0
    fq31050:     Optional[float] = 0.0
    lt301031:    Optional[float] = 0.0
    lic31012_pv: Optional[float] = 0.0
    lic31002_pv: Optional[float] = 0.0
    fic31011_pv: Optional[float] = 0.0
    # Allow arbitrary extra sensor keys
    model_config = {"extra": "allow"}


class ForecastRequest(BaseModel):
    recent_observations: List[Dict[str, float]] = Field(
        ...,
        description=f"Ordered list of sensor readings (oldest first). "
                    f"Minimum {WINDOW_SIZE} entries required.",
        min_length=1,
    )
    horizon: int = Field(
        default=1,
        description="Hours ahead to forecast: 1, 3, or 6.",
        ge=1,
        le=6,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict")
def predict(payload: PredictRequest) -> dict:
    """Point-in-time anomaly risk score from a flat feature vector."""
    REQ_COUNT.inc()
    with PRED_LATENCY.time():
        result = predict_risk(payload.features)

    LAST_RISK.set(result["risk_score"])
    if result["risk_score"] >= 0.7:
        HIGH_RISK_COUNT.inc()

    return result


@app.post("/forecast")
def forecast(payload: ForecastRequest) -> dict:
    """
    Sliding-window early-warning forecast.
    Accepts the last N hours of sensor readings and returns anomaly
    probability at the requested horizon (1h / 3h / 6h ahead).
    """
    valid_horizons = {1, 3, 6}
    if payload.horizon not in valid_horizons:
        raise HTTPException(
            status_code=422,
            detail=f"horizon must be one of {sorted(valid_horizons)}, got {payload.horizon}",
        )

    FORECAST_COUNT.labels(horizon=str(payload.horizon)).inc()

    try:
        result = predict_forecast(
            recent_observations=payload.recent_observations,
            horizon=payload.horizon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return result


@app.post("/recommend")
def recommend(payload: RecommendRequest) -> dict[str, str]:
    """Rule-based maintenance recommendation."""
    ff   = payload.failure_frequency_48
    risk = payload.risk_score

    if ff >= 5 and risk >= 0.8:
        action = "High urgency: inspect and schedule replacement within 24h"
    elif ff >= 3 or risk >= 0.6:
        action = "Medium urgency: perform maintenance check in next shift"
    else:
        action = "Low urgency: continue monitoring and weekly inspection"

    return {"recommendation": action}


@app.get("/models")
def list_models() -> dict:
    """List available registered models that can be loaded."""
    model_names = [
        "plant_alarm_champion",
        "plant_alarm_isolation_forest",
        "plant_alarm_regime_classifier",
        "plant_alarm_deviation_predictor",
        "plant_alarm_forecaster_1h",
        "plant_alarm_forecaster_3h",
        "plant_alarm_forecaster_6h",
    ]
    status = {}
    for name in model_names:
        try:
            load_named_model(name)
            status[name] = "loaded"
        except Exception as exc:  # noqa: BLE001
            status[name] = f"unavailable: {exc}"
    return {"models": status}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
