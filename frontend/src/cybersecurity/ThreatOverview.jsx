import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiShieldWarningBold,
  PiFireBold,
  PiChartBarBold,
  PiChartLineBold,
  PiBellRingingBold,
  PiClockBold,
  PiArrowsClockwiseBold,
} from "react-icons/pi";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { getThreatSummary, getActiveThreats, getRecentThreats } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;
const RECENT_LIMIT = 50;
const TIMELINE_BUCKETS = 12;

const SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"];

const SEVERITY_COLOR = {
  Low: "#a3c266",
  Medium: "#e879c9",
  High: "#f87171",
  Critical: "#f87171",
};

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function highestSeverity(counts) {
  for (let i = SEVERITY_ORDER.length - 1; i >= 0; i -= 1) {
    const level = SEVERITY_ORDER[i];
    if ((counts?.[level] || 0) > 0) return level;
  }
  return null;
}

/**
 * buildTimeline — buckets already-timestamped threats (from
 * threat_detector.py::get_recent_threats) into a fixed number of
 * equal-width time windows and counts threats per bucket. Pure
 * client-side grouping/counting for display purposes only - the
 * severity/threat determination itself was already made by the
 * backend; nothing here re-detects or re-scores anything.
 */
function buildTimeline(threats) {
  if (!threats.length) return [];
  const times = threats.map((t) => new Date(t.timestamp).getTime()).filter((t) => !Number.isNaN(t));
  if (!times.length) return [];

  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = Math.max(max - min, 60_000);
  const bucketSize = span / TIMELINE_BUCKETS;

  const buckets = Array.from({ length: TIMELINE_BUCKETS }, (_, i) => ({
    bucketStart: min + i * bucketSize,
    count: 0,
  }));

  threats.forEach((t) => {
    const time = new Date(t.timestamp).getTime();
    if (Number.isNaN(time)) return;
    const index = Math.min(TIMELINE_BUCKETS - 1, Math.floor((time - min) / bucketSize));
    if (buckets[index]) buckets[index].count += 1;
  });

  return buckets;
}

function TimelineTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-bg-elevated,#161922)] px-3 py-2 text-xs shadow-lg">
      <p className="text-[var(--color-text-secondary,#64748b)]">{formatTime(point.bucketStart)}</p>
      <p className="font-medium text-[var(--color-text-primary,#f1f5f9)]">{point.count} threat(s)</p>
    </div>
  );
}

/**
 * ThreatOverview — the overall threat detection workspace. Summarizes
 * active threats, severity distribution, a recent threat timeline,
 * and the latest security alerts, all sourced from the backend
 * threat_detector.py via services/api.js. Purely presentational: it
 * counts and charts risk data the backend already computed and
 * assigns no severities of its own.
 */
function ThreatOverview() {
  const [summary, setSummary] = useState(null);
  const [activeThreats, setActiveThreats] = useState([]);
  const [recentThreats, setRecentThreats] = useState([]);

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
        getThreatSummary(),
        getActiveThreats("Medium"),
        getRecentThreats(RECENT_LIMIT),
      ]);
      if (!isMountedRef.current) return;

      const [summaryRes, activeRes, recentRes] = results;
      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);
      if (activeRes.status === "fulfilled") setActiveThreats(activeRes.value || []);
      if (recentRes.status === "fulfilled") setRecentThreats(recentRes.value || []);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some threat data could not be loaded.");
        if (!silent) toast.error("Some threat data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load threat overview.");
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

  const distributionData = useMemo(
    () =>
      SEVERITY_ORDER.map((level) => ({
        severity: level,
        count: summary?.counts?.[level] || 0,
      })),
    [summary]
  );

  const timelineData = useMemo(() => buildTimeline(recentThreats), [recentThreats]);

  const overallSeverity = useMemo(() => highestSeverity(summary?.counts), [summary]);
  const overallStatus = overallSeverity
    ? overallSeverity
    : (summary?.total ?? 0) === 0
    ? "healthy"
    : "healthy";

  if (isLoading) {
    return (
      <Card title="Threat Overview" icon={PiShieldWarningBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading threat overview..." />
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
            <PiShieldWarningBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Threat Overview
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

      {/* Overall Threat Status + Active Threats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card title="Overall Threat Status" icon={PiFireBold}>
          <StatusBadge status={overallStatus} />
          <p className="mt-2 text-sm text-[var(--color-text-secondary,#94a3b8)]">
            {summary?.total ?? 0} threat(s) recorded in the recent window.
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
            Last updated {formatTimestamp(summary?.generated_at)}
          </p>
        </Card>

        <Card title="Active Threats" icon={PiShieldWarningBold}>
          <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {activeThreats.length}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
            at Medium severity or above
          </p>
        </Card>
      </div>

      {/* Threat Severity Distribution */}
      <Card title="Threat Severity Distribution" icon={PiChartBarBold}>
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={distributionData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" vertical={false} />
              <XAxis
                dataKey="severity"
                tick={{ fill: "#64748b", fontSize: 12 }}
                axisLine={{ stroke: "var(--color-border,#232733)" }}
                tickLine={false}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={28}
              />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
                contentStyle={{
                  background: "var(--color-bg-elevated,#161922)",
                  border: "1px solid var(--color-border,#232733)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {distributionData.map((entry) => (
                  <Cell key={entry.severity} fill={SEVERITY_COLOR[entry.severity]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Threat Timeline */}
      <Card title="Threat Timeline" icon={PiChartLineBold}>
        {timelineData.length ? (
          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="threat-timeline-gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f87171" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" vertical={false} />
                <XAxis
                  dataKey="bucketStart"
                  tickFormatter={formatTime}
                  tick={{ fill: "#64748b", fontSize: 11 }}
                  axisLine={{ stroke: "var(--color-border,#232733)" }}
                  tickLine={false}
                  minTickGap={24}
                />
                <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip content={<TimelineTooltip />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#f87171"
                  strokeWidth={2}
                  fill="url(#threat-timeline-gradient)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
            Not enough recent threat data to chart a timeline yet.
          </p>
        )}
      </Card>

      {/* Latest Security Alerts */}
      <Card title="Latest Security Alerts" icon={PiBellRingingBold}>
        {recentThreats.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No security alerts recorded yet.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {recentThreats.slice(0, 8).map((threat) => (
              <div
                key={threat.threat_id}
                className="flex flex-col gap-1 rounded-lg border border-[var(--color-border,#232733)] p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-start gap-2">
                  <StatusBadge status={threat.severity} size="sm" />
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {threat.title}
                    </p>
                    <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">{threat.reason}</p>
                  </div>
                </div>
                <span className="whitespace-nowrap text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatTimestamp(threat.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default ThreatOverview;