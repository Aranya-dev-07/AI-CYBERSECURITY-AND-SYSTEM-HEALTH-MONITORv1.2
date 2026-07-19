import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  PiWarningCircleBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiGaugeBold,
  PiPulseBold,
  PiCpuBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";
import { getAnomalies } from "../services/api.js";

const REFRESH_INTERVAL_MS = 5000; // matches backend MONITOR_INTERVAL (config.py)

const SEVERITY_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };

const SEVERITY_STYLES = {
  Critical: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  High: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  Medium: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  Low: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatConfidence(confidence) {
  if (confidence == null || Number.isNaN(Number(confidence))) return "—";
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  return `${pct.toFixed(1)}%`;
}

function severityStyle(severity) {
  return SEVERITY_STYLES[severity] || "border-[var(--color-border,#232733)] bg-white/5 text-[var(--color-text-secondary,#94a3b8)]";
}

/**
 * Anomalies — displays AI anomaly detection results produced by the
 * backend (ai/anomaly_detection.py -> AnomalyDetectionEngine). Renders
 * each AnomalyResult (anomaly_id, timestamp, is_anomaly, anomaly_score,
 * confidence, severity, affected_metrics, top_process, evidence) as a
 * card, sorted by severity. Performs no detection logic itself.
 *
 * Props:
 *   anomalies (array)   — optional pre-fetched anomalies (e.g. from
 *                          AIWorkspace's latestResult.anomalies). When
 *                          provided, used as the initial render and as
 *                          a fallback if a background refresh fails.
 *   autoRefresh (bool)  — enable/disable polling. Default true.
 *   refreshInterval (number) — ms between polls. Default 5000.
 */
function Anomalies({ anomalies: initialAnomalies = [], autoRefresh = true, refreshInterval = REFRESH_INTERVAL_MS }) {
  const [anomalies, setAnomalies] = useState(initialAnomalies || []);
  const [isLoading, setIsLoading] = useState(!(initialAnomalies && initialAnomalies.length));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchAnomalies = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getAnomalies();
      if (!isMountedRef.current) return;
      setAnomalies(Array.isArray(data) ? data : data?.anomalies || []);
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load anomalies.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchAnomalies({ silent: Boolean(initialAnomalies && initialAnomalies.length) });

    let intervalId;
    if (autoRefresh) {
      intervalId = setInterval(() => fetchAnomalies({ silent: true }), refreshInterval);
    }

    return () => {
      isMountedRef.current = false;
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, fetchAnomalies]);

  const activeAnomalies = useMemo(() => {
    return (anomalies || [])
      .filter((a) => a?.is_anomaly !== false)
      .slice()
      .sort((a, b) => {
        const sevDiff = (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
        if (sevDiff !== 0) return sevDiff;
        return new Date(b.timestamp || 0) - new Date(a.timestamp || 0);
      });
  }, [anomalies]);

  if (isLoading) {
    return (
      <Card title="Active Anomalies" icon={PiWarningCircleBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading anomalies..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="Active Anomalies" icon={PiWarningCircleBold}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {activeAnomalies.length}
            </p>
            <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {activeAnomalies.length === 1 ? "anomaly currently active" : "anomalies currently active"}
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
              onClick={() => fetchAnomalies({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <p className="mt-3 text-xs text-rose-400">
            {error} — showing last known data.
          </p>
        )}
      </Card>

      {activeAnomalies.length === 0 ? (
        <Card>
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No active anomalies detected. System behavior is within expected bounds.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {activeAnomalies.map((anomaly) => (
            <div
              key={anomaly.anomaly_id}
              className={`rounded-xl border p-4 ${severityStyle(anomaly.severity)}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <StatusBadge status={anomaly.severity || "Unknown"} />
                  <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
                    ID: {anomaly.anomaly_id || "—"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
                  <PiClockBold className="h-3.5 w-3.5" />
                  {formatTimestamp(anomaly.timestamp)}
                </div>
              </div>

              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                    <PiPulseBold className="h-3.5 w-3.5" />
                    Affected Metrics
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(anomaly.affected_metrics || []).length ? (
                      anomaly.affected_metrics.map((metric) => (
                        <span
                          key={metric}
                          className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-text-primary,#f1f5f9)]"
                        >
                          {metric}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-[var(--color-text-secondary,#64748b)]">—</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                    <PiGaugeBold className="h-3.5 w-3.5" />
                    Confidence
                  </p>
                  <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {formatConfidence(anomaly.confidence)}
                  </p>
                </div>

                <div>
                  <p className="flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                    <PiCpuBold className="h-3.5 w-3.5" />
                    Top Process
                  </p>
                  <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {anomaly.top_process || "—"}
                  </p>
                </div>
              </div>

              {anomaly.evidence && Object.keys(anomaly.evidence).length > 0 && (
                <div className="mt-3 border-t border-white/10 pt-2">
                  <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Evidence</p>
                  <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
                    {Object.entries(anomaly.evidence).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-2 text-xs">
                        <span className="capitalize text-[var(--color-text-secondary,#64748b)]">
                          {key.replace(/_/g, " ")}
                        </span>
                        <span className="text-[var(--color-text-primary,#f1f5f9)]">
                          {typeof value === "number" ? value.toFixed?.(2) ?? value : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Anomalies;