# Lavender Trinetra — Software Architecture

**Observe. Learn. Protect.**

---

## 1. Project Overview

Lavender Trinetra is an AI-driven system health and cybersecurity monitoring platform. It continuously observes host system resources and processes, applies machine learning to detect anomalies, analyze trends, forecast issues, and surface root causes, and pairs that with cybersecurity monitoring (threat detection, firewall status, port scanning, intrusion detection, vulnerability scanning) — all surfaced through a unified, explainable dashboard.

The system is composed of three cooperating layers:

1. A **Python/FastAPI backend** that collects system telemetry, runs AI analysis, evaluates security posture, and persists results.
2. A **PostgreSQL database** that stores historical metrics, process samples, AI results, and generated reports.
3. A **React/Vite frontend** that visualizes live and historical data, hosts the AI workspace, cybersecurity workspace, reports, and settings.

The guiding principle across all three layers is **explainability**: every AI-derived output (health score, anomaly, trend, prediction, recommendation, root cause) is expected to carry a human-readable explanation alongside its numeric result, rather than being a black-box score.

---

## 2. System Architecture

```
                        ┌───────────────────────────┐
                        │        Frontend           │
                        │   React + Vite (SPA)      │
                        │  Dashboard · Monitoring    │
                        │  AI Workspace · Cyber      │
                        │  Reports · Settings        │
                        └─────────────┬─────────────┘
                                      │ HTTPS (REST, Axios)
                                      │ WebSocket (planned, real-time push)
                                      ▼
                        ┌───────────────────────────┐
                        │        Backend            │
                        │   FastAPI Application      │
                        │  ┌───────────────────────┐ │
                        │  │  API Layer (routes)   │ │
                        │  └──────────┬────────────┘ │
                        │             │               │
                        │  ┌──────────▼───────────┐  │
                        │  │  Monitoring Engine    │  │
                        │  │  AI Engine            │  │
                        │  │  Cybersecurity Engine  │  │
                        │  └──────────┬────────────┘  │
                        └─────────────┼───────────────┘
                                      │ SQLAlchemy ORM
                                      ▼
                        ┌───────────────────────────┐
                        │       PostgreSQL           │
                        │  Metrics · Processes ·     │
                        │  AI Results · Reports       │
                        └───────────────────────────┘

               (Supplementary CSV export: system_metrics.csv,
                system_processes.csv, system_report.csv)
```

The frontend never talks to PostgreSQL or the collection engines directly — every interaction is mediated by the FastAPI REST API, itself accessed exclusively through the frontend's centralized API layer (`services/api.js`).

---

## 3. Backend Architecture

The backend is organized as a modular FastAPI application under `backend/`, split into clearly bounded subsystems:

| Module | Responsibility |
|---|---|
| `main.py` | Application entry point; boots the FastAPI app and the monitoring loop. |
| `config.py` | Central configuration: alert thresholds (CPU/RAM/Disk/Network), monitoring interval, shared in-memory state (`alert_count`, etc.), and `generate_alert()`. |
| `core.py` | Shared utilities used across backend modules. |
| `monitoring/` | Metrics/process collection, alert generation, and report/session summarization. |
| `ai/` | Machine-learning driven analysis: anomaly detection, health scoring, root cause analysis, recommendations, trend analysis, predictive alerts, and the orchestrating `ai_engine.py`. |
| `cybersecurity/` | Threat detection, firewall monitoring, port scanning, intrusion detection, malware detection, vulnerability scanning, and an aggregate security score. **Implementation status:** `routes.py` imports and calls `backend.cybersecurity.security_score.compute_security_score()` for `GET /api/cybersecurity/score`, but the `backend/cybersecurity/` package does not yet exist in the repository — this module is designed but not yet implemented. |
| `api/` | FastAPI routers (`routes.py`), Pydantic request/response schemas (`schemas.py`), dependency injection (`dependencies.py`), and app wiring (`api.py`). |
| `database/` | SQLAlchemy models, CRUD operations, session/engine setup, and Alembic migrations. |
| `data/` | CSV mirrors of collected metrics/process/report data for lightweight export and offline inspection. |

### Design pattern

The backend follows a **layered service architecture**:

```
routes.py (API layer)
    → monitoring / ai / cybersecurity (domain/service layer)
        → database/crud.py (persistence layer)
            → database/models.py (ORM layer) → PostgreSQL
```

Each domain layer (`monitoring`, `ai`, `cybersecurity`) is independent and unaware of the API layer — routers call into domain modules and shape their output into `api/schemas.py` response models, keeping FastAPI concerns (serialization, HTTP status codes) out of the domain logic.

---

## 4. Frontend Architecture

The frontend is a React single-page application built with Vite, organized by **feature domain** rather than by component type:

| Directory | Responsibility |
|---|---|
| `layout/` | Application shell: `AppShell.jsx`, `Sidebar.jsx`, `Topbar.jsx`. |
| `pages/` | Top-level routed views: Dashboard, Monitoring, AI Workspace, Cybersecurity, Reports, Settings. |
| `monitoring/` | Live metrics, process monitoring, graphs/charts, and session controls. |
| `ai/` | AI Engine overview, Health Score, Root Cause, Recommendations, Anomalies, Trends, Predictive Alerts, AI Reports. |
| `cybersecurity/` | Threat overview, firewall, ports, intrusion, vulnerabilities, security score. **Implementation status:** all six component files currently exist as empty stubs pending implementation. |
| `reports/` | Test run history, database statistics, export workspace, report history. |
| `settings/` | Alert policy, preferences, appearance, about. |
| `context/` | `SystemStatusContext.jsx` — the single global state provider. |
| `services/` | `api.js` (REST) and `websocket.js` (real-time channel manager). |
| `components/` | Shared design-system primitives: `Card`, `StatusBadge`, `ProgressRing`, `Loader`, `Toast`, `Modal`. **Implementation status:** all six files currently exist as empty stubs; every other feature component (`ai/`, `monitoring/`, `reports/`, `settings/`) is written to import from these primitives, so implementing them is a prerequisite for the application to render. |
| `utils/` | Shared frontend utilities. |

### Design pattern

Every feature page follows the same **container → presentational** split:

- A `pages/*.jsx` file fetches its domain's data (directly or via `SystemStatusContext`) and composes the relevant feature components.
- Feature components under `ai/`, `monitoring/`, `cybersecurity/`, `reports/`, and `settings/` are largely self-contained: they accept props for initial data, independently poll `services/api.js` for refreshes, and render using shared `components/` primitives — but perform no scoring, detection, or aggregation logic themselves.
- Global, cross-cutting state (service status, active alert count, AI health score, current workspace) lives in `SystemStatusContext`, avoiding prop-drilling between `AppShell`, `Sidebar`, `Topbar`, and page-level components.

---

## 5. Directory Structure

```
Lavender-Trinetra/
│
├── README.md
├── LICENSE
├── requirements.txt
├── .env
├── .gitignore
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── core.py
│   │
│   ├── monitoring/
│   │   ├── collector.py
│   │   ├── processes.py
│   │   ├── alerts.py
│   │   ├── reports.py
│   │   └── metrics.py
│   │
│   ├── ai/
│   │   ├── ai_engine.py
│   │   ├── anomaly_detection.py
│   │   ├── health_score.py
│   │   ├── root_cause.py
│   │   ├── recommendations.py
│   │   ├── trend_analysis.py
│   │   ├── predictive_alerts.py
│   │   └── models/
│   │
│   ├── cybersecurity/
│   │   ├── threat_detector.py
│   │   ├── firewall_monitor.py
│   │   ├── port_scanner.py
│   │   ├── intrusion_detector.py
│   │   ├── malware_detector.py
│   │   ├── vulnerability_scan.py
│   │   └── security_score.py
│   │
│   ├── api/
│   │   ├── api.py
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── dependencies.py
│   │
│   ├── database/
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── crud.py
│   │   └── migrations/
│   │
│   └── data/
│       ├── system_metrics.csv
│       ├── system_processes.csv
│       ├── system_report.csv
│       └── models/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── public/
│   │
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── assets/
│       │
│       ├── layout/
│       │   ├── AppShell.jsx
│       │   ├── Sidebar.jsx
│       │   └── Topbar.jsx
│       │
│       ├── pages/
│       │   ├── Dashboard.jsx
│       │   ├── Monitoring.jsx
│       │   ├── AIWorkspace.jsx
│       │   ├── Cybersecurity.jsx
│       │   ├── Reports.jsx
│       │   └── Settings.jsx
│       │
│       ├── monitoring/
│       │   ├── LiveMetrics.jsx
│       │   ├── ProcessMonitoring.jsx
│       │   ├── Graphs.jsx
│       │   ├── Charts.jsx
│       │   └── Controls.jsx
│       │
│       ├── ai/
│       │   ├── AIEngine.jsx
│       │   ├── HealthScore.jsx
│       │   ├── RootCause.jsx
│       │   ├── Recommendations.jsx
│       │   ├── Anomalies.jsx
│       │   ├── Trends.jsx
│       │   ├── Predictive.jsx
│       │   └── AIReports.jsx
│       │
│       ├── cybersecurity/
│       │   ├── ThreatOverview.jsx
│       │   ├── Firewall.jsx
│       │   ├── Ports.jsx
│       │   ├── Intrusion.jsx
│       │   ├── Vulnerabilities.jsx
│       │   └── SecurityScore.jsx
│       │
│       ├── reports/
│       │   ├── TestRuns.jsx
│       │   ├── Database.jsx
│       │   ├── Export.jsx
│       │   └── ReportHistory.jsx
│       │
│       ├── settings/
│       │   ├── AlertPolicy.jsx
│       │   ├── Preferences.jsx
│       │   ├── Appearance.jsx
│       │   └── About.jsx
│       │
│       ├── context/
│       │   └── SystemStatusContext.jsx
│       │
│       ├── services/
│       │   ├── api.js
│       │   └── websocket.js
│       │
│       ├── utils/
│       │
│       └── components/
│           ├── Card.jsx
│           ├── StatusBadge.jsx
│           ├── ProgressRing.jsx
│           ├── Loader.jsx
│           ├── Toast.jsx
│           └── Modal.jsx
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── dashboard.md
│   └── screenshots/        # UI screenshots referenced from docs/*.md via
│                            # relative paths, e.g. ![Dashboard](screenshots/dashboard.png)
│
└── tests/
    ├── backend/
    └── frontend/
```

---

## 6. Data Flow

End-to-end flow of a single piece of telemetry, from collection to screen:

1. **Collection** — `monitoring/collector.py` samples CPU, RAM, disk, and network usage on a fixed interval (`MONITOR_INTERVAL`, default 5s), and `monitoring/processes.py` samples the running process table.
2. **Threshold evaluation** — `config.py::generate_alert()` compares each sample against configured thresholds (CPU/RAM/Disk/Network) and increments `alert_count` when exceeded.
3. **Persistence** — Samples are written to PostgreSQL via `database/crud.py` (and mirrored to CSV under `backend/data/` for lightweight export).
4. **AI analysis** — `ai/ai_engine.py` orchestrates the AI subsystems (anomaly detection, health scoring, root cause, trend analysis, predictive alerts, recommendations) against recent samples, producing an explainable result set.
5. **Cybersecurity analysis** — The `cybersecurity/` module independently evaluates firewall status, open ports, intrusion signals, and known vulnerabilities, rolling up into a security score.
6. **API exposure** — `api/routes.py` exposes all of the above as versioned REST endpoints, shaped by `api/schemas.py` Pydantic models.
7. **Frontend retrieval** — `services/api.js` polls (and, in the future, receives push updates via `services/websocket.js`) the relevant endpoints.
8. **Global state distribution** — `SystemStatusContext.jsx` holds cross-cutting status (API/AI/DB/monitoring/security health, active alert count, AI health score, current workspace) and distributes it to `Sidebar`, `Topbar`, and page-level components.
9. **Rendering** — Feature components (`monitoring/`, `ai/`, `cybersecurity/`, `reports/`) render the data using shared `components/` primitives, with no computation happening client-side.

---

## 7. Monitoring Pipeline

```
psutil sampling (collector.py, processes.py)
        │
        ▼
Threshold evaluation (config.py::generate_alert)
        │
        ▼
In-memory state update (metrics_data, process_data, alert_count)
        │
        ├──────────────► CSV mirror (backend/data/*.csv)
        │
        ▼
PostgreSQL persistence (database/crud.py)
        │
        ▼
Session summarization (monitoring/reports.py → RunSummary)
        │
        ▼
Exposed via /api/monitoring/* and /api/reports
```

The monitoring pipeline is intentionally the most foundational layer — both the AI pipeline and the reporting pipeline consume its output rather than sampling the system independently.

---

## 8. AI Pipeline

```
Recent metrics/process samples (from Monitoring Pipeline)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                     ai_engine.py                          │
│                 (orchestration layer)                     │
├─────────────────┬─────────────────┬───────────────────────┤
│ anomaly_detection│  health_score    │   root_cause          │
│      .py         │      .py         │      .py              │
├─────────────────┼─────────────────┼───────────────────────┤
│ trend_analysis   │ predictive_alerts│  recommendations      │
│      .py         │      .py         │      .py              │
└─────────────────┴─────────────────┴───────────────────────┘
        │
        ▼
Explainable result objects (AnomalyResult, TrendResult,
Prediction, Recommendation, RootCauseResult, HealthScore)
        │
        ▼
Persisted + exposed via /api/ai/* endpoints
        │
        ▼
Rendered by frontend/src/ai/* components (Anomalies, Trends,
Predictive, HealthScore, RootCause, Recommendations, AIReports)
```

Each AI subsystem is independently callable and independently testable — `ai_engine.py` composes their outputs into a single analysis cycle rather than embedding their logic itself.

---

## 9. Cybersecurity Pipeline

> **Implementation status:** the diagram below reflects the designed pipeline per the project's intended structure. In the current repository, `backend/cybersecurity/` has not yet been created — only the aggregate `GET /api/cybersecurity/score` route exists in `routes.py`, and it references a `security_score.py` module that is not yet present. The six detector modules and all six corresponding frontend components (`frontend/src/cybersecurity/*`) are pending implementation.

```
┌────────────────────────────────────────────────────────────┐
│                    cybersecurity/                            │
├───────────────┬────────────────┬────────────────────────────┤
│ threat_detector│ firewall_monitor│  port_scanner               │
│     .py        │      .py        │      .py                    │
├───────────────┼────────────────┼────────────────────────────┤
│intrusion_detector│malware_detector│ vulnerability_scan          │
│     .py          │      .py       │      .py                   │
└───────────────┴────────────────┴────────────────────────────┘
        │
        ▼
security_score.py (aggregate rollup)
        │
        ▼
Exposed via /api/cybersecurity/* endpoints
        │
        ▼
Rendered by frontend/src/cybersecurity/* components
(ThreatOverview, Firewall, Ports, Intrusion, Vulnerabilities,
SecurityScore)
```

The cybersecurity pipeline runs independently of the AI pipeline — the two are correlated only at the presentation layer (e.g. a security event may be cross-referenced against a system anomaly on the Dashboard), not through shared backend state.

---

## 10. Database Architecture

PostgreSQL is the system of record for all historical data:

| Concern | Owning module |
|---|---|
| Connection/session/engine setup | `database/database.py` |
| ORM models (metrics, processes, AI results, reports) | `database/models.py` |
| Read/write operations, aggregate statistics | `database/crud.py` |
| Schema evolution | `database/migrations/` (Alembic) |

`database/crud.py` is the single point of contact for all persistence — no other backend module issues SQL directly. Aggregate reporting (e.g. dashboard statistics: total runs, total metric/process samples, average/peak CPU & RAM, total alerts, latest run snapshot) is computed at the CRUD layer, not duplicated in the API or frontend.

CSV files under `backend/data/` act as a lightweight, human-readable mirror of recent metrics/process/report data — useful for quick inspection or export — but PostgreSQL remains the authoritative store.

---

## 11. API Architecture

The API layer is a versioned FastAPI router (`api/routes.py`) mounted under a common prefix, structured by domain:

| Domain | Example endpoints |
|---|---|
| System Status | `GET /status` |
| Monitoring | `GET /monitoring/metrics`, `GET /monitoring/processes` |
| AI Workspace | `GET /ai/health-score`, `GET /ai/root-cause`, `GET /ai/recommendations`, `GET /ai/trends`, `GET /ai/predictive-alerts`, `GET /ai/anomalies` |
| Cybersecurity | `GET /cybersecurity/score` |
| Reports | `GET /reports`, `GET /reports/{id}` |

Request/response contracts are defined once in `api/schemas.py` as Pydantic models and reused by both the route handlers and (conceptually) the frontend's expected payload shapes — keeping the API self-documenting via FastAPI's generated OpenAPI schema. Cross-cutting concerns (dependency injection, e.g. database sessions) live in `api/dependencies.py`, and application/router wiring lives in `api/api.py`.

The frontend never calls these endpoints directly — every call is routed through `frontend/src/services/api.js`, which owns the Axios instance, base URL resolution, timeout, and centralized error normalization.

---

## 12. Frontend Architecture (State & Communication)

- **Global state** — `SystemStatusContext.jsx` is the single source of truth for cross-cutting status, wrapping the application via `App.jsx`. It exposes `status`, `isLoading`, `error`, and reusable functions: `refreshStatus`, `updateStatus`, `resetStatus`, `updateWorkspace`.
- **REST communication** — `services/api.js` centralizes all HTTP communication: a single Axios instance, request/response interceptors, timeout handling, and one exported function per backend capability (dashboard, monitoring, AI workspace, cybersecurity, reports, settings, system status, test runs).
- **Real-time communication (future-ready)** — `services/websocket.js` defines a reconnecting WebSocket manager with named channels (live metrics, process monitoring, AI health score, anomalies, root cause, trends, predictive alerts, cybersecurity events, system status, dashboard updates) so components can subscribe today and receive live pushes the moment the backend implements the corresponding channel — with no frontend changes required.
- **Design system** — `components/` holds the shared Lavender Trinetra primitives (`Card`, `StatusBadge`, `ProgressRing`, `Loader`, `Toast`, `Modal`) that every feature component composes from, keeping visual language consistent across Dashboard, Monitoring, AI Workspace, Cybersecurity, Reports, and Settings.

---

## 13. Explainable AI Workflow

Lavender Trinetra treats explainability as a first-class output, not an afterthought. Every AI result type is designed to answer three questions simultaneously:

1. **What happened?** — the raw signal (a score, a detected anomaly, a forecast).
2. **How confident is the system?** — a confidence/probability value accompanies anomalies and predictions.
3. **Why did it happen, and what should be done?** — a natural-language explanation and, where applicable, a recommended action.

```
Raw metrics/process samples
        │
        ▼
Anomaly Detection ──► AnomalyResult { severity, confidence,
                       affected_metrics, top_process, evidence }
        │
        ▼
Root Cause Analysis ──► RootCauseResult { affected_metric,
                         responsible_process, explanation,
                         recommended_action }
        │
        ▼
Trend Analysis ──► TrendResult { direction, severity,
                    explanation, current vs. window-start value }
        │
        ▼
Predictive Alerts ──► Prediction { predicted_event, risk_level,
                       confidence_score, eta_minutes,
                       explanation, recommended_action }
        │
        ▼
Recommendations ──► Recommendation { title, category,
                     priority_score, reasoning,
                     recommended_action }
        │
        ▼
Health Score ──► { score, status, contributing_factors,
                    explanation }
```

Every one of these result objects is rendered as-is by the frontend (`ai/Anomalies.jsx`, `ai/Trends.jsx`, `ai/Predictive.jsx`, `ai/RootCause.jsx`, `ai/Recommendations.jsx`, `ai/HealthScore.jsx`) — the frontend never re-derives or re-scores anything; it only displays the backend's explanation.

---

## 14. Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | Python, FastAPI |
| System telemetry | psutil |
| Backend validation/serialization | Pydantic |
| Database | PostgreSQL, SQLAlchemy, Alembic (migrations) |
| AI / ML | Anomaly detection, trend analysis, predictive alerting (backend/ai/) |
| Frontend framework | React, Vite |
| Frontend styling | Tailwind CSS (Lavender Trinetra Design System) |
| Frontend data viz | Recharts |
| Frontend HTTP | Axios (`services/api.js`) |
| Frontend real-time (future) | Native WebSocket (`services/websocket.js`) |
| Frontend icons | Phosphor Icons (`react-icons/pi`) |
| Frontend notifications | react-hot-toast |
| Frontend animation | Framer Motion |
| Frontend state (local) | Zustand (where applicable), React Context (global) |

---

## 15. Future Scalability

The architecture is deliberately modular to support the following without structural rewrites:

- **Real-time push** — `services/websocket.js` is already channel-based and ready to receive live pushes for metrics, processes, AI results, and cybersecurity events the moment the backend exposes a `/ws` endpoint; consuming components subscribe via `useWebSocketChannel` with no future refactor needed.
- **Horizontal scaling of the AI engine** — because each `ai/` submodule is independently callable, individual analyses (e.g. anomaly detection) could be moved to a background worker or separate service without changing `api/routes.py`'s contract.
- **Pluggable cybersecurity detectors** — new detectors can be added under `cybersecurity/` and rolled into `security_score.py` without touching existing detectors.
- **Multi-tenant / multi-host monitoring** — the current single-host model can be extended by parameterizing `monitoring/collector.py` and the database schema with a host identifier, without changing the frontend's data-fetching contracts.
- **Authentication** — `services/api.js`'s request interceptor already reserves a bearer-token attachment point, and `api/dependencies.py` is the natural place to add auth dependencies backend-side.
- **Alternative frontends** — because all backend capabilities are exposed as a documented REST API (and soon WebSocket channels), additional clients (mobile, CLI, third-party integrations) can be built against the same backend without modification.

---

## 16. Design Principles

- **Separation of concerns** — collection, analysis, persistence, and presentation are distinct layers that communicate through well-defined contracts (Pydantic schemas, REST endpoints, prop interfaces).
- **Explainability over opacity** — every AI and security result carries a human-readable explanation alongside its numeric output.
- **Single source of truth** — `SystemStatusContext.jsx` on the frontend and `database/crud.py` on the backend are the only places cross-cutting state is computed or aggregated.
- **No duplicated business logic** — frontend components render backend-computed results; they do not re-implement scoring, detection, or threshold evaluation.
- **Centralized communication** — all HTTP traffic flows through `services/api.js`; all (future) real-time traffic flows through `services/websocket.js`. No component talks to the network directly.
- **Consistent design language** — all UI surfaces are built from the same `components/` primitives, maintaining the Lavender Trinetra Design System across every workspace.
- **Fail gracefully** — network and backend failures are normalized into readable error messages (`api.js`'s interceptors) and surfaced via non-blocking UI (toasts, inline error text) rather than crashing the interface.
- **Modularity for scale** — each domain (monitoring, AI, cybersecurity, reports, settings) is independently extensible without cross-module coupling.