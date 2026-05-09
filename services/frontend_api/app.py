"""
Frontend Gateway — JWT auth, per-user inference history, and live-sensor bridge.

Run:
    pip install -r requirements.txt
    uvicorn app:app --port 8001 --reload

Environment variables (all optional, defaults shown):
    JWT_SECRET          dev-secret-change-in-production
    INFERENCE_API_URL   http://localhost:8000
    SENSOR_API_URL      http://localhost:8002
    DB_PATH             frontend.db
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY    = os.getenv("JWT_SECRET",           "dev-secret-change-in-production")
ALGORITHM     = "HS256"
TOKEN_MINUTES = 60 * 24  # 24 hours

INFERENCE_API = os.getenv("INFERENCE_API_URL", "http://localhost:8000")
SENSOR_API    = os.getenv("SENSOR_API_URL",    "http://localhost:8002")
DB_PATH       = Path(os.getenv("DB_PATH",      "frontend.db"))

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Plant Alarm Frontend API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ── SQLite bootstrap ──────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


with _conn() as _bootstrap:
    _bootstrap.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            pw_hash  TEXT    NOT NULL,
            created  TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type    TEXT    NOT NULL,
            input   TEXT    NOT NULL,
            result  TEXT    NOT NULL,
            ts      TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

# ── Auth helpers ──────────────────────────────────────────────────────────────
def _hash(pw: str) -> str:
    return _pwd.hash(pw)


def _verify(pw: str, hashed: str) -> bool:
    return _pwd.verify(pw, hashed)


def _make_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def _current_user(token: str = Depends(_oauth)) -> dict:
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(401, "Invalid token")
    except JWTError:
        raise HTTPException(401, "Invalid token")
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        raise HTTPException(401, "User not found")
    return dict(row)


# ── History helper ────────────────────────────────────────────────────────────
def _store(user_id: int, kind: str, inp: dict, result: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO history (user_id, type, input, result, ts) VALUES (?,?,?,?,?)",
            (user_id, kind, json.dumps(inp), json.dumps(result),
             datetime.now(timezone.utc).isoformat()),
        )


# ── Auth endpoints ────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def register(body: RegisterIn):
    if len(body.username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (username, pw_hash, created) VALUES (?,?,?)",
                (body.username, _hash(body.password),
                 datetime.now(timezone.utc).isoformat()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already taken")
    return {"access_token": _make_token(body.username), "token_type": "bearer"}


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE username=?", (form.username,)
        ).fetchone()
    if not row or not _verify(form.password, row["pw_hash"]):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": _make_token(form.username), "token_type": "bearer"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/me")
def me(user: dict = Depends(_current_user)):
    return {"id": user["id"], "username": user["username"], "created": user["created"]}


# ── Inference proxy (stores every result in history) ─────────────────────────
FORECAST_KEYS = [
    "te301020", "pdt31008", "pdt31001", "pdt31007",
    "fq31050", "lt301031", "lic31012_pv", "lic31002_pv", "fic31011_pv",
]


class PredictIn(BaseModel):
    features: dict


class ForecastIn(BaseModel):
    recent_observations: list
    horizon: int = 1


@app.post("/infer/predict")
def infer_predict(body: PredictIn, user: dict = Depends(_current_user)):
    """Call inference /predict, fetch recommendation, store result, return to client."""
    try:
        pr = httpx.post(
            f"{INFERENCE_API}/predict",
            json={"features": body.features},
            timeout=10,
        )
        pr.raise_for_status()
        pred = pr.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text)
    except Exception as exc:
        raise HTTPException(502, f"Inference API unavailable: {exc}")

    try:
        rr = httpx.post(
            f"{INFERENCE_API}/recommend",
            json={
                "failure_frequency_48": float(body.features.get("failure_frequency_48", 0)),
                "risk_score": float(pred["risk_score"]),
            },
            timeout=5,
        )
        pred["recommendation"] = rr.json().get("recommendation", "")
    except Exception:
        pred["recommendation"] = ""

    _store(user["id"], "predict", body.features, pred)
    return pred


@app.post("/infer/forecast")
def infer_forecast(body: ForecastIn, user: dict = Depends(_current_user)):
    """Call inference /forecast, store result, return to client."""
    try:
        r = httpx.post(
            f"{INFERENCE_API}/forecast",
            json={"recent_observations": body.recent_observations, "horizon": body.horizon},
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text)
    except Exception as exc:
        raise HTTPException(502, f"Inference API unavailable: {exc}")

    _store(
        user["id"],
        f"forecast_{body.horizon}h",
        {"horizon": body.horizon, "n_obs": len(body.recent_observations)},
        result,
    )
    return result


@app.post("/infer/auto")
def auto_infer(user: dict = Depends(_current_user)):
    """
    Fetch live sensor history → run 1-hour forecast → store and return result.
    Requires mock_sensor_api and inference API to be running.
    """
    # 1. Pull the last 20 readings from the mock sensor API
    try:
        sr = httpx.get(f"{SENSOR_API}/sensors/history?n=20", timeout=5)
        sr.raise_for_status()
        readings = sr.json().get("readings", [])
    except Exception as exc:
        raise HTTPException(502, f"Sensor API unavailable: {exc}")

    if len(readings) < 12:
        raise HTTPException(
            422,
            f"Need ≥12 sensor readings, got {len(readings)}. "
            "Start mock_sensor_api.py and wait a moment.",
        )

    obs = [{k: float(r.get(k, 0.0)) for k in FORECAST_KEYS} for r in readings]

    # 2. Run the 1-hour forecast
    try:
        r = httpx.post(
            f"{INFERENCE_API}/forecast",
            json={"recent_observations": obs, "horizon": 1},
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, exc.response.text)
    except Exception as exc:
        raise HTTPException(502, f"Inference API unavailable: {exc}")

    # Attach latest sensor snapshot for the UI
    latest = readings[-1] if readings else {}
    result["sensor_snapshot"] = {k: latest.get(k) for k in FORECAST_KEYS}

    _store(user["id"], "auto_1h", {"source": "live_sensor", "n_obs": len(obs)}, result)
    return result


# ── History endpoints ─────────────────────────────────────────────────────────
@app.get("/history")
def get_history(limit: int = 200, user: dict = Depends(_current_user)):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user["id"], limit),
        ).fetchall()
    return [
        {
            "id":     r["id"],
            "type":   r["type"],
            "input":  json.loads(r["input"]),
            "result": json.loads(r["result"]),
            "ts":     r["ts"],
        }
        for r in rows
    ]


@app.delete("/history/{entry_id}")
def delete_entry(entry_id: int, user: dict = Depends(_current_user)):
    with _conn() as c:
        c.execute(
            "DELETE FROM history WHERE id=? AND user_id=?",
            (entry_id, user["id"]),
        )
    return {"deleted": entry_id}


@app.delete("/history")
def clear_history(user: dict = Depends(_current_user)):
    with _conn() as c:
        c.execute("DELETE FROM history WHERE user_id=?", (user["id"],))
    return {"cleared": True}
