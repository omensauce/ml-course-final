// API client — all calls go through two services:
//   FRONTEND_API  (auth, history, inference proxy)  default: localhost:8001
//   SENSOR_API    (mock live sensor data)            default: localhost:8002

const FRONTEND = import.meta.env.VITE_FRONTEND_API_URL || 'http://localhost:8001';
const SENSOR   = import.meta.env.VITE_SENSOR_API_URL   || 'http://localhost:8002';

function token() {
  return localStorage.getItem('pa_token');
}

function authHdr() {
  const t = token();
  return t
    ? { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' };
}

async function _json(res) {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function apiRegister(username, password) {
  return _json(await fetch(`${FRONTEND}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  }));
}

export async function apiLogin(username, password) {
  return _json(await fetch(`${FRONTEND}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  }));
}

export async function apiMe() {
  return _json(await fetch(`${FRONTEND}/auth/me`, { headers: authHdr() }));
}

// ── Sensor (no auth required) ─────────────────────────────────────────────────
export async function apiLiveSensor() {
  return _json(await fetch(`${SENSOR}/sensors/live`));
}

export async function apiSensorHistory(n = 60) {
  return _json(await fetch(`${SENSOR}/sensors/history?n=${n}`));
}

export async function apiScenarios() {
  return _json(await fetch(`${SENSOR}/scenarios`));
}

export async function apiActivateScenario(name) {
  return _json(await fetch(`${SENSOR}/scenarios/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }));
}

// ── Inference (auth required, results persisted to history) ───────────────────
export async function apiPredict(features) {
  return _json(await fetch(`${FRONTEND}/infer/predict`, {
    method: 'POST',
    headers: authHdr(),
    body: JSON.stringify({ features }),
  }));
}

export async function apiForecast(recentObservations, horizon) {
  return _json(await fetch(`${FRONTEND}/infer/forecast`, {
    method: 'POST',
    headers: authHdr(),
    body: JSON.stringify({ recent_observations: recentObservations, horizon }),
  }));
}

export async function apiAutoInfer() {
  return _json(await fetch(`${FRONTEND}/infer/auto`, {
    method: 'POST',
    headers: authHdr(),
  }));
}

// ── History ───────────────────────────────────────────────────────────────────
export async function apiGetHistory(limit = 200) {
  return _json(await fetch(`${FRONTEND}/history?limit=${limit}`, { headers: authHdr() }));
}

export async function apiDeleteEntry(id) {
  return _json(await fetch(`${FRONTEND}/history/${id}`, {
    method: 'DELETE',
    headers: authHdr(),
  }));
}

export async function apiClearHistory() {
  return _json(await fetch(`${FRONTEND}/history`, {
    method: 'DELETE',
    headers: authHdr(),
  }));
}
