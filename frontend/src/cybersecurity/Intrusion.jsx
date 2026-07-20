import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiWarningOctagonBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiMapPinBold,
  PiTargetBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { getRecentIntrusions } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;
const INTRUSIONS_LIMIT = 100;

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatCategory(category) {
  if (!category) return null;
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Intrusion — displays active intrusion detection alerts for the
 * Cybersecurity workspace: severity, time, source, and an explainable
 * reason for each alert. Sourced entirely from intrusion_detection.py
 * via services/api.js. Purely presentational — implements no
 * intrusion detection or correlation logic of its own.
 */
function Intrusion() {
  const [intrusions, setIntrusions] = useState([]);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchIntrusions = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getRecentIntrusions(INTRUSIONS_LIMIT);
      if (!isMountedRef.current) return;
      setIntrusions(Array.isArray(data) ? data : data?.intrusions || []);
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load intrusion alerts.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchIntrusions();
    const intervalId = setInterval(() => fetchIntrusions({ silent: true }), REFRESH_INTERVAL_MS);
    return () => {
      isMountedRef.current = false;
      clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchIntrusions]);

  const sortedIntrusions = useMemo(() => {
    const rank = { critical: 0, high: 1, medium: 2, low: 3 };
    return [...intrusions].sort((a, b) => {
      const severityDiff =
        (rank[String(a.severity).toLowerCase()] ?? 9) - (rank[String(b.severity).toLowerCase()] ?? 9);
      if (severityDiff !== 0) return severityDiff;
      return new Date(b.timestamp || 0) - new Date(a.timestamp || 0);
    });
  }, [intrusions]);

  if (isLoading) {
    return (
      <Card title="Active Intrusion Alerts" icon={PiWarningOctagonBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading intrusion alerts..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="Active Intrusion Alerts" icon={PiWarningOctagonBold}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {sortedIntrusions.length}
            </p>
            <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {sortedIntrusions.length === 1 ? "alert recorded" : "alerts recorded"}
            </p>
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
              onClick={() => fetchIntrusions({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-3 text-xs text-rose-400">{error} — showing last known data.</p>
        )}
      </Card>

      {sortedIntrusions.length === 0 ? (
        <Card>
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No intrusion alerts recorded. Network, port, and session activity is within
            expected bounds.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {sortedIntrusions.map((alert) => (
            <div
              key={alert.alert_id}
              className="rounded-xl border border-[var(--color-border,#232733)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <StatusBadge status={alert.severity || "unknown"} />
                  {alert.category && (
                    <span className="flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      <PiTargetBold className="h-3 w-3" />
                      {formatCategory(alert.category)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
                  <PiClockBold className="h-3.5 w-3.5" />
                  {formatTimestamp(alert.timestamp)}
                </div>
              </div>

              <div className="mt-3 flex items-center gap-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                <PiMapPinBold className="h-3.5 w-3.5 text-[var(--color-text-secondary,#64748b)]" />
                Source: {alert.source || "Unknown"}
              </div>

              <p className="mt-2 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                {alert.reason || "No further explanation provided."}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Intrusion;