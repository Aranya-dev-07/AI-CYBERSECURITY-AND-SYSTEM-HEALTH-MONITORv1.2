import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiClockCounterClockwiseBold,
  PiListMagnifyingGlassBold,
  PiChartPieSliceBold,
  PiChartLineUpBold,
  PiFunnelBold,
  PiMagnifyingGlassBold,
  PiArrowsClockwiseBold,
  PiClockBold,
  PiXBold,
} from "react-icons/pi";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import {
  getIncidents,
  getIncidentStatistics,
  getIncidentTimeline,
} from "../services/api.js";

const REFRESH_INTERVAL_MS = 20000;
const WINDOW_DAYS = 30;
const LIST_LIMIT = 300;

const SEVERITY_OPTIONS = ["Low", "Medium", "High", "Critical"];
const STATUS_OPTIONS = ["Open", "In Progress", "Resolved"];

const SEVERITY_COLOR = {
  Low: "#a3c266",
  Medium: "#e879c9",
  High: "#f87171",
  Critical: "#f87171",
};

const STATUS_COLOR = {
  Open: "#f87171",
  "In Progress": "#e879c9",
  Resolved: "#a3c266",
};

const AXIS_COLOR = "#64748b";
const GRID_COLOR = "#232733";

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

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-3 py-2 text-xs shadow-lg">
      {label && <p className="mb-1 font-medium text-[var(--color-text-secondary,#94a3b8)]">{label}</p>}
      {payload.map((entry) => (
        <p key={entry.dataKey || entry.name} style={{ color: entry.color || entry.payload?.fill }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

function EmptyState({ message = "No data available yet." }) {
  return (
    <div className="flex h-[200px] items-center justify-center text-sm text-[var(--color-text-secondary,#64748b)]">
      {message}
    </div>
  );
}

/**
 * IncidentHistory — historical cybersecurity incident workspace:
 * chronological timeline, full incident details, severity
 * distribution, status breakdown, historical trend charting, and
 * client-side search/filter over already-fetched incidents. All data
 * is sourced exclusively from incident_logger.py and
 * security_history.py via services/api.js - this component
 * implements no incident detection, scoring, or persistence logic of
 * its own; filtering/searching happens only over data the backend
 * already returned.
 */
function IncidentHistory() {
  const [incidents, setIncidents] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [timeline, setTimeline] = useState(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedIncident, setSelectedIncident] = useState(null);

  const fetchAll = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const results = await Promise.allSettled([
        getIncidents({ limit: LIST_LIMIT }),
        getIncidentStatistics(),
        getIncidentTimeline({ windowDays: WINDOW_DAYS, limit: LIST_LIMIT }),
      ]);
      if (!isMountedRef.current) return;

      const [incidentsRes, statsRes, timelineRes] = results;
      if (incidentsRes.status === "fulfilled") setIncidents(incidentsRes.value || []);
      if (statsRes.status === "fulfilled") setStatistics(statsRes.value);
      if (timelineRes.status === "fulfilled") setTimeline(timelineRes.value);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some incident history data could not be loaded.");
        if (!silent) toast.error("Some incident history data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load incident history.");
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

  // ---------------------------------------------------------------
  // Search / filter (client-side, over already-fetched incidents)
  // ---------------------------------------------------------------
  const filteredIncidents = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return incidents.filter((incident) => {
      if (severityFilter !== "all" && incident.severity !== severityFilter) return false;
      if (statusFilter !== "all" && incident.status !== statusFilter) return false;
      if (!term) return true;
      const haystack = [
        incident.description,
        incident.category,
        incident.source_module,
        incident.incident_id,
        incident.resolution_notes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [incidents, searchTerm, severityFilter, statusFilter]);

  const hasActiveFilters = searchTerm.trim() !== "" || severityFilter !== "all" || statusFilter !== "all";

  const clearFilters = useCallback(() => {
    setSearchTerm("");
    setSeverityFilter("all");
    setStatusFilter("all");
  }, []);

  // ---------------------------------------------------------------
  // Chart-ready derived data
  // ---------------------------------------------------------------
  const severityDistribution = useMemo(() => {
    const bySeverity = statistics?.by_severity ?? {};
    return SEVERITY_OPTIONS.map((level) => ({ name: level, value: bySeverity[level] || 0 })).filter(
      (entry) => entry.value > 0
    );
  }, [statistics]);

  const statusDistribution = useMemo(() => {
    const byStatus = statistics?.by_status ?? {};
    return STATUS_OPTIONS.map((status) => ({ name: status, value: byStatus[status] || 0 }));
  }, [statistics]);

  const historicalTrend = useMemo(() => {
    const events = timeline?.timeline ?? [];
    const dailyCounts = {};
    events.forEach((event) => {
      if (!event.timestamp) return;
      const day = event.timestamp.slice(0, 10);
      dailyCounts[day] = (dailyCounts[day] || 0) + 1;
    });
    return Object.entries(dailyCounts)
      .sort(([a], [b]) => (a > b ? 1 : -1))
      .map(([date, count]) => ({ date, count }));
  }, [timeline]);

  const timelineEvents = useMemo(() => {
    const events = timeline?.timeline ?? filteredIncidents;
    return [...events].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));
  }, [timeline, filteredIncidents]);

  if (isLoading) {
    return (
      <Card title="Incident History" icon={PiClockCounterClockwiseBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading incident history..." />
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
            <PiClockCounterClockwiseBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Incident History
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

      {/* Severity Distribution + Incident Status */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Severity Distribution" icon={PiChartPieSliceBold}>
          {severityDistribution.length === 0 ? (
            <EmptyState message="No incidents recorded yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={severityDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {severityDistribution.map((entry) => (
                    <Cell key={entry.name} fill={SEVERITY_COLOR[entry.name] || "#8b5cf6"} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Incident Status" icon={PiChartPieSliceBold}>
          {statusDistribution.every((s) => s.value === 0) ? (
            <EmptyState message="No incidents recorded yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={statusDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {statusDistribution.map((entry) => (
                    <Cell key={entry.name} fill={STATUS_COLOR[entry.name] || "#94a3b8"} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Historical Trends */}
      <Card title="Historical Trends" icon={PiChartLineUpBold}>
        {historicalTrend.length === 0 ? (
          <EmptyState message="No historical incident activity in the selected window." />
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={historicalTrend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke={AXIS_COLOR} fontSize={10} tickLine={false} />
              <YAxis allowDecimals={false} stroke={AXIS_COLOR} fontSize={11} tickLine={false} width={28} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="count" stroke="#b4a7f5" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
        <p className="mt-2 text-xs text-[var(--color-text-secondary,#64748b)]">
          {timeline?.event_count ?? 0} event(s) over the last {timeline?.window_days ?? WINDOW_DAYS} day(s)
        </p>
      </Card>

      {/* Search and Filter */}
      <Card title="Search & Filter" icon={PiFunnelBold}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <PiMagnifyingGlassBold className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-secondary,#64748b)]" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by description, category, or source…"
              className="w-full rounded-md border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] py-2 pl-9 pr-3 text-sm text-[var(--color-text-primary,#f1f5f9)] placeholder:text-[var(--color-text-secondary,#64748b)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-md border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-3 py-2 text-sm text-[var(--color-text-secondary,#94a3b8)] focus:outline-none focus:ring-1 focus:ring-violet-500"
          >
            <option value="all">All Severities</option>
            {SEVERITY_OPTIONS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-3 py-2 text-sm text-[var(--color-text-secondary,#94a3b8)] focus:outline-none focus:ring-1 focus:ring-violet-500"
          >
            <option value="all">All Statuses</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="flex items-center gap-1.5 rounded-md border border-[var(--color-border,#232733)] px-3 py-2 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              <PiXBold className="h-3.5 w-3.5" />
              Clear
            </button>
          )}

          <span className="ml-auto text-xs text-[var(--color-text-secondary,#64748b)]">
            {filteredIncidents.length} of {incidents.length} incident(s)
          </span>
        </div>
      </Card>

      {/* Incident Details table */}
      <Card title="Incident Details" icon={PiListMagnifyingGlassBold}>
        {filteredIncidents.length === 0 ? (
          <EmptyState message="No incidents match the current filters." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border,#232733)] text-xs uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
                  <th className="px-3 py-2 font-medium">Timestamp</th>
                  <th className="px-3 py-2 font-medium">Severity</th>
                  <th className="px-3 py-2 font-medium">Category</th>
                  <th className="px-3 py-2 font-medium">Source</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {filteredIncidents.map((incident) => (
                  <tr
                    key={incident.incident_id}
                    onClick={() => setSelectedIncident(incident)}
                    className="cursor-pointer border-b border-[var(--color-border,#232733)]/60 transition-colors hover:bg-white/5"
                  >
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      {formatTimestamp(incident.timestamp)}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={incident.severity} size="sm" />
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--color-text-primary,#f1f5f9)]">
                      {formatLabel(incident.category)}
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      {formatLabel(incident.source_module)}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={incident.status} size="sm" />
                    </td>
                    <td className="max-w-[320px] truncate px-3 py-2 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      {incident.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Incident Timeline */}
      <Card title="Incident Timeline" icon={PiClockCounterClockwiseBold}>
        {timelineEvents.length === 0 ? (
          <EmptyState message="No timeline events in the selected window." />
        ) : (
          <div className="flex max-h-[420px] flex-col gap-3 overflow-y-auto pr-1">
            {timelineEvents.map((event, index) => (
              <div key={event.incident_id || index} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span
                    className="mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: SEVERITY_COLOR[event.severity] || "#94a3b8" }}
                  />
                  {index < timelineEvents.length - 1 && (
                    <span className="mt-1 w-px flex-1 bg-[var(--color-border,#232733)]" />
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedIncident(event)}
                  className="flex-1 pb-3 text-left"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={event.severity} size="sm" />
                    <span className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {formatLabel(event.category)}
                    </span>
                    <StatusBadge status={event.status} size="sm" />
                    <span className="ml-auto text-xs text-[var(--color-text-secondary,#64748b)]">
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                    {event.description}
                  </p>
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Incident Details drawer/panel */}
      {selectedIncident && (
        <Card
          title="Incident Detail"
          icon={PiListMagnifyingGlassBold}
          action={
            <button
              type="button"
              onClick={() => setSelectedIncident(null)}
              className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-text-secondary,#64748b)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
              aria-label="Close incident detail"
            >
              <PiXBold className="h-3.5 w-3.5" />
            </button>
          }
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <DetailRow label="Incident ID" value={selectedIncident.incident_id} mono />
            <DetailRow label="Timestamp" value={formatTimestamp(selectedIncident.timestamp)} />
            <DetailRow
              label="Severity"
              value={<StatusBadge status={selectedIncident.severity} size="sm" />}
            />
            <DetailRow label="Status" value={<StatusBadge status={selectedIncident.status} size="sm" />} />
            <DetailRow label="Category" value={formatLabel(selectedIncident.category)} />
            <DetailRow label="Source Module" value={formatLabel(selectedIncident.source_module)} />
          </div>
          <div className="mt-3 flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              Description
            </span>
            <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{selectedIncident.description}</p>
          </div>
          {selectedIncident.resolution_notes && (
            <div className="mt-3 flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
                Resolution Notes
              </span>
              <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
                {selectedIncident.resolution_notes}
              </p>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function DetailRow({ label, value, mono = false }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
        {label}
      </span>
      <span
        className={`text-sm text-[var(--color-text-primary,#f1f5f9)] ${mono ? "font-mono text-xs" : ""}`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

export default IncidentHistory;