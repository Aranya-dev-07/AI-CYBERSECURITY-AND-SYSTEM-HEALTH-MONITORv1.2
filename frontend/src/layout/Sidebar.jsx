import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  PiHouseBold,
  PiChartLineBold,
  PiBrainBold,
  PiShieldCheckeredBold,
  PiFileTextBold,
  PiGearSixBold,
  PiCaretLeftBold,
  PiEyeBold,
} from "react-icons/pi";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";

const APP_VERSION = "1.0.0";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: PiHouseBold },
  { to: "/monitoring", label: "Monitoring", icon: PiChartLineBold },
  { to: "/ai-workspace", label: "Trinetra AI", icon: PiBrainBold },
  { to: "/cybersecurity", label: "Cybersecurity", icon: PiShieldCheckeredBold },
  { to: "/reports", label: "Reports", icon: PiFileTextBold },
  { to: "/settings", label: "Settings", icon: PiGearSixBold },
];

const STATUS_META = {
  online: { label: "Online", dotClass: "bg-emerald-400", glow: "shadow-[0_0_6px_2px_rgba(52,211,153,0.5)]" },
  starting: { label: "Starting", dotClass: "bg-amber-400", glow: "shadow-[0_0_6px_2px_rgba(251,191,36,0.5)]" },
  offline: { label: "Offline", dotClass: "bg-rose-500", glow: "shadow-[0_0_6px_2px_rgba(244,63,94,0.5)]" },
};

function StatusRow({ label, status, isCollapsed }) {
  const meta = STATUS_META[status] || STATUS_META.offline;

  return (
    <div
      className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-[var(--color-text-secondary,#94a3b8)] ${
        isCollapsed ? "justify-center" : "justify-between"
      }`}
      title={`${label}: ${meta.label}`}
    >
      {!isCollapsed && <span className="truncate">{label}</span>}
      <span className="flex items-center gap-1.5">
        {!isCollapsed && <span className="font-medium">{meta.label}</span>}
        <span className={`h-2 w-2 rounded-full ${meta.dotClass} ${meta.glow}`} />
      </span>
    </div>
  );
}

/**
 * Sidebar — primary navigation for Lavender Trinetra.
 *
 * Props:
 *   isCollapsed (bool)       — collapsed/expanded width state, owned by AppShell.
 *   onToggleCollapse (func)  — toggles the collapsed state.
 */
function Sidebar({ isCollapsed = false, onToggleCollapse }) {
  const { status } = useSystemStatus();

  const aiEngineStatus = status?.aiEngine ?? "offline";
  const databaseStatus = status?.database ?? "offline";
  const apiStatus = status?.api ?? "offline";

  return (
    <div className="flex h-full flex-col">
      {/* Logo + tagline */}
      <div
        className={`flex items-center gap-3 border-b border-[var(--color-border,#232733)] px-4 py-5 ${
          isCollapsed ? "justify-center px-2" : ""
        }`}
      >
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 shadow-lg shadow-violet-900/30">
          <PiEyeBold className="h-5 w-5 text-white" />
        </div>
        {!isCollapsed && (
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-wide text-[var(--color-text-primary,#f1f5f9)]">
              Lavender Trinetra
            </p>
            <p className="truncate text-[11px] text-[var(--color-text-secondary,#94a3b8)]">
              Observe. Learn. Protect.
            </p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors duration-150",
                isCollapsed ? "justify-center px-2" : "",
                isActive
                  ? "bg-violet-600/15 text-violet-300"
                  : "text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]",
              ].join(" ")
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="sidebar-active-indicator"
                    className="absolute left-0 h-6 w-1 rounded-r-full bg-violet-400"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <Icon
                  className={`h-5 w-5 flex-shrink-0 transition-transform duration-150 group-hover:scale-110 ${
                    isActive ? "text-violet-300" : ""
                  }`}
                />
                {!isCollapsed && <span className="truncate">{label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className={`mx-3 mb-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)] ${
          isCollapsed ? "justify-center" : ""
        }`}
        aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <PiCaretLeftBold
          className={`h-4 w-4 transition-transform duration-200 ${isCollapsed ? "rotate-180" : ""}`}
        />
        {!isCollapsed && <span>Collapse</span>}
      </button>

      {/* Status panel */}
      <div
        className={`border-t border-[var(--color-border,#232733)] px-3 py-3 ${
          isCollapsed ? "px-2" : ""
        }`}
      >
        {!isCollapsed && (
          <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
            Version {APP_VERSION}
          </p>
        )}
        <div className="space-y-0.5">
          <StatusRow label="AI Engine" status={aiEngineStatus} isCollapsed={isCollapsed} />
          <StatusRow label="Database" status={databaseStatus} isCollapsed={isCollapsed} />
          <StatusRow label="API" status={apiStatus} isCollapsed={isCollapsed} />
        </div>
      </div>
    </div>
  );
}

export default Sidebar;