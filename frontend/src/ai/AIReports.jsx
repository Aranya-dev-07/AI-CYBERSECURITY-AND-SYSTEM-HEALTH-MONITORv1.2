import { useMemo, useState } from "react";
import {
  PiFileTextBold,
  PiHeartbeatBold,
  PiWarningCircleBold,
  PiTrendUpBold,
  PiChartLineBold,
  PiLightbulbBold,
  PiDownloadSimpleBold,
  PiFunnelBold,
} from "react-icons/pi";
import toast from "react-hot-toast";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const SECTIONS = [
  { key: "health", label: "AI Health History", icon: PiHeartbeatBold },
  { key: "anomalies", label: "Anomaly History", icon: PiWarningCircleBold },
  { key: "trends", label: "Trend Reports", icon: PiTrendUpBold },
  { key: "predictive", label: "Predictive Reports", icon: PiChartLineBold },
  { key: "recommendations", label: "Recommendation History", icon: PiLightbulbBold },
];

const SEVERITY_OPTIONS = ["All", "Critical", "High", "Medium", "Low"];

const DATE_RANGE_OPTIONS = [
  { key: "24h", label: "Last 24 Hours", ms: 24 * 60 * 60 * 1000 },
  { key: "7d", label: "Last 7 Days", ms: 7 * 24 * 60 * 60 * 1000 },
  { key: "30d", label: "Last 30 Days", ms: 30 * 24 * 60 * 60 * 1000 },
  { key: "all", label: "All Time", ms: null },
];

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function withinRange(timestamp, rangeMs) {
  if (rangeMs == null) return true;
  if (!timestamp) return false;
  const time = new Date(timestamp).getTime();
  if (Number.isNaN(time)) return false;
  return Date.now() - time <= rangeMs;
}

function matchesSeverity(item, severityFilter) {
  if (severityFilter === "All") return true;
  const severity = item.severity || item.risk_level;
  return severity === severityFilter;
}

/**
 * AIReports — displays historical AI results fetched by AIWorkspace
 * (GET /api/ai/results, etc.) across health score, anomalies, trends,
 * predictions, and recommendations. Purely presentational: applies
 * client-side filtering (date range, severity, search) over the
 * result history already supplied via props and offers export
 * placeholders. Generates no report content itself.
 *
 * Props:
 *   results (array) — AI result history, most recent first. Each item
 *                      is expected to loosely follow the shape produced
 *                      by ai/ai_engine.py: { timestamp, health_score,
 *                      health_status, anomalies, trends, predictions,
 *                      recommendations, ... }.
 */
function AIReports({ results = [] }) {
  const [activeSection, setActiveSection] = useState("health");
  const [dateRange, setDateRange] = useState("7d");
  const [severityFilter, setSeverityFilter] = useState("All");
  const [search, setSearch] = useState("");

  const rangeMs = DATE_RANGE_OPTIONS.find((r) => r.key === dateRange)?.ms ?? null;

  const flattened = useMemo(() => {
    const health = [];
    const anomalies = [];
    const trends = [];
    const predictive = [];
    const recommendations = [];

    (results || []).forEach((result) => {
      const timestamp = result.timestamp;

      if (result.health_score != null || result.health_status) {
        health.push({
          timestamp,
          score: result.health_score,
          status: result.health_status,
          explanation: result.health_details?.explanation,
        });
      }

      (result.anomalies || []).forEach((a) =>
        anomalies.push({ ...a, timestamp: a.timestamp || timestamp })
      );

      (result.trends || []).forEach((t) =>
        trends.push({ ...t, timestamp: t.timestamp || timestamp })
      );

      (result.predictions || []).forEach((p) =>
        predictive.push({ ...p, timestamp: p.timestamp || p.generated_at || timestamp })
      );

      (result.recommendations || []).forEach((r) =>
        recommendations.push({ ...r, timestamp: r.timestamp || timestamp })
      );
    });

    return { health, anomalies, trends, predictive, recommendations };
  }, [results]);

  const filteredData = useMemo(() => {
    const rows = flattened[activeSection === "predictive" ? "predictive" : activeSection] || [];
    const query = search.trim().toLowerCase();

    return rows.filter((item) => {
      if (!withinRange(item.timestamp, rangeMs)) return false;
      if (!matchesSeverity(item, severityFilter)) return false;
      if (!query) return true;

      const searchable = [
        item.status,
        item.explanation,
        item.metric,
        item.affected_metric,
        item.predicted_event,
        item.predicted_issue,
        item.reasoning,
        item.recommended_action,
        item.title,
        item.category,
        item.severity,
        item.risk_level,
        item.direction,
        ...(item.affected_metrics || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return searchable.includes(query);
    });
  }, [flattened, activeSection, rangeMs, severityFilter, search]);

  const handleExport = (format) => {
    toast(`Export to ${format} is not yet available.`, { icon: "🚧" });
  };

  const renderRow = (item, index) => {
    switch (activeSection) {
      case "health":
        return (
          <tr key={index} className="border-b border-white/5">
            <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(item.timestamp)}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {item.score != null ? `${item.score}/100` : "—"}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.status || "Unknown"} />
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.explanation || "—"}
            </td>
          </tr>
        );
      case "anomalies":
        return (
          <tr key={item.anomaly_id || index} className="border-b border-white/5">
            <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(item.timestamp)}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.severity || "Unknown"} />
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {(item.affected_metrics || []).join(", ") || "—"}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.confidence != null ? `${(item.confidence <= 1 ? item.confidence * 100 : item.confidence).toFixed(1)}%` : "—"}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.top_process || "—"}
            </td>
          </tr>
        );
      case "trends":
        return (
          <tr key={item.trend_id || index} className="border-b border-white/5">
            <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(item.timestamp)}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {item.metric || "—"}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.direction || "Stable"} />
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.severity || "Low"} />
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.explanation || "—"}
            </td>
          </tr>
        );
      case "predictive":
        return (
          <tr key={item.prediction_id || item.id || index} className="border-b border-white/5">
            <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(item.timestamp)}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {item.predicted_event || item.predicted_issue || "—"}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.risk_level || item.severity || "Unknown"} />
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.eta_minutes != null ? `${Math.round(item.eta_minutes)} min` : "—"}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.recommended_action || "—"}
            </td>
          </tr>
        );
      case "recommendations":
        return (
          <tr key={item.recommendation_id || index} className="border-b border-white/5">
            <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(item.timestamp)}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={item.severity || "Unknown"} />
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {item.title || "—"}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.category || "—"}
            </td>
            <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
              {item.priority_score ?? "—"}
            </td>
          </tr>
        );
      default:
        return null;
    }
  };

  const columnHeaders = {
    health: ["Timestamp", "Score", "Status", "Explanation"],
    anomalies: ["Timestamp", "Severity", "Affected Metrics", "Confidence", "Top Process"],
    trends: ["Timestamp", "Metric", "Direction", "Severity", "Explanation"],
    predictive: ["Timestamp", "Predicted Event", "Risk Level", "ETA", "Recommended Action"],
    recommendations: ["Timestamp", "Severity", "Recommendation", "Category", "Priority Score"],
  };

  return (
    <div className="flex flex-col gap-4">
      <Card title="AI Reports" icon={PiFileTextBold}>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Historical AI analysis results across health scoring, anomaly detection, trend
          analysis, predictive alerts, and recommendations.
        </p>
      </Card>

      {/* Section tabs */}
      <div className="flex flex-wrap gap-2 border-b border-[var(--color-border,#232733)] pb-2">
        {SECTIONS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveSection(key)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              activeSection === key
                ? "bg-violet-600/15 text-violet-300"
                : "text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Filters + export */}
      <Card>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <PiFunnelBold className="h-4 w-4 text-[var(--color-text-secondary,#64748b)]" />

            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {DATE_RANGE_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key} className="bg-[var(--color-bg,#0f1115)]">
                  {opt.label}
                </option>
              ))}
            </select>

            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            >
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt} value={opt} className="bg-[var(--color-bg,#0f1115)]">
                  {opt === "All" ? "All Severities" : opt}
                </option>
              ))}
            </select>

            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)] placeholder:text-[var(--color-text-secondary,#64748b)] focus:outline-none focus:ring-1 focus:ring-violet-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleExport("CSV")}
              className="flex items-center gap-1.5 rounded-md border border-[var(--color-border,#232733)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              <PiDownloadSimpleBold className="h-3.5 w-3.5" />
              Export CSV
            </button>
            <button
              type="button"
              onClick={() => handleExport("PDF")}
              className="flex items-center gap-1.5 rounded-md border border-[var(--color-border,#232733)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              <PiDownloadSimpleBold className="h-3.5 w-3.5" />
              Export PDF
            </button>
          </div>
        </div>
      </Card>

      {/* Table */}
      <Card>
        {filteredData.length === 0 ? (
          <p className="py-6 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
            No records match the current filters.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--color-border,#232733)]">
                  {columnHeaders[activeSection].map((header) => (
                    <th
                      key={header}
                      className="py-2 pr-4 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>{filteredData.map((item, index) => renderRow(item, index))}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

export default AIReports;