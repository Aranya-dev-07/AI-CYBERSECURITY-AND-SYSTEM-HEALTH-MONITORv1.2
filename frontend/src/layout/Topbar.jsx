import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  PiListBold,
  PiMagnifyingGlassBold,
  PiBellBold,
  PiUserCircleBold,
} from "react-icons/pi";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";

const ROUTE_META = {
  "/": {
    title: "Dashboard",
    description: "Unified overview of system health, alerts, and activity.",
  },
  "/dashboard": {
    title: "Dashboard",
    description: "Unified overview of system health, alerts, and activity.",
  },
  "/monitoring": {
    title: "Monitoring",
    description: "Live CPU, RAM, disk, and network telemetry.",
  },
  "/ai-workspace": {
    title: "Trinetra AI",
    description: "Explainable anomaly detection, predictions, and recommendations.",
  },
  "/cybersecurity": {
    title: "Cybersecurity",
    description: "Threats, firewall activity, and vulnerability posture.",
  },
  "/reports": {
    title: "Reports",
    description: "Session history and exportable monitoring summaries.",
  },
  "/settings": {
    title: "Settings",
    description: "Alert policy, preferences, and application configuration.",
  },
};

const DEFAULT_META = {
  title: "Lavender Trinetra",
  description: "Observe. Learn. Protect.",
};

const OVERALL_STATUS_META = {
  online: { label: "All Systems Operational", dotClass: "bg-emerald-400" },
  starting: { label: "Starting Up", dotClass: "bg-amber-400" },
  offline: { label: "Systems Offline", dotClass: "bg-rose-500" },
};

function useLiveClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  return now;
}

function deriveOverallStatus(status) {
  const values = [status?.aiEngine, status?.database, status?.api];
  if (values.some((v) => v === "offline")) return "offline";
  if (values.some((v) => v === "starting")) return "starting";
  if (values.every((v) => v === "online")) return "online";
  return "offline";
}

/**
 * Topbar — global topbar rendered inside AppShell's sticky header.
 *
 * Props:
 *   isSidebarCollapsed (bool) — current sidebar collapse state.
 *   onToggleSidebar (func)    — toggles the sidebar (mirrors Sidebar's own toggle).
 */
function Topbar({ isSidebarCollapsed = false, onToggleSidebar }) {
  const location = useLocation();
  const now = useLiveClock();
  const { status } = useSystemStatus();

  const meta = useMemo(() => ROUTE_META[location.pathname] || DEFAULT_META, [location.pathname]);
  const overallStatus = deriveOverallStatus(status);
  const statusMeta = OVERALL_STATUS_META[overallStatus];

  const formattedDate = now.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const formattedTime = now.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="flex h-16 items-center justify-between gap-4 px-4 md:px-6">
      {/* Left: sidebar toggle + title/description */}
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="hidden h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)] md:flex"
          aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <PiListBold className="h-5 w-5" />
        </button>

        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold leading-tight text-[var(--color-text-primary,#f1f5f9)] md:text-lg">
            {meta.title}
          </h1>
          <p className="hidden truncate text-xs text-[var(--color-text-secondary,#94a3b8)] sm:block">
            {meta.description}
          </p>
        </div>
      </div>

      {/* Center: search placeholder (prepared for future global search) */}
      <div className="hidden max-w-md flex-1 md:flex">
        <div className="flex w-full items-center gap-2 rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-bg,#0f1115)] px-3 py-2 text-sm text-[var(--color-text-secondary,#64748b)] shadow-inner transition-colors focus-within:border-violet-500/50">
          <PiMagnifyingGlassBold className="h-4 w-4 flex-shrink-0" />
          <input
            type="text"
            placeholder="Search metrics, alerts, processes..."
            disabled
            className="w-full bg-transparent text-sm text-[var(--color-text-primary,#f1f5f9)] placeholder:text-[var(--color-text-secondary,#64748b)] focus:outline-none disabled:cursor-not-allowed"
          />
          <kbd className="hidden flex-shrink-0 rounded-md border border-[var(--color-border,#232733)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text-secondary,#64748b)] lg:inline-block">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right: date/time, status, notifications, profile */}
      <div className="flex flex-shrink-0 items-center gap-2 md:gap-3">
        <div className="hidden flex-col items-end leading-tight lg:flex">
          <span className="text-xs font-medium text-[var(--color-text-primary,#f1f5f9)]">
            {formattedTime}
          </span>
          <span className="text-[11px] text-[var(--color-text-secondary,#64748b)]">
            {formattedDate}
          </span>
        </div>

        <div
          className="hidden items-center gap-2 rounded-full border border-[var(--color-border,#232733)] bg-[var(--color-bg,#0f1115)] px-3 py-1.5 shadow-sm sm:flex"
          title={statusMeta.label}
        >
          <span className={`h-2 w-2 rounded-full ${statusMeta.dotClass}`} />
          <span className="text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
            {statusMeta.label}
          </span>
        </div>

        <button
          type="button"
          className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
          aria-label="Notifications"
        >
          <PiBellBold className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-violet-400" />
        </button>

        <button
          type="button"
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-sm transition-transform hover:scale-105"
          aria-label="User profile"
        >
          <PiUserCircleBold className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

export default Topbar;