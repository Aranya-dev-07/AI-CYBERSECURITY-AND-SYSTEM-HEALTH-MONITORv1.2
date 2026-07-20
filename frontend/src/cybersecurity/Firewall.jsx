import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiLockKeyBold,
  PiLockKeyOpenBold,
  PiShieldCheckBold,
  PiShieldSlashBold,
  PiGaugeBold,
  PiClockCounterClockwiseBold,
  PiBellRingingBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiWarningCircleBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { getFirewallStatus, getRecentFirewallEvents } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;
const EVENTS_LIMIT = 50;

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

/**
 * deriveProtectionLevel — a presentational label derived from fields
 * the backend (firewall_monitor.py) already computed (available,
 * enabled, risk_reasons). No new detection or evaluation happens
 * here; this only chooses a human-readable category and badge status
 * for what firewall_monitor.py already determined.
 */
function deriveProtectionLevel(status) {
  if (!status) return { label: "Unknown", badge: "unknown" };
  if (!status.available) return { label: "None", badge: "critical" };
  if (status.enabled === false) return { label: "None", badge: "critical" };
  if (status.enabled === null || status.enabled === undefined) {
    return { label: "Unverified", badge: "warning" };
  }
  if ((status.risk_reasons || []).length > 0) {
    return { label: "Partial", badge: "warning" };
  }
  return { label: "Strong", badge: "healthy" };
}

const EVENT_LABELS = {
  firewall_status_changed: "Status Changed",
  firewall_disabled: "Firewall Disabled",
  firewall_unavailable: "Firewall Unavailable",
};

/**
 * Firewall — displays firewall monitoring information for the
 * Cybersecurity workspace: current status, a derived protection
 * level, a short status history, and recent change events. Sourced
 * entirely from firewall_monitor.py via services/api.js. Purely
 * presentational — implements no firewall detection or evaluation
 * logic of its own.
 */
function Firewall() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchAll = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const results = await Promise.allSettled([
        getFirewallStatus(),
        getRecentFirewallEvents(EVENTS_LIMIT),
      ]);
      if (!isMountedRef.current) return;

      const [statusRes, eventsRes] = results;
      if (statusRes.status === "fulfilled") setStatus(statusRes.value);
      if (eventsRes.status === "fulfilled") setEvents(eventsRes.value || []);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some firewall data could not be loaded.");
        if (!silent) toast.error("Some firewall data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load firewall information.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchAll();
    const intervalId = setInterval(() => fetchAll({ silent: true }), REFRESH_INTERVAL_MS);
    return () => {
      isMountedRef.current = false;
      clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchAll]);

  const statusHistory = useMemo(
    () => events.filter((e) => e.type === "firewall_status").slice(-10).reverse(),
    [events]
  );

  const recentChangeEvents = useMemo(
    () =>
      events
        .filter((e) => e.type && e.type !== "firewall_status")
        .slice()
        .reverse(),
    [events]
  );

  const protection = useMemo(() => deriveProtectionLevel(status), [status]);

  if (isLoading) {
    return (
      <Card title="Firewall" icon={PiLockKeyBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading firewall status..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header / refresh */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {status?.enabled ? (
              <PiLockKeyBold className="h-5 w-5 text-violet-400" />
            ) : (
              <PiLockKeyOpenBold className="h-5 w-5 text-violet-400" />
            )}
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Firewall
            </h2>
          </div>
          <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary,#64748b)]">
            {isRefreshing && (
              <span className="flex items-center gap-1">
                <PiArrowsClockwiseBold className="h-3.5 w-3.5 animate-spin" />
                Refreshing…
              </span>
            )}
            <span className="flex items-center gap-1">
              <PiClockBold className="h-3.5 w-3.5" />
              Updated {lastFetched ? lastFetched.toLocaleTimeString() : "—"}
            </span>
            <button
              type="button"
              onClick={() => fetchAll({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-rose-400">{error} — showing last known data.</p>}
      </Card>

      {/* Firewall Status + Protection Level */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card
          title="Firewall Status"
          icon={status?.available ? PiShieldCheckBold : PiShieldSlashBold}
        >
          <StatusBadge
            status={!status?.available ? "critical" : status?.enabled ? "healthy" : "critical"}
          />
          <p className="mt-2 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
            {status?.backend || "No backend detected"}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">{status?.platform || "—"}</p>
          <p className="mt-2 text-xs text-[var(--color-text-secondary,#94a3b8)]">
            {status?.detail || "Firewall status unavailable"}
          </p>

          {status?.profiles && Object.keys(status.profiles).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(status.profiles).map(([name, on]) => (
                <span
                  key={name}
                  className="flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-1 text-xs text-[var(--color-text-primary,#f1f5f9)]"
                >
                  {name}
                  <StatusBadge status={on ? "healthy" : "critical"} size="sm" showLabel={false} />
                </span>
              ))}
            </div>
          )}
        </Card>

        <Card title="Protection Level" icon={PiGaugeBold}>
          <StatusBadge status={protection.badge} />
          <p className="mt-2 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {protection.label}
          </p>
          {(status?.risk_reasons || []).length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1">
              {status.risk_reasons.map((reason, index) => (
                <li
                  key={index}
                  className="flex items-start gap-1.5 text-xs text-[var(--color-text-secondary,#94a3b8)]"
                >
                  <PiWarningCircleBold className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-400" />
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-[var(--color-text-secondary,#64748b)]">
              No contributing risk factors detected.
            </p>
          )}
        </Card>
      </div>

      {/* Status History */}
      <Card title="Status History" icon={PiClockCounterClockwiseBold}>
        {statusHistory.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No status history recorded yet.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {statusHistory.map((entry, index) => (
              <div
                key={`${entry.timestamp}-${index}`}
                className="flex items-center justify-between rounded-lg border border-[var(--color-border,#232733)] px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge
                    status={!entry.available ? "critical" : entry.enabled ? "healthy" : "critical"}
                    size="sm"
                  />
                  <span className="text-xs text-[var(--color-text-primary,#f1f5f9)]">
                    {entry.backend || "unknown backend"}
                  </span>
                </div>
                <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatTimestamp(entry.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Recent Events */}
      <Card title="Recent Events" icon={PiBellRingingBold}>
        {recentChangeEvents.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No firewall change events recorded yet.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {recentChangeEvents.slice(0, 10).map((event, index) => (
              <div
                key={`${event.timestamp}-${index}`}
                className="flex flex-col gap-1 rounded-lg border border-[var(--color-border,#232733)] p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-start gap-2">
                  <StatusBadge status={event.risk_level || "unknown"} size="sm" />
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {EVENT_LABELS[event.type] || event.type}
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">{event.detail}</p>
                  </div>
                </div>
                <span className="whitespace-nowrap text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatTimestamp(event.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default Firewall;