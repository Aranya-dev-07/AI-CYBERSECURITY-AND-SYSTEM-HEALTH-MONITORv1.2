# Lavender Trinetra — API Reference

**Observe. Learn. Protect.**

---

## 1. API Overview

The Lavender Trinetra backend exposes a single REST API built with **FastAPI**, covering system status, live monitoring, AI-driven analysis, cybersecurity posture, and historical reports. All routes are defined in `backend/api/routes.py`, all request/response contracts are defined once as Pydantic models in `backend/api/schemas.py`, and dependency injection (such as database sessions) lives in `backend/api/dependencies.py`.

The API is:

- **Read-first** — the current implementation exposes primarily `GET` endpoints for status, metrics, and analysis retrieval.
- **Self-documenting** — FastAPI automatically generates an OpenAPI schema and interactive docs (`/docs`, `/redoc`) from the same Pydantic models documented here.
- **Explainability-oriented** — AI and cybersecurity endpoints return structured, human-readable explanations alongside numeric scores, not raw model output.

---

## 2. Base URL

All endpoints are mounted under a common router prefix:

```
/api
```

| Environment | Base URL |
|---|---|
| Local development (via Vite proxy) | `http://localhost:5173/api` → proxied to `http://localhost:8000/api` |
| Local development (direct) | `http://localhost:8000/api` |
| Production | `https://<your-deployed-host>/api` |

The frontend never hardcodes this URL — it is resolved centrally in `frontend/src/services/api.js` from the `VITE_BACKEND_URL` environment variable, falling back to a relative `/api` path so the Vite dev server proxy (`vite.config`) can forward requests during local development.

---

## 3. Authentication (Future-Ready)

The current API is unauthenticated — all endpoints are open. The following is reserved for a future release:

- **Scheme:** Bearer token (`Authorization: Bearer <token>`).
- **Frontend readiness:** `services/api.js`'s Axios request interceptor already checks for a stored token (`lt_auth_token`) and attaches it automatically when present, so no frontend changes will be required when auth ships.
- **Backend readiness:** `backend/api/dependencies.py` is the intended location for an auth dependency (e.g. `get_current_user`), to be added as a `Depends(...)` on protected routes without altering route signatures otherwise.
- **Planned flow:** token issuance via a future `/api/auth/login` endpoint, validated per-request via dependency injection, with 401 responses on missing/invalid/expired tokens.

Until implemented, do not rely on any endpoint being access-controlled.

---

## 4. Monitoring Endpoints

### `GET /api/monitoring/metrics`

Returns the latest live system metrics snapshot.

**Response** — `LiveMetricsResponse`

```json
{
  "metrics": {
    "timestamp": "2026-07-18T10:15:00Z",
    "cpu_usage_percent": 42.3,
    "memory_usage_percent": 61.8,
    "disk_usage_percent": 55.0,
    "network_sent_mb": 12.4,
    "network_received_mb": 34.9,
    "uptime_seconds": 305412.0
  },
  "status": "healthy"
}
```

| Field | Type | Notes |
|---|---|---|
| `metrics.cpu_usage_percent` | float (0–100) | |
| `metrics.memory_usage_percent` | float (0–100) | |
| `metrics.disk_usage_percent` | float (0–100) | |
| `metrics.network_sent_mb` / `network_received_mb` | float | Since last sampling interval |
| `metrics.uptime_seconds` | float, optional | |
| `status` | enum: `healthy` \| `warning` \| `critical` \| `unknown` | Derived from thresholds in `config.py` |

---

### `GET /api/monitoring/processes`

Returns the current top running processes.

**Query Parameters**

| Parameter | Type | Default | Constraints |
|---|---|---|---|
| `limit` | int | `50` | `1 ≤ limit ≤ 500` |

**Response** — `list[ProcessInfo]`

```json
[
  {
    "pid": 4821,
    "name": "python3",
    "cpu_percent": 12.5,
    "memory_percent": 3.8,
    "status": "running",
    "user": "lavender",
    "created_at": "2026-07-18T09:02:11Z"
  }
]
```

---

## 5. AI Endpoints

### `GET /api/ai/health-score`

Returns the current AI-computed system health score.

**Response** — `HealthScoreResponse`

```json
{
  "generated_at": "2026-07-18T10:15:00Z",
  "model_version": "1.0.0",
  "score": 87.5,
  "status": "healthy",
  "contributing_factors": [
    "CPU usage within normal range",
    "No active anomalies detected"
  ]
}
```

---

### `GET /api/ai/root-cause`

Returns the latest root cause analysis for any active issue.

**Response** — `RootCauseResponse`

```json
{
  "generated_at": "2026-07-18T10:15:00Z",
  "model_version": "1.0.0",
  "issue": "Elevated memory usage sustained over 15 minutes",
  "probable_causes": [
    {
      "factor": "Process 'node' memory growth",
      "confidence": 0.82,
      "explanation": "Memory usage for 'node' increased 34% over the analysis window."
    }
  ],
  "affected_components": ["memory", "process:node"]
}
```

---

### `GET /api/ai/recommendations`

Returns current AI-generated recommendations.

**Response** — `list[RecommendationItem]`

```json
[
  {
    "id": 12,
    "title": "Restart high-memory process",
    "description": "Process 'node' has grown steadily and may benefit from a restart.",
    "priority": "medium",
    "category": "performance",
    "created_at": "2026-07-18T10:15:00Z"
  }
]
```

---

### `GET /api/ai/trends`

Returns trend analysis across tracked metrics.

**Query Parameters**

| Parameter | Type | Default |
|---|---|---|
| `window` | string | `"24h"` |

**Response** — `TrendAnalysisResponse`

```json
{
  "generated_at": "2026-07-18T10:15:00Z",
  "model_version": "1.0.0",
  "window": "24h",
  "series": [
    {
      "metric_name": "cpu_usage",
      "points": [
        { "timestamp": "2026-07-18T09:00:00Z", "value": 38.2 },
        { "timestamp": "2026-07-18T10:00:00Z", "value": 42.3 }
      ],
      "direction": "increasing"
    }
  ],
  "summary": "CPU usage has trended upward over the last 24 hours."
}
```

---

### `GET /api/ai/predictive-alerts`

Returns current predictive alerts (forecasted future issues).

**Response** — `list[PredictiveAlert]`

```json
[
  {
    "id": 5,
    "metric": "disk_usage_percent",
    "predicted_issue": "Disk usage may exceed 90% within the next 2 hours.",
    "probability": 0.74,
    "eta_minutes": 118.0,
    "severity": "high",
    "generated_at": "2026-07-18T10:15:00Z"
  }
]
```

---

### `GET /api/ai/anomalies`

Returns currently detected anomalies.

**Response** — `list[AnomalyItem]`

```json
[
  {
    "id": 31,
    "metric": "network_sent_mb",
    "value": 340.2,
    "expected_range": "0–120 MB",
    "severity": "critical",
    "detected_at": "2026-07-18T10:14:00Z"
  }
]
```

---

## 6. Cybersecurity Endpoints

### `GET /api/cybersecurity/score`

Intended to return the overall security posture score.

**Response (as routed)** — `SecurityScoreResponse`

```json
{
  "score": 91.0,
  "status": "healthy",
  "open_threats": 0,
  "last_scan_at": "2026-07-18T09:45:00Z"
}
```

> **Implementation status:** this route is declared in `routes.py` and calls `backend.cybersecurity.security_score.compute_security_score()`, but the `backend/cybersecurity/` package does not yet exist in the repository. As currently checked in, this endpoint will fail at import/runtime rather than return the response above — it is documented here as the intended contract, not a verified working example.
>
> Detailed cybersecurity sub-domains (threat feed, firewall status, open ports, intrusion events, vulnerability scan results) are planned to be exposed as `GET /api/cybersecurity/threats`, `/firewall`, `/ports`, `/intrusion`, and `/vulnerabilities` respectively, backing the corresponding (not yet created) `backend/cybersecurity/` detector modules.

---

## 7. Reports Endpoints

### `GET /api/reports`

Returns all stored monitoring session reports.

**Response** — `list[ReportSummary]`

```json
[
  {
    "id": 7,
    "title": "Monitoring Session — 2026-07-18",
    "created_at": "2026-07-18T08:00:00Z",
    "report_type": "session_summary"
  }
]
```

### `GET /api/reports/{report_id}`

Returns full detail for a single report.

**Path Parameters**

| Parameter | Type | Required |
|---|---|---|
| `report_id` | int | Yes |

**Response** — `ReportDetail`

```json
{
  "id": 7,
  "title": "Monitoring Session — 2026-07-18",
  "created_at": "2026-07-18T08:00:00Z",
  "report_type": "session_summary",
  "content": {
    "duration_seconds": 3600,
    "avg_cpu": 41.2,
    "avg_ram": 58.9,
    "total_alerts": 3
  },
  "generated_by": "monitoring.reports"
}
```

**Errors:** `404 Not Found` if no report exists with the given `report_id`.

> `GET /api/dashboard/statistics` (aggregate PostgreSQL statistics: total runs, total metric/process samples, average/peak CPU & RAM, total alerts, latest run snapshot) and report export (`GET /api/reports/export?category=...&format=...`) are planned but not yet implemented.

---

## 8. Settings Endpoints

Not yet implemented in the current backend. The frontend's Settings workspace (`frontend/src/settings/`) is built against the following planned contract, mirroring `backend/config.py`'s existing threshold constants:

| Planned Endpoint | Method | Purpose |
|---|---|---|
| `/api/settings/alert-policy` | `GET` | Retrieve CPU/RAM/Disk/Network thresholds, severity levels, alert frequency, and enabled state |
| `/api/settings/alert-policy` | `PUT` | Persist alert policy changes |
| `/api/settings/preferences` | `GET` | Retrieve monitoring interval, auto-refresh, landing page, notification, and time-format preferences |
| `/api/settings/preferences` | `PUT` | Persist preference changes |
| `/api/settings/appearance` | `GET` | Retrieve theme mode, sidebar width, card density, animation toggle, font size, accent color |
| `/api/settings/appearance` | `PUT` | Persist appearance changes |

---

## 9. Dashboard Endpoints

| Planned Endpoint | Method | Purpose |
|---|---|---|
| `/api/dashboard/statistics` | `GET` | Aggregate statistics for the Dashboard and Reports → Database view (total test runs, total metrics/process samples stored, total AI reports, average/peak resource usage, latest run snapshot) |

The Dashboard's live status tiles (API/AI/monitoring/database health) are already served by the existing `GET /api/status` endpoint — see [System Status](#4-monitoring-endpoints).

---

## 10. WebSocket Overview

A real-time WebSocket channel is planned at:

```
ws://<host>/ws
```

The frontend's `services/websocket.js` already implements a full reconnecting WebSocket manager — auto-connect, exponential-backoff reconnection, graceful disconnect, heartbeat, and a channel-based pub/sub model — ready to receive live pushes the moment the backend implements this endpoint. No frontend changes will be required.

**Planned channels:**

| Channel | Purpose |
|---|---|
| `system.status` | Live push of `SystemStatusResponse` |
| `dashboard.live` | Live dashboard-wide updates |
| `monitoring.metrics` | Live push of `LiveMetricsResponse` (replacing polling) |
| `monitoring.processes` | Live push of `list[ProcessInfo]` |
| `ai.health_score` | Live push of `HealthScoreResponse` |
| `ai.anomalies` | Live push of newly detected `AnomalyItem`s |
| `ai.root_cause` | Live push of `RootCauseResponse` on new analysis |
| `ai.trends` | Live push of updated `TrendAnalysisResponse` |
| `ai.predictive_alerts` | Live push of new `PredictiveAlert`s |
| `cybersecurity.events` | Live push of security events/score changes |

**Planned message envelope:**

```json
{
  "channel": "monitoring.metrics",
  "type": "update",
  "payload": { "...": "matches the corresponding REST response schema" }
}
```

---

## 11. Request Format

- All request bodies (for future `POST`/`PUT` endpoints) must be `application/json`.
- Query parameters are validated by FastAPI/Pydantic per-route (see `Query(...)` constraints documented per endpoint above, e.g. `limit` on `/monitoring/processes`).
- Path parameters are strictly typed (e.g. `report_id: int`); non-matching types return `422 Unprocessable Entity` automatically.
- No request currently requires custom headers beyond the standard `Content-Type: application/json` and `Accept: application/json` sent by the frontend's Axios instance.

---

## 12. Response Format

- All responses are `application/json`, shaped by an explicit `response_model` Pydantic schema — every endpoint's response is validated against its documented schema before being sent, so the contracts above are guaranteed, not just conventions.
- List endpoints return a bare JSON array (e.g. `list[ProcessInfo]`), not a wrapped envelope.
- A generic `APIResponse` envelope (`{ success, message, data }`) is defined in `schemas.py` for future use in endpoints that need a uniform success/message wrapper (e.g. mutation endpoints), but is not yet used by any current `GET` endpoint.
- Timestamps are ISO 8601 (`datetime`), serialized in UTC.

---

## 13. Error Responses

All errors follow FastAPI's standard `HTTPException` shape:

```json
{
  "detail": "Human-readable error message"
}
```

| Scenario | Status | Example `detail` |
|---|---|---|
| Unhandled backend exception | `500` | The exception's string representation (all routes wrap their logic in `try/except` and re-raise as `HTTPException(status_code=500, ...)`, logging the full traceback server-side via `logger.exception(...)`) |
| Report not found | `404` | `"Report not found"` |
| Invalid query/path parameter | `422` | FastAPI's default Pydantic validation error detail |

The frontend's `services/api.js` normalizes all of the above (plus network errors and timeouts) into a single `Error` object with a readable `.message`, so components never need to branch on response shape to display an error.

---

## 14. Status Codes

| Code | Meaning | Used for |
|---|---|---|
| `200 OK` | Success | All successful `GET` responses |
| `404 Not Found` | Resource does not exist | `GET /api/reports/{report_id}` with an unknown ID |
| `422 Unprocessable Entity` | Request validation failed | Invalid query/path parameter types or out-of-range values (e.g. `limit` outside `1–500`) |
| `500 Internal Server Error` | Unhandled exception in a route handler | Any route — caught centrally and logged via `logger.exception(...)` |
| `501 Not Implemented` *(reserved)* | Planned endpoint not yet built | Not currently returned; endpoints documented as "planned" in this document simply do not exist yet (404 at the routing level) |

---

## 15. API Best Practices

**For backend contributors:**

- Add new endpoints to `backend/api/routes.py` only; define their request/response contracts once in `backend/api/schemas.py` and reference via `response_model` so FastAPI validates and documents them automatically.
- Keep route handlers thin — delegate to the appropriate domain module (`monitoring/`, `ai/`, `cybersecurity/`, `database/crud.py`) rather than embedding logic in the route function.
- Wrap route logic in `try/except`, log with `logger.exception(...)`, and re-raise as `HTTPException` — follow the existing pattern in every current route.
- Prefer query parameters with explicit `Query(default=..., ge=..., le=...)` constraints over unvalidated raw parameters.

**For frontend contributors:**

- Never call `fetch`/`axios` directly from a component — always add a named function to `frontend/src/services/api.js` and import that.
- Treat endpoints marked "planned" in this document as returning errors until implemented; components consuming them should already handle loading/error states gracefully (per the existing component patterns).
- When the WebSocket channel above ships, prefer subscribing via `useWebSocketChannel` over polling for any data available on a live channel.

**For API consumers generally:**

- Always check the `/docs` (Swagger UI) or `/redoc` endpoint on a running instance for the authoritative, always-current schema — this document describes intent and structure, but the live OpenAPI schema is generated directly from the code.
- Treat all endpoints as unauthenticated for now; do not expose a Lavender Trinetra backend instance to an untrusted network until authentication ships.