import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiListChecksBold,
  PiMagnifyingGlassBold,
  PiArrowsClockwiseBold,
  PiCaretUpBold,
  PiCaretDownBold,
  PiCaretLeftBold,
  PiCaretRightBold,
  PiClockBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";
import { getReports } from "../services/api.js";

const PAGE_SIZE = 10;

const COLUMNS = [
  { key: "run_id", label: "Run ID", sortable: true },
  { key: "start_time", label: "Start Time", sortable: true },
  { key: "end_time", label: "End Time", sortable: true },
  { key: "duration", label: "Duration", sortable: true },
  { key: "total_alerts", label: "Total Alerts", sortable: true },
  { key: "health_score", label: "AI Health Score", sortable: true },
  { key: "status", label: "Overall Status", sortable: false },
];

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatDuration(startTime, endTime, explicitSeconds) {
  if (explicitSeconds != null && !Number.isNaN(Number(explicitSeconds))) {
    const seconds = Number(explicitSeconds);
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  }
  if (!startTime || !endTime) return "—";
  const start = new Date(startTime).getTime();
  const end = new Date(endTime).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  return formatDuration(null, null, (end - start) / 1000);
}

/**
 * normalizeRun — maps a backend report record (ReportSummary /
 * ReportDetail, per backend/api/schemas.py, potentially with a nested
 * `content` payload from monitoring/reports.py) to the flat fields
 * this table displays. Tolerant of multiple possible key names since
 * report content shape is backend-owned; performs no calculation
 * beyond simple duration derivation when only start/end are given.
 */
function normalizeRun(raw) {
  const content = raw?.content || {};
  const source = { ...content, ...raw };

  const runId = source.run_id ?? source.id ?? source.report_id ?? "—";
  const startTime = source.start_time ?? source.started_at ?? source.created_at ?? null;
  const endTime = source.end_time ?? source.ended_at ?? source.completed_at ?? null;
  const totalAlerts =
    source.total_alerts ?? source.alert_count ?? source.alerts_count ?? source.alerts ?? null;
  const healthScore = source.health_score ?? source.ai_health_score ?? source.score ?? null;
  const status = source.status ?? source.overall_status ?? source.report_type ?? "Unknown";
  const explicitDuration = source.duration_seconds ?? source.duration ?? null;

  return {
    id: raw.id,
    run_id: runId,
    start_time: startTime,
    end_time: endTime,
    duration_seconds:
      typeof explicitDuration === "number" ? explicitDuration : null,
    duration_display:
      typeof explicitDuration === "string"
        ? explicitDuration
        : formatDuration(startTime, endTime, explicitDuration),
    total_alerts: totalAlerts,
    health_score: healthScore,
    status,
    title: raw.title,
  };
}

function compareValues(a, b, key) {
  const av = a[key];
  const bv = b[key];

  if (key === "start_time" || key === "end_time") {
    const at = av ? new Date(av).getTime() : -Infinity;
    const bt = bv ? new Date(bv).getTime() : -Infinity;
    return at - bt;
  }

  if (key === "duration") {
    const ad = a.duration_seconds ?? -Infinity;
    const bd = b.duration_seconds ?? -Infinity;
    return ad - bd;
  }

  if (key === "total_alerts" || key === "health_score") {
    const an = av == null ? -Infinity : Number(av);
    const bn = bv == null ? -Infinity : Number(bv);
    return an - bn;
  }

  return String(av ?? "").localeCompare(String(bv ?? ""));
}

/**
 * TestRuns — displays monitoring session/test run history in a
 * searchable, sortable, paginated table. Fetched via GET /api/reports
 * (backend/api/routes.py -> monitoring/reports.py) through
 * services/api.js. Purely presentational: no report generation,
 * aggregation, or scoring logic lives here.
 *
 * Props:
 *   reports (array) — optional pre-fetched report records (from
 *                      Reports.jsx's getReports() call). Used as
 *                      initial render; refresh re-fetches independently.
 *   stats (object)  — optional dashboard statistics (unused for
 *                      rendering here, accepted for prop compatibility
 *                      with Reports.jsx).
 */
function TestRuns({ reports: initialReports = [], stats: _stats = null }) {
  const [runs, setRuns] = useState((initialReports || []).map(normalizeRun));
  const [isLoading, setIsLoading] = useState(!(initialReports && initialReports.length));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("start_time");
  const [sortDirection, setSortDirection] = useState("desc");
  const [page, setPage] = useState(1);

  const isMountedRef = useRef(true);

  const fetchRuns = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getReports({ limit: 100 });
      if (!isMountedRef.current) return;
      const list = Array.isArray(data) ? data : data?.reports || [];
      setRuns(list.map(normalizeRun));
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load test runs.");
      toast.error("Failed to refresh test runs.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    if (!initialReports || !initialReports.length) {
      fetchRuns();
    } else {
      setLastFetched(new Date());
    }
    return () => {
      isMountedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setPage(1);
  }, [search, sortKey, sortDirection]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return runs;
    return runs.filter((run) => {
      const searchable = [run.run_id, run.status, run.title]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return searchable.includes(query);
    });
  }, [runs, search]);

  const sortedRuns = useMemo(() => {
    const sorted = [...filteredRuns].sort((a, b) => compareValues(a, b, sortKey));
    return sortDirection === "asc" ? sorted : sorted.reverse();
  }, [filteredRuns, sortKey, sortDirection]);

  const totalPages = Math.max(1, Math.ceil(sortedRuns.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedRuns = useMemo(
    () => sortedRuns.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [sortedRuns, currentPage]
  );

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  };

  if (isLoading) {
    return (
      <Card title="Test Runs" icon={PiListChecksBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading test runs..." />
        </div>
      </Card>
    );
  }

  return (
    <Card title="Test Runs" icon={PiListChecksBold}>
      <div className="flex flex-col gap-4">
        {/* Toolbar */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-xs">
            <PiMagnifyingGlassBold className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-secondary,#64748b)]" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by run ID or status..."
              className="w-full rounded-md border border-[var(--color-border,#232733)] bg-transparent py-1.5 pl-8 pr-3 text-sm text-[var(--color-text-primary,#f1f5f9)] placeholder:text-[var(--color-text-secondary,#64748b)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
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
              onClick={() => fetchRuns({ silent: true })}
              className="flex items-center gap-1.5 rounded-md border border-[var(--color-border,#232733)] px-3 py-1.5 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              <PiArrowsClockwiseBold className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <p className="text-xs text-rose-400">{error} — showing last known data.</p>
        )}

        {/* Table */}
        {sortedRuns.length === 0 ? (
          <p className="py-6 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
            No test runs found.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-[var(--color-border,#232733)]">
                    {COLUMNS.map((col) => (
                      <th
                        key={col.key}
                        className="py-2 pr-4 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]"
                      >
                        {col.sortable ? (
                          <button
                            type="button"
                            onClick={() => handleSort(col.key)}
                            className="flex items-center gap-1 transition-colors hover:text-[var(--color-text-primary,#f1f5f9)]"
                          >
                            {col.label}
                            {sortKey === col.key &&
                              (sortDirection === "asc" ? (
                                <PiCaretUpBold className="h-3 w-3" />
                              ) : (
                                <PiCaretDownBold className="h-3 w-3" />
                              ))}
                          </button>
                        ) : (
                          col.label
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedRuns.map((run) => (
                    <tr key={run.id ?? run.run_id} className="border-b border-white/5">
                      <td className="py-2 pr-4 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                        {run.run_id}
                      </td>
                      <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                        {formatTimestamp(run.start_time)}
                      </td>
                      <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                        {formatTimestamp(run.end_time)}
                      </td>
                      <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                        {run.duration_display}
                      </td>
                      <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                        {run.total_alerts ?? "—"}
                      </td>
                      <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                        {run.health_score != null ? `${run.health_score}/100` : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <StatusBadge status={run.status || "Unknown"} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
              <span>
                Showing {(currentPage - 1) * PAGE_SIZE + 1}–
                {Math.min(currentPage * PAGE_SIZE, sortedRuns.length)} of {sortedRuns.length} runs
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  className="flex items-center gap-1 rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <PiCaretLeftBold className="h-3.5 w-3.5" />
                  Prev
                </button>
                <span className="px-1 text-[var(--color-text-primary,#f1f5f9)]">
                  {currentPage} / {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                  className="flex items-center gap-1 rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                  <PiCaretRightBold className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

export default TestRuns;