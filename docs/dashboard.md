# Lavender Trinetra — Dashboard & UI Architecture

**Observe. Learn. Protect.**

---

## 1. Dashboard Overview

The Lavender Trinetra frontend is a single-page React application organized around one persistent application shell (`AppShell.jsx`) hosting six routed workspaces: **Dashboard**, **Monitoring**, **Trinetra AI**, **Cybersecurity**, **Reports**, and **Settings**. Every workspace shares the same shell, the same global status context, the same design-system primitives, and the same visual language — so the experience of monitoring system health, reviewing AI analysis, and investigating security posture feels like one coherent product rather than six separate tools.

The interface follows a **dark, focused, data-dense aesthetic**: a fixed sidebar for navigation and live service status, a contextual topbar for page identity and quick actions, and a scrollable content area built from a small set of reusable `Card`-based primitives.

---

## 2. Navigation Structure

Routing is handled by `react-router-dom`, with route metadata centralized in `layout/topbar.jsx` (`ROUTE_META`) and navigation entries centralized in `layout/sidebar.jsx` (`NAV_ITEMS`):

| Route | Workspace | Page Component |
|---|---|---|
| `/dashboard` | Dashboard | `pages/Dashboard.jsx` |
| `/monitoring` | Monitoring | `pages/Monitoring.jsx` |
| `/ai-workspace` | Trinetra AI | `pages/AIWorkspace.jsx` |
| `/cybersecurity` | Cybersecurity | `pages/Cybersecurity.jsx` |
| `/reports` | Reports | `pages/Reports.jsx` |
| `/settings` | Settings | `pages/Settings.jsx` |

Navigation state (which workspace is active) is reflected in both the Sidebar's highlighted nav item and the Topbar's page title/description, and is additionally tracked in `SystemStatusContext` via `updateWorkspace()` so any component can be workspace-aware without prop-drilling.

---

## 3. Sidebar

**Component:** `layout/Sidebar.jsx`

The Sidebar is the primary navigation surface, rendered full-height on the left edge of the shell. It contains:

- **Brand mark** — the Lavender Trinetra icon mark plus wordmark and version, hidden to just the icon when collapsed.
- **Primary navigation** — six items (Dashboard, Monitoring, Trinetra AI, Cybersecurity, Reports, Settings), each with a Phosphor icon and label, using `NavLink` active-state styling.
- **Live service status rows** — compact indicators for AI Engine, Database, and API status, sourced live from `useSystemStatus()`. Each row shows a colored, glowing status dot (online / starting / offline) plus a label, collapsing to dot-only when the sidebar is collapsed.
- **Collapse toggle** — lets the user shrink the sidebar to an icon-only rail, with state owned by `AppShell.jsx` and animated via Framer Motion.

The Sidebar contains no data-fetching or business logic of its own — it is a pure consumer of `SystemStatusContext` and `react-router-dom`.

![Sidebar](screenshots/sidebar.png)

---

## 4. Topbar

**Component:** `layout/Topbar.jsx`

The Topbar sits above the content area and provides page-level context:

- **Page identity** — the current workspace's title and one-line description, resolved from the active route via `ROUTE_META`.
- **Sidebar toggle** — a menu icon for collapsing/expanding the Sidebar on smaller viewports.
- **Global search** *(UI present, wiring workspace-dependent)* — a search affordance for cross-workspace lookups.
- **Overall system status indicator** — a compact, color-coded summary ("All Systems Operational" / "Starting Up" / etc.) derived from `SystemStatusContext`, giving at-a-glance health awareness from anywhere in the app.
- **Notifications and user affordances** — bell and user icons, reserved for alert-center and account/profile functionality.

![Topbar](screenshots/topbar.png)

---

## 5. Dashboard

**Component:** `pages/Dashboard.jsx`

The Dashboard is the executive landing page — a single-glance summary that pulls from every domain without duplicating any of their internal logic. On mount, it fetches (in parallel, via `Promise.allSettled`):

- Aggregate statistics (`getDashboardStatistics`)
- The latest AI analysis cycle (`getLatestAIResult`)
- The five most recent reports (`getReports({ limit: 5 })`)

It composes this into summary tiles (system activity, AI health, active warnings, security posture) built from `Card`, `StatusBadge`, and `Loader`, plus a **Quick Actions** panel (Start Monitoring, Open Trinetra AI, Run Security Scan, View Reports) that deep-links into the relevant workspace. As documented in its own header comment, the Dashboard is "pure orchestration" — no scoring, aggregation, or threshold logic lives in this component; all of that is computed server-side.

![Dashboard](screenshots/dashboard.png)

---

## 6. Monitoring Workspace

**Page:** `pages/Monitoring.jsx` · **Components:** `monitoring/`

The Monitoring workspace is the real-time telemetry surface:

- **`LiveMetrics.jsx`** — current CPU, RAM, disk, and network readings.
- **`ProcessMonitoring.jsx`** — the live process table (top processes by resource usage).
- **`Graphs.jsx` / `Charts.jsx`** — Recharts-based visualizations of metric history.
- **`Controls.jsx`** — session controls: start/stop monitoring, reset the session, and force an immediate refresh, calling `startMonitoring`, `stopMonitoring`, `resetMonitoringSession`, and `refreshMetrics` respectively.

This workspace polls `services/api.js` on an interval and is the primary future consumer of the `monitoring.metrics` / `monitoring.processes` WebSocket channels once real-time push is implemented.

![Monitoring Workspace](screenshots/monitoring.png)

---

## 7. AI Workspace

**Page:** `pages/AIWorkspace.jsx` (branded "Trinetra AI" in navigation) · **Components:** `ai/`

The AI Workspace is a tabbed interface surfacing every AI analysis dimension as an equal, explorable tab:

| Tab | Component | Shows |
|---|---|---|
| Health Score | `HealthScore.jsx` | Overall score, status, contributing factors |
| Anomalies | `Anomalies.jsx` | Active anomalies, affected metrics, confidence, severity, detection time |
| Root Cause | `RootCause.jsx` | Identified issue, probable causes, affected components |
| Recommendations | `Recommendations.jsx` | Prioritized, categorized recommended actions |
| Trends | `Trends.jsx` | Per-metric Recharts trend series plus natural-language summary |
| Predictive | `Predictive.jsx` | Forecasted events, risk level, confidence, ETA, recommended action |
| AI Reports | `AIReports.jsx` | Filterable historical view across all of the above |

`AIEngine.jsx` sits above these tabs as the orchestration/overview component, fetching the latest and historical AI results (`getLatestAIResult`, `getAIResults`) and distributing them as props — individual tab components never re-derive AI output themselves, they only render what the backend already computed.

![AI Workspace](screenshots/ai-workspace.png)

---

## 8. Cybersecurity Workspace

**Page:** `pages/Cybersecurity.jsx` · **Components:** `cybersecurity/`

Structured as a parallel to the AI Workspace, covering security posture end-to-end:

| Component | Shows |
|---|---|
| `SecurityScore.jsx` | Aggregate security score and status |
| `ThreatOverview.jsx` | Active detected threats |
| `Firewall.jsx` | Firewall status and rule activity |
| `Ports.jsx` | Open port scan results |
| `Intrusion.jsx` | Intrusion detection events |
| `Vulnerabilities.jsx` | Known vulnerability scan results |

This workspace is designed to run and read independently from the AI Workspace — the two domains are correlated visually on the Dashboard, not through shared backend state.

> **Implementation status:** all six components listed above currently exist as empty files pending implementation, and their backing `backend/cybersecurity/` detector modules have not yet been created (see `docs/architecture.md` §9). Once implemented, capture and add `screenshots/cybersecurity.png` per the reference below.

![Cybersecurity Workspace](screenshots/cybersecurity.png)

---

## 9. Reports Workspace

**Page:** `pages/Reports.jsx` · **Components:** `reports/`

The historical record-keeping surface:

- **`TestRuns.jsx`** — searchable, sortable, paginated table of monitoring session runs (Run ID, start/end time, duration, total alerts, AI health score, overall status).
- **`Database.jsx`** — PostgreSQL connection status and stored-record statistics (total runs, metrics, process records, AI reports) plus recent database activity.
- **`ReportHistory.jsx`** — the full historical report list with search, type/health filters, sorting, and pagination.
- **`Export.jsx`** — the export workspace, offering CSV/JSON export (PDF marked future-ready) across Monitoring, AI, Cybersecurity, and Test Run report categories, with per-job progress and toast notifications.

None of these components generate or aggregate report data client-side — they exclusively render what `services/api.js` retrieves from PostgreSQL via the backend's report/statistics endpoints.

![Reports Workspace](screenshots/reports.png)

---

## 10. Settings Workspace

**Page:** `pages/Settings.jsx` · **Components:** `settings/`

A tabbed configuration surface:

- **`AlertPolicy.jsx`** — CPU/RAM/Disk/Network thresholds, severity level toggles, alert frequency, and a global alerts on/off switch.
- **`Preferences.jsx`** — monitoring interval, auto-refresh and dashboard refresh rate, default landing page, time format, and per-severity/channel notification toggles.
- **`Appearance.jsx`** — theme mode (dark shipped, light future-ready), sidebar width, card density, animation toggle, font size, and accent color (Lavender shipped, others future-ready) — each with a live inline preview.
- **`About.jsx`** — project identity, tagline, description, technology stack, live backend/AI/database/API status (via `SystemStatusContext`), license, and a developer information placeholder.

All four panels follow the same load → edit locally → Save/Reset pattern, persisting through `services/api.js`.

![Settings Workspace](screenshots/settings.png)

---

## 11. Reusable Components

**Location:** `frontend/src/components/`

The entire application is assembled from a small, shared set of primitives:

| Component | Purpose |
|---|---|
| `Card.jsx` | The fundamental content container — a titled, optionally-iconed panel used by virtually every workspace. |
| `StatusBadge.jsx` | Renders a severity/status string (`Critical`, `High`, `Healthy`, `Online`, `Unknown`, etc.) as a consistently colored pill. |
| `ProgressRing.jsx` | Circular progress indicator, used for scores (health score, security score). |
| `Loader.jsx` | Standard loading spinner with an accompanying label, shown during initial data fetches. |
| `Toast.jsx` | Notification surface (backed by `react-hot-toast`) for success/error feedback on actions like save and export. |
| `Modal.jsx` | Shared dialog/overlay primitive for confirmations and detail views. |

Every feature component across `ai/`, `monitoring/`, `cybersecurity/`, `reports/`, and `settings/` composes from this set rather than defining its own card, badge, or loading UI — this is what keeps the six workspaces visually unified.

> **Implementation status:** all six files above currently exist as empty stubs. Because every feature component across the application imports from this set (`Card`, `StatusBadge`, and `Loader` most heavily), implementing these primitives is a prerequisite for any workspace to render.

---

## 12. Color Palette

The Lavender Trinetra Design System is a **dark-first palette**, expressed as CSS custom properties with inline fallbacks throughout the codebase (`var(--color-*, #hex)`), so components remain themeable without a hard dependency on a global stylesheet being loaded first.

| Token | Fallback | Usage |
|---|---|---|
| `--color-bg` | `#0f1115` | Application background |
| `--color-bg-elevated` | `#161922` | Elevated surfaces (tooltips, dropdown panels) |
| `--color-surface` | `#171923` | Card/panel surfaces |
| `--color-border` | `#232733` | Borders, dividers, input outlines |
| `--color-text-primary` | `#f1f5f9` | Primary text, headings, values |
| `--color-text-secondary` | `#94a3b8` | Secondary text, labels |
| `--color-text-secondary` (muted) | `#64748b` | Tertiary/muted text, timestamps, helper copy |
| `--color-accent` | `#7c3aed` | Brand accent — the "Lavender" in Lavender Trinetra |

**Semantic status colors** (applied consistently via `StatusBadge` and severity-driven card borders across AI and cybersecurity surfaces):

| Meaning | Color family |
|---|---|
| Critical | Rose (`rose-500`) |
| High | Orange (`orange-500`) |
| Medium / Warning | Amber (`amber-500`) |
| Low / Healthy / Online | Emerald / Sky (`emerald-400`, `sky-500`) |
| Unknown / Offline | Neutral gray, muted |

The primary interactive/brand color throughout buttons, active nav states, and focus rings is **violet** (`violet-500`/`violet-600`), reinforcing the "Lavender" identity independently of the `--color-accent` token.

---

## 13. Design Language

- **Dark, low-glare surfaces** — near-black backgrounds with subtle elevation steps (`bg` → `surface` → `bg-elevated`) rather than stark panels, reducing eye strain for a monitoring tool meant to stay open for long sessions.
- **Card-first composition** — nearly every unit of information is a `Card` with a title, optional icon, and body; this repetition is intentional and is what makes six very different workspaces feel like one product.
- **Status through color, not just text** — severity and health are always color-coded (via `StatusBadge` and severity-tinted card borders), letting users scan for problems at a glance before reading any text.
- **Explainability in the UI, not just the data** — AI and security components consistently pair a number (score, confidence, probability) with a plain-language explanation, mirroring the backend's explainable-AI philosophy.
- **Iconography** — Phosphor Icons (`react-icons/pi`), bold weight, used consistently for navigation, section headers, and inline metadata (clock, gauge, timer, etc.).
- **Motion with restraint** — Framer Motion is used for structural transitions (sidebar collapse, tab switches) rather than decorative animation, and is itself toggleable via `Settings → Appearance → Animations`.
- **Typography** — a single sans-serif type scale, weight used to establish hierarchy (semibold for values and titles, regular for labels and body copy) rather than multiple typefaces.

---

## 14. Responsive Behaviour

- **Sidebar** — collapses to an icon-only rail below desktop widths (and manually via the collapse toggle at any width), preserving navigation access without consuming horizontal space on smaller screens.
- **Grid layouts** — dashboard tiles, AI/cybersecurity card grids, and settings threshold fields use responsive Tailwind grid classes (e.g. `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`), collapsing to a single column on narrow viewports.
- **Tables** — all data tables (`TestRuns`, `ReportHistory`) wrap in a horizontally scrollable container (`overflow-x-auto`) rather than truncating columns, keeping every field accessible on mobile without redesigning the table.
- **Toolbars** — search/filter/refresh toolbars stack vertically on narrow viewports (`flex-col` → `sm:flex-row`) rather than compressing controls.
- **Charts** — all Recharts visualizations use `ResponsiveContainer`, resizing fluidly with their parent card rather than fixed pixel dimensions.

---

## 15. User Flow

**Typical session:**

```
Land on Dashboard
    │
    ▼
Glance at system activity, AI health, alerts, security posture
    │
    ├──► Quick Action: "Start Monitoring" ──► Monitoring Workspace
    │        │
    │        ▼
    │    Watch live metrics/processes, manage session via Controls
    │
    ├──► Quick Action: "Open Trinetra AI" ──► AI Workspace
    │        │
    │        ▼
    │    Review Health Score → drill into Anomalies/Root Cause
    │    → read Recommendations → check Trends/Predictive
    │
    ├──► Quick Action: "Run Security Scan" ──► Cybersecurity Workspace
    │        │
    │        ▼
    │    Review Security Score → Threats/Firewall/Ports/Intrusion/
    │    Vulnerabilities
    │
    └──► Quick Action: "View Reports" ──► Reports Workspace
             │
             ▼
         Browse Test Runs / Report History → Export as needed
```

**Configuration flow (as-needed, not part of the primary loop):**

```
Sidebar → Settings
    │
    ├─ Alert Policy   → adjust thresholds/severity/frequency → Save
    ├─ Preferences    → adjust refresh/landing page/notifications → Save
    ├─ Appearance     → adjust density/font size/animations → Save
    └─ About          → verify live system status, license, version
```

Throughout every flow, the Sidebar's live status rows and the Topbar's overall status indicator remain visible, so the user never loses situational awareness of system/AI/database/API health while navigating between workspaces.

---

## 16. Future Enhancements

- **Real-time push** — replace interval polling across Monitoring, AI Workspace, and Cybersecurity with live WebSocket channels (`services/websocket.js` is already built for this; only the backend `/ws` endpoint is pending).
- **Light theme** — `Appearance.jsx` already has the toggle UI reserved (`theme_mode: "light"`); only the corresponding CSS variable set needs to be authored.
- **Additional accent colors** — `Appearance.jsx`'s accent color picker is scaffolded with Sky, Emerald, and Amber options locked behind a "coming soon" state.
- **Global command palette / search** — the Topbar's search affordance is present but not yet wired to a cross-workspace search index.
- **Notification center** — the Topbar's bell icon is reserved for a dedicated alert/notification history panel, likely backed by the same data as `AlertPolicy`'s severity configuration.
- **Authenticated, multi-user sessions** — user-specific preferences, saved report filters, and the Topbar's user icon are ready to be wired to a future auth system (see `docs/api.md` §3).
- **PDF export** — `reports/Export.jsx` already reserves a disabled "Soon" state for PDF alongside working CSV/JSON export.
- **Cybersecurity detail endpoints** — once `backend/cybersecurity/` exposes threat/firewall/port/intrusion/vulnerability endpoints individually (beyond the current aggregate `/score`), the corresponding frontend components can move from placeholder-ready to fully live.