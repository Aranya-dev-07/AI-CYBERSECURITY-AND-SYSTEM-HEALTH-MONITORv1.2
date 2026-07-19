import { useEffect, useRef, useState, useCallback } from "react";
import {
  PiDatabaseBold,
  PiListChecksBold,
  PiChartLineBold,
  PiCpuBold,
  PiBrainBold,
  PiHardDrivesBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiPulseBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";
import { getDashboardStatistics } from "../services/api.js";

const REFRESH_INTERVAL_MS = 30000;

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString();
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

/**
 * Database — displays PostgreSQL connection status and aggregate
 * stored-record statistics. All data is sourced from the backend via
 * services/api.js (GET /api/status for connectivity, and the
 * dashboard statistics aggregate produced by
 * database/crud.py::get_dashboard_statistics). This component never
 * talks to PostgreSQL directly and performs no aggregation itself.
 *
 * Props:
 *   stats (object)           — optional pre-fetched dashboard
 *                               statistics (e.g. from Reports.jsx's
 *                               getDashboardStatistics() call). Used
 *                               as initial render; refresh re-fetches.
 *   autoRefresh (bool)       — enable/disable polling. Default true.
 *   refreshInterval (number) — ms between polls. Default 30000.
 */
function Database({ stats: initialStats = null, autoRefresh = true, refreshInterval = REFRESH_INTERVAL_MS }) {
  const { status } = useSystemStatus();
  const [stats, setStats] = useState(initialStats);
  const [isLoading, setIsLoading] = useState(!initialStats);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchStats = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getDashboardStatistics();
      if (!isMountedRef.current) return;
      setStats(data);
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load database statistics.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchStats({ silent: Boolean(initialStats) });

    let intervalId;
    if (autoRefresh) {
      intervalId = setInterval(() => fetchStats({ silent: true }), refreshInterval);
    }

    return () => {
      isMountedRef.current = false;
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, fetchStats]);

  const dbStatus = status?.database ?? "unknown";
  const latestRun = stats?.latest_run;

  if (isLoading) {
    return (
      <Card title="Database" icon={PiDatabaseBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading database statistics..." />
        </div>
      </Card>
    );
  }

  return (
    <Card title="Database" icon={PiDatabaseBold}>
      <div className="flex flex-col gap-4">
        {/* Connection status + refresh */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
              Connection Status
            </span>
            <StatusBadge status={dbStatus} />
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
              onClick={() => fetchStats({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <p className="text-xs text-rose-400">{error} — showing last known data.</p>
        )}

        {/* Record counts */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-[var(--color-border,#232733)] p-3">
            <p className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
              <PiListChecksBold className="h-3.5 w-3.5" />
              Total Test Runs
            </p>
            <p className="mt-1 text-xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {formatNumber(stats?.total_runs)}
            </p>
          </div>

          <div className="rounded-lg border border-[var(--color-border,#232733)] p-3">
            <p className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
              <PiChartLineBold className="h-3.5 w-3.5" />
              Total Metrics Stored
            </p>
            <p className="mt-1 text-xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {formatNumber(stats?.total_metric_samples)}
            </p>
          </div>

          <div className="rounded-lg border border-[var(--color-border,#232733)] p-3">
            <p className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
              <PiCpuBold className="h-3.5 w-3.5" />
              Total Process Records
            </p>
            <p className="mt-1 text-xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {formatNumber(stats?.total_process_samples)}
            </p>
          </div>

          <div className="rounded-lg border border-[var(--color-border,#232733)] p-3">
            <p className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
              <PiBrainBold className="h-3.5 w-3.5" />
              Total AI Reports
            </p>
            <p className="mt-1 text-xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {formatNumber(stats?.total_ai_results)}
            </p>
          </div>
        </div>

        {/* Storage statistics */}
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]">
            <PiHardDrivesBold className="h-3.5 w-3.5" />
            Storage Statistics
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Avg CPU</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatPercent(stats?.avg_cpu)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Peak CPU</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatPercent(stats?.peak_cpu)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Avg RAM</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatPercent(stats?.avg_ram)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Peak RAM</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatPercent(stats?.peak_ram)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Avg Disk Usage</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatPercent(stats?.avg_disk_usage)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Total Alerts</p>
              <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                {formatNumber(stats?.total_alerts)}
              </p>
            </div>
          </div>
        </div>

        {/* Recent activity */}
        <div className="border-t border-white/10 pt-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]">
            <PiPulseBold className="h-3.5 w-3.5" />
            Recent Activity
          </p>
          {latestRun ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/5 p-3 text-sm">
              <div>
                <p className="font-medium text-[var(--color-text-primary,#f1f5f9)]">
                  Run {latestRun.run_id ?? latestRun.id ?? "—"}
                </p>
                <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                  Started {formatTimestamp(latestRun.start_time)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {stats?.latest_health_score != null && (
                  <span className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
                    Health {stats.latest_health_score}/100
                  </span>
                )}
                <StatusBadge status={stats?.latest_health_status || latestRun.status || "Unknown"} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
              No recent database activity recorded.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

export default Database;