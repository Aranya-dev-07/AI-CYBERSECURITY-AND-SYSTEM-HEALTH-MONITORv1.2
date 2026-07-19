import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiClockCounterClockwiseBold,
  PiMagnifyingGlassBold,
  PiFunnelBold,
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
  { key: "title", label: "Report Name", sortable: true },
  { key: "report_type", label: "Report Type", sortable: true },
  { key: "created_at", label: "Generated Time", sortable: true },
  { key: "duration_seconds", label: "Monitoring Duration", sortable: true },
  { key: "summary", label: "AI Summary", sortable: false },
  { key: "health_status", label: "Overall Health", sortable: true },
  { key: "export_status", label: "Export Status", sortable: false },
];

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "—";
  const s = Number(seconds);
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  const hours = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  return `${hours}h ${mins}m`;
}

/**
 * normalizeReport — maps a backend report record (ReportSummary /
 * ReportDetail, per backend/api/schemas.py) to the flat fields this
 * table displays. Tolerant of multiple possible nested content key
 * names since the report payload shape is backend-owned
 * (monitoring/reports.py). Performs no report generation or
 * aggregation itself.
 */
function normalizeReport(raw) {
  const content = raw?.content || {};
  const source = { ...content, ...raw };

  return {
    id: raw.id,
    title: source.title || `Report #${raw.id}`,
    report_type: source.report_type || "General",
    created_at: source.created_at,
    duration_seconds: source.duration_seconds ?? source.duration ?? null,
    summary:
      source.ai_summary || source.summary || source.health_details?.explanation || null,
    health_status: source.health_status || source.overall_status || source.status || "Unknown",
    health_score: source.health_score ?? source.ai_health_score ?? null,
    export_status: source.export_status || source.exported ? "Exported" : "Not Exported",
    generated_by: source.generated_by,
  };
}

function compareValues(a, b, key) {
  const av = a[key];
  const bv = b[key];

  if (key === "created_at") {
    const at = av ? new Date(av).getTime() : -Infinity;
    const bt = bv ? new Date(bv).getTime() : -Infinity;
    return at - bt;
  }

  if (key === "duration_seconds") {
    const ad = av ?? -Infinity;
    const bd = bv ?? -Infinity;
    return ad - bd;
  }

  return String(av ?? "").localeCompare(String(bv ?? ""));
}

/**
 * ReportHistory — displays the full historical list of Lavender
 * Trinetra reports in a searchable, filterable, sortable, paginated
 * table. Fetched via GET /api/reports (backend/api/routes.py ->
 * monitoring/reports.py) through services/api.js. Purely
 * presentational: no report generation, aggregation, or scoring logic
 * lives here.
 *
 * Props:
 *   reports (array) — optional pre-fetched report records (from
 *                      Reports.jsx's getReports() call). Used as
 *                      initial render; refresh re-fetches independently.
 */
function ReportHistory({ reports: initialReports = [] }) {
  const [reports, setReports] = useState((initialReports || []).map(normalizeReport));
  const [isLoading, setIsLoading] = useState(!(initialReports && initialReports.length));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("All");
  const [healthFilter, setHealthFilter] = useState("All");
  const [sortKey, setSortKey] = useState("created_at");
  const [sortDirection, setSortDirection] = useState("desc");
  const [page, setPage] = useState(1);

  const isMountedRef = useRef(true);

  const fetchReports = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getReports({ limit: 100 });
      if (!isMountedRef.current) return;
      const list = Array.isArray(data) ? data : data?.reports || [];
      setReports(list.map(normalizeReport));
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load report history.");
      toast.error("Failed to refresh report history.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    if (!initialReports || !initialReports.length) {
      fetchReports();
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
  }, [search, typeFilter, healthFilter, sortKey, sortDirection]);

  const typeOptions = useMemo(() => {
    const types = new Set(reports.map((r) => r.report_type).filter(Boolean));
    return ["All", ...Array.from(types).sort()];
  }, [reports]);

  const healthOptions = useMemo(() => {
    const statuses = new Set(reports.map((r) => r.health_status).filter(Boolean));
    return ["All", ...Array.from(statuses).sort()];
  }, [reports]);

  const filteredReports = useMemo(() => {
    const query = search.trim().toLowerCase();
    return reports.filter((report) => {
      if (typeFilter !== "All" && report.report_type !== typeFilter) return false;
      if (healthFilter !== "All" && report.health_status !== healthFilter) return false;
      if (!query) return true;
      const searchable = [report.title, report.report_type, report.summary, report.generated_by]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return searchable.includes(query);
    });
  }, [reports, search, typeFilter, healthFilter]);

  const sortedReports = useMemo(() => {
    const sorted = [...filteredReports].sort((a, b) => compareValues(a, b, sortKey));
    return sortDirection === "asc" ? sorted : sorted.reverse();
  }, [filteredReports, sortKey, sortDirection]);

  const totalPages = Math.max(1, Math.ceil(sortedReports.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedReports = useMemo(
    () => sortedReports.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [sortedReports, currentPage]
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
      <Card title="Report History" icon={PiClockCounterClockwiseBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading report history..." />
        </div>
      </Card>
    );
  }

  return (
    <Card title="Report History" icon={PiClockCounterClockwiseBold}>
      <div className="flex flex-col gap-4">
        {/* Toolbar */}
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative w-full sm:max-w-xs">
              <PiMagnifyingGlassBold className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-secondary,#64748b)]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search reports..."
                className="w-full rounded-md border border-[var(--color-border,#232733)] bg-transparent py-1.5 pl-8 pr-3 text-sm text-[var(--color-text-primary,#f1f5f9)] placeholder:text-[var(--color-text-secondary,#64748b)] focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>

            <PiFunnelBold className="h-4 w-4 text-[var(--color-text-secondary,#64748b)]" />

            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {typeOptions.map((opt) => (
                <option key={opt} value={opt} className="bg-[var(--color-bg,#0f1115)]">
                  {opt === "All" ? "All Types" : opt}
                </option>
              ))}
            </select>

            <select
              value={healthFilter}
              onChange={(e) => setHealthFilter(e.target.value)}
              className="rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {healthOptions.map((opt) => (
                <option key={opt} value={opt} className="bg-[var(--color-bg,#0f1115)]">
                  {opt === "All" ? "All Health States" : opt}
                </option>
              ))}
            </select>
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
              onClick={() => fetchReports({ silent: true })}
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
        {sortedReports.length === 0 ? (
          <p className="py-6 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
            No reports match the current filters.
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
                  {pagedReports.map((report) => (
                    <tr key={report.id} className="border-b border-white/5 align-top">
                      <td className="py-2 pr-4 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                        {report.title}
                      </td>
                      <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                        {report.report_type}
                      </td>
                      <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                        {formatTimestamp(report.created_at)}
                      </td>
                      <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                        {formatDuration(report.duration_seconds)}
                      </td>
                      <td className="max-w-xs py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                        <span className="line-clamp-2">{report.summary || "—"}</span>
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex flex-col gap-1">
                          <StatusBadge status={report.health_status} />
                          {report.health_score != null && (
                            <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
                              {report.health_score}/100
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 pr-4">
                        <StatusBadge status={report.export_status} />
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
                {Math.min(currentPage * PAGE_SIZE, sortedReports.length)} of {sortedReports.length} reports
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

export default ReportHistory;