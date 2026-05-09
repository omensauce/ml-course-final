"""
Mock live sensor API for the industrial plant alarm system demo.
Generates realistic sensor readings from 9 plant instruments with
configurable anomaly scenarios so the auto-inference pipeline has
data to work with even without a live historian.

Run standalone:
    pip install fastapi uvicorn
    uvicorn mock_sensor_api:app --port 8002 --reload
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Mock Plant Sensor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── Sensor catalogue ──────────────────────────────────────────────────────────
SENSORS: dict[str, dict] = {
    "te301020":    {"base": 107.2, "noise": 0.30, "unit": "°C",   "label": "DEA Temperature D304"},
    "pdt31008":    {"base": 225.0, "noise": 4.00, "unit": "mbar", "label": "Pressure Diff D304"},
    "pdt31001":    {"base": 6.20,  "noise": 0.12, "unit": "mbar", "label": "Pressure Diff D301"},
    "pdt31007":    {"base": 53.10, "noise": 0.50, "unit": "mbar", "label": "Flow Pressure Archive"},
    "fq31050":     {"base": 83.50, "noise": 0.40, "unit": "m³/h", "label": "Steam Flow D304"},
    "lt301031":    {"base": 44.00, "noise": 2.00, "unit": "%",    "label": "Level D304"},
    "lic31012_pv": {"base": 79.80, "noise": 0.25, "unit": "%",    "label": "Level Ctrl D304 PV"},
    "lic31002_pv": {"base": 70.30, "noise": 0.25, "unit": "%",    "label": "Level Ctrl D301 PV"},
    "fic31011_pv": {"base": 413.5, "noise": 0.60, "unit": "m³/h", "label": "Reflux Flow PV"},
}

# ── Scenarios ─────────────────────────────────────────────────────────────────
#   Each modifier dict may contain:
#     drift_rate    – units/min added linearly over time, capped at drift_cap
#     drift_cap     – absolute maximum drift (positive = upward, negative = downward)
#     oscillate_amp – peak amplitude of sinusoidal oscillation
#     oscillate_period – period in seconds (default 40 s)
#     noise_mult    – multiplier on the baseline noise std
SCENARIOS: dict[str, dict] = {
    "normal": {
        "description": "All sensors within normal operating range",
        "color": "green",
        "modifiers": {},
    },
    "pressure_rise": {
        "description": "PDT31008 building — potential column flooding",
        "color": "amber",
        "modifiers": {
            "pdt31008": {"drift_rate": 6.0,  "drift_cap": 90.0,  "noise_mult": 2.5},
            "fq31050":  {"drift_rate": -0.5, "drift_cap": -5.0,  "noise_mult": 1.5},
        },
    },
    "level_swing": {
        "description": "LT301031 oscillating — reboiler instability",
        "color": "amber",
        "modifiers": {
            "lt301031":    {"oscillate_amp": 28.0, "oscillate_period": 30, "noise_mult": 3.0},
            "lic31012_pv": {"drift_rate": -1.0, "drift_cap": -8.0, "noise_mult": 1.5},
        },
    },
    "multi_alarm": {
        "description": "Multiple sensors critical — high alarm probability",
        "color": "red",
        "modifiers": {
            "pdt31008":    {"drift_rate": 10.0, "drift_cap": 130.0, "noise_mult": 3.0},
            "lt301031":    {"oscillate_amp": 35.0, "oscillate_period": 20, "noise_mult": 4.0},
            "lic31002_pv": {"drift_rate": 4.0,  "drift_cap": 20.0,  "noise_mult": 2.0},
            "te301020":    {"drift_rate": 0.8,  "drift_cap": 4.0,   "noise_mult": 1.5},
        },
    },
}

# ── Runtime state ─────────────────────────────────────────────────────────────
_state: dict = {"scenario": "normal", "scenario_start": time.time()}
_history: deque[dict] = deque(maxlen=600)  # ~10 min at 1 reading/s


# ── Reading generator ─────────────────────────────────────────────────────────
def _make_reading() -> dict:
    t   = time.time() - _state["scenario_start"]
    mods = SCENARIOS[_state["scenario"]]["modifiers"]
    out: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

    for key, cfg in SENSORS.items():
        noise    = random.gauss(0, cfg["noise"])
        mod      = mods.get(key, {})
        nm       = mod.get("noise_mult", 1.0)

        drift = 0.0
        if "drift_rate" in mod:
            # Linear drift that fully saturates at drift_cap after 60 s
            progress  = min(t / 60.0, 1.0)
            raw_drift = mod["drift_rate"] * progress
            cap       = mod["drift_cap"]
            drift     = max(raw_drift, cap) if cap < 0 else min(raw_drift, cap)

        oscillation = 0.0
        if "oscillate_amp" in mod:
            period      = mod.get("oscillate_period", 40)
            oscillation = mod["oscillate_amp"] * math.sin(2 * math.pi * t / period)

        out[key] = round(cfg["base"] + drift + oscillation + noise * nm, 3)

    return out


# Pre-populate 90 seconds of history so /sensors/history always has ≥12 entries
for _ in range(90):
    _history.append(_make_reading())


# ── Endpoints ─────────────────────────────────────────────────────────────────
class ScenarioRequest(BaseModel):
    name: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sensors/live")
def get_live():
    """Return a fresh sensor snapshot and append it to rolling history."""
    reading = _make_reading()
    _history.append(reading)
    sc = _state["scenario"]
    return {
        "reading":               reading,
        "scenario":              sc,
        "scenario_description":  SCENARIOS[sc]["description"],
        "scenario_color":        SCENARIOS[sc]["color"],
    }


@app.get("/sensors/history")
def get_history(n: int = 60):
    """Return the last n readings (default 60, max 600)."""
    n = min(n, 600)
    items = list(_history)[-n:]
    return {"readings": items, "count": len(items)}


@app.get("/scenarios")
def list_scenarios():
    return {
        "active": _state["scenario"],
        "scenarios": {
            name: {"description": cfg["description"], "color": cfg["color"]}
            for name, cfg in SCENARIOS.items()
        },
    }


@app.post("/scenarios/activate")
def activate_scenario(body: ScenarioRequest):
    if body.name not in SCENARIOS:
        raise HTTPException(404, f"Unknown scenario '{body.name}'. "
                            f"Valid: {list(SCENARIOS)}")
    _state["scenario"]       = body.name
    _state["scenario_start"] = time.time()
    return {"active": body.name, "description": SCENARIOS[body.name]["description"]}


@app.get("/sensors/meta")
def sensor_meta():
    """Return sensor labels and units for the UI."""
    return {k: {"label": v["label"], "unit": v["unit"]} for k, v in SENSORS.items()}
