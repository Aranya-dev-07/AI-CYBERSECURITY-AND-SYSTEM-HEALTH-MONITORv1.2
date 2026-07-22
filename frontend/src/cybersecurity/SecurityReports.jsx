import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiFileTextBold,
  PiShieldWarningBold,
  PiListChecksBold,
  PiChartLineUpBold,
  PiLightbulbBold,
  PiDownloadSimpleBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiWarningOctagonBold,
} from "react-icons/pi";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";

import Card from "../components/Card.jsx";
import ProgressRing from "../components/ProgressRing.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import {
  getSecurityReportSummary,
  getSecurityReportThreatStatistics,
  getSecurityReportIncidentSummary,
  getSecurityReportScoreTrends,
  getSecurityReportRecommendationSummary,
  exportSecurityReport,
} from "../services/api.js";

const REFRESH_INTERVAL_MS = 20000;
const WINDOW_DAYS = 7;
const RECENT_LIMIT = 10;

const SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"];
const SEVERITY_COLOR = {
  Low: "#a3c266",
  Medium: "#e879c9",
  High: "#f87171",
  Critical: "#f87171",
};

const GRADE_TO_RING_COLOR = {
  Excellent: "olive",
  Good: "lavender",
  Fair: "magenta",
  Poor: "red",
  Critical: "red",
};

const DIRECTION_STATUS = {
  improving: "healthy",
  stable: "warning",
  declining: "critical",
};

const EXPORT_FORMATS = [
  { value: "json", label: "JSON" },
  { value: "csv", label: "CSV" },
];

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatLabel(value) {
  if (!value) return "";
  return String(value).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function downloadJsonFile(payload, filename) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * SecurityReports — the Cybersecurity Reports workspace: Security
 * Summary, Threat Statistics, Incident Summary, Security Score
 * Trends, Recommendation Summary, and report export. All data is
 * sourced exclusively from security_reports.py via services/api.js -
 * this component implements no aggregation, scoring, or reporting
 * logic of its own; it only fetches, shapes for display, and renders
 * what the backend already computed.
 */
function SecurityReports() {
  const [summary, setSummary] = useState(null);
  const [threatStats, setThreatStats] = useState(null);
  const [incidentSummary, setIncidentSummary] = useState(null);
  const [scoreTrends, setScoreTrends] = useState(null);
  const [recommendationSummary, setRecommendationSummary] = useState(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState("json");
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchAll = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const results = await Promise.allSettled([
        getSecurityReportSummary({ windowDays: WINDOW_DAYS }),
        getSecurityReportThreatStatistics({ windowDays: WINDOW_DAYS }),
        getSecurityReportIncidentSummary({ limit: RECENT_LIMIT }),
        getSecurityReportScoreTrends({ limit: 100 }),
        getSecurityReportRecommendationSummary({ limit: RECENT_LIMIT }),
      ]);
      if (!isMountedRef.current) return;

      const [summaryRes, threatRes, incidentRes, trendRes, recommendationRes] = results;
      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);
      if (threatRes.status === "fulfilled") setThreatStats(threatRes.value);
      if (incidentRes.status === "fulfilled") setIncidentSummary(incidentRes.value);
      if (trendRes.status === "fulfilled") setScoreTrends(trendRes.value);
      if (recommendationRes.status === "fulfilled") setRecommendationSummary(recommendationRes.value);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some report data could not be loaded.");
        if (!silent) toast.error("Some report data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load the security reports workspace.");
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

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      const envelope = await exportSecurityReport({
        exportFormat,
        windowDays: WINDOW_DAYS,
        limit: RECENT_LIMIT,
      });
      const filename = `security-report-${new Date().toISOString().slice(0, 10)}.${
        exportFormat === "csv" ? "csv.json" : "json"
      }`;
      downloadJsonFile(envelope, filename);
      toast.success("Security report exported.");
    } catch (err) {
      toast.error(err?.message || "Failed to export the security report.");
    } finally {
      if (isMountedRef.current) setIsExporting(false);
    }
  }, [exportFormat]);

  // ---------------------------------------------------------------
  // Derived / chart-ready data
  // ---------------------------------------------------------------
  const latestScore = summary?.latest_security_score;
  const score = latestScore?.score ?? 0;
  const grade = latestScore?.grade ?? "Unknown";

  const threatSeverityData = useMemo(() => {
    const bySeverity = threatStats?.by_severity ?? {};
    return SEVERITY_ORDER.map((level) => ({ severity: level, count: bySeverity[level] || 0 }));
  }, [threatStats]);

  const threatDailyData = useMemo(() => {
    const daily = threatStats?.daily_counts ?? {};
    return Object.entries(daily)
      .sort(([a], [b]) => (a > b ? 1 : -1))
      .map(([date, count]) => ({ date, count }));
  }, [threatStats]);

  const incidentStatusData = useMemo(() => {
    const byStatus = incidentSummary?.statistics?.by_status ?? {};
    return Object.entries(byStatus).map(([status, count]) => ({ status, count }));
  }, [incidentSummary]);

  const scoreTrendSeries = useMemo(() => {
    const series = scoreTrends?.series ?? [];
    return series.map((point) => ({
      timestamp: point.timestamp,
      label: formatTimestamp(point.timestamp),
      score: point.score ?? 0,
    }));
  }, [scoreTrends]);

  const priorityCounts = recommendationSummary?.summary?.priority_counts ?? {};
  const recentRecommendations = recommendationSummary?.recent_recommendations ?? [];
  const recentIncidents = incidentSummary?.recent_incidents ?? [];

  if (isLoading) {
    return (
      <Card title="Security Reports" icon={PiFileTextBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading security reports..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header / refresh / export */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <PiFileTextBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Security Reports
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-secondary,#64748b)]">
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
            <select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value)}
              className="rounded-md border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] focus:outline-none"
            >
              {EXPORT_FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleExport}
              disabled={isExporting}
              className="flex items-center gap-1.5 rounded-md bg-violet-600/90 px-3 py-1.5 font-medium text-white transition-colors hover:bg-violet-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PiDownloadSimpleBold className="h-3.5 w-3.5" />
              {isExporting ? "Exporting…" : "Export Report"}
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-rose-400">{error} — showing last known data.</p>}
      </Card>

      {/* Security Summary */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Security Score" icon={PiShieldWarningBold} className="lg:col-span-1">
          <div className="flex items-center gap-4">
            <ProgressRing
              value={score}
              size={96}
              color={GRADE_TO_RING_COLOR[grade] || "lavender"}
              label={grade}
            />
            <div className="flex flex-col gap-1.5">
              <StatusBadge status={grade} />
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                {summary?.critical_open_incidents ?? 0} critical open incident(s)
              </p>
            </div>
          </div>
        </Card>

        <Card title="Incidents (window)" icon={PiWarningOctagonBold} className="lg:col-span-1">
          <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {summary?.incidents_in_window ?? 0}
          </p>
          <p className="mb-3 text-xs text-[var(--color-text-secondary,#64748b)]">
            in the last {summary?.window_days ?? WINDOW_DAYS} day(s)
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
            {summary?.incident_totals?.total_incidents ?? 0} total incident(s) recorded
          </p>
        </Card>

        <Card title="Recommendations" icon={PiLightbulbBold} className="lg:col-span-1">
          <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {summary?.recommendation_totals?.total ?? 0}
          </p>
          <p className="mb-3 text-xs text-[var(--color-text-secondary,#64748b)]">
            active recommendation(s)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {SEVERITY_ORDER.map((level) => (
              <span
                key={level}
                className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                style={{
                  color: SEVERITY_COLOR[level],
                  backgroundColor: `${SEVERITY_COLOR[level]}22`,
                }}
              >
                {level}: {priorityCounts[level] || 0}
              </span>
            ))}
          </div>
        </Card>
      </div>

      {/* Threat Statistics */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Threat Statistics — By Severity" icon={PiShieldWarningBold}>
          <div className="h-52 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={threatSeverityData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" vertical={false} />
                <XAxis
                  dataKey="severity"
                  tick={{ fill: "#64748b", fontSize: 12 }}
                  axisLine={{ stroke: "var(--color-border,#232733)" }}
                  tickLine={false}
                />
                <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
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
                  {threatSeverityData.map((entry) => (
                    <Cell key={entry.severity} fill={SEVERITY_COLOR[entry.severity]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-[var(--color-text-secondary,#64748b)]">
            {threatStats?.total_threats ?? 0} threat-related incident(s) in the last{" "}
            {threatStats?.window_days ?? WINDOW_DAYS} day(s)
          </p>
        </Card>

        <Card title="Threat Statistics — Daily Trend" icon={PiChartLineUpBold}>
          {threatDailyData.length === 0 ? (
            <p className="py-10 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No threat activity recorded in this window.
            </p>
          ) : (
            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={threatDailyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" />
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                  <Tooltip
                    contentStyle={{
                      background: "var(--color-bg-elevated,#161922)",
                      border: "1px solid var(--color-border,#232733)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Line type="monotone" dataKey="count" stroke="#b4a7f5" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* Incident Summary */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Incident Status Breakdown" icon={PiWarningOctagonBold} className="lg:col-span-1">
          {incidentStatusData.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No incidents recorded yet.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {incidentStatusData.map((entry) => (
                <div
                  key={entry.status}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border,#232733)] px-3 py-2 text-xs"
                >
                  <StatusBadge status={entry.status} size="sm" />
                  <span className="font-medium text-[var(--color-text-primary,#f1f5f9)]">{entry.count}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent Incidents" icon={PiListChecksBold} className="lg:col-span-2">
          {recentIncidents.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No recent incidents.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {recentIncidents.map((incident) => (
                <div
                  key={incident.incident_id}
                  className="flex flex-col gap-1 rounded-lg border border-[var(--color-border,#232733)] p-3"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="flex items-start gap-2">
                      <StatusBadge status={incident.severity} size="sm" />
                      <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                        {formatLabel(incident.category)}
                      </p>
                    </div>
                    <span className="whitespace-nowrap text-xs text-[var(--color-text-secondary,#64748b)]">
                      {formatTimestamp(incident.timestamp)}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">{incident.description}</p>
                  <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary,#64748b)]">
                    <span>Source: {formatLabel(incident.source_module)}</span>
                    <span>•</span>
                    <StatusBadge status={incident.status} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Security Score Trends */}
      <Card title="Security Score Trends" icon={PiChartLineUpBold}>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <StatusBadge status={DIRECTION_STATUS[scoreTrends?.direction] || "warning"} />
          <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
            {formatLabel(scoreTrends?.direction) || "Stable"} — change of{" "}
            {typeof scoreTrends?.change === "number" ? scoreTrends.change.toFixed(1) : "0.0"} pts across{" "}
            {scoreTrends?.sample_count ?? 0} sample(s)
          </span>
        </div>
        {scoreTrendSeries.length === 0 ? (
          <p className="py-10 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
            No historical security score data available yet.
          </p>
        ) : (
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={scoreTrendSeries} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" />
                <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-bg-elevated,#161922)",
                    border: "1px solid var(--color-border,#232733)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Line type="monotone" dataKey="score" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* Recommendation Summary */}
      <Card title="Recommendation Summary" icon={PiLightbulbBold}>
        {recentRecommendations.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No active recommendations — current posture does not require action.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {recentRecommendations.map((rec) => (
              <div
                key={rec.recommendation_id}
                className="flex flex-col gap-1 rounded-lg border border-[var(--color-border,#232733)] p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <StatusBadge status={rec.priority} size="sm" />
                    <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">{rec.title}</p>
                  </div>
                  <span className="whitespace-nowrap text-xs text-[var(--color-text-secondary,#64748b)]">
                    {formatTimestamp(rec.timestamp)}
                  </span>
                </div>
                <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">{rec.explanation}</p>
                {rec.action && (
                  <p className="text-xs text-[var(--color-text-primary,#f1f5f9)]">
                    <span className="font-semibold text-violet-400">Action: </span>
                    {rec.action}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default SecurityReports;