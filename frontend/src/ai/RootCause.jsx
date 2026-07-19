import { PiMagnifyingGlassBold, PiGaugeBold, PiCubeBold, PiWrenchBold } from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatMetricLabel(metric) {
  if (!metric) return "—";
  return metric.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * RootCause — displays explainable AI root cause analyses produced by
 * the backend (ai/root_cause.py). One card per analyzed anomaly,
 * showing the affected metric, responsible process (if identified),
 * root cause category, severity, explanation, and suggested fix. No
 * analysis or classification logic lives here.
 *
 * Props:
 *   rootCauses (array) — list of RootCauseResult dicts.
 */
function RootCause({ rootCauses = [] }) {
  if (!rootCauses.length) {
    return (
      <Card title="Root Cause Analysis" icon={PiMagnifyingGlassBold}>
        <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
          No root cause analyses available. This appears when active anomalies are detected.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {rootCauses.map((entry) => (
        <Card
          key={entry.analysis_id}
          title={entry.root_cause_category || "Root Cause"}
          icon={PiMagnifyingGlassBold}
        >
          <div className="flex flex-col gap-4">
            {/* Metric / Process / Severity summary row */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="flex items-start gap-2">
                <PiGaugeBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-violet-400" />
                <div>
                  <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                    Responsible Metric
                  </p>
                  <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {formatMetricLabel(entry.affected_metric)}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <PiCubeBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-violet-400" />
                <div>
                  <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                    Responsible Process
                  </p>
                  <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {entry.responsible_process || "Not identified"}
                  </p>
                </div>
              </div>

              <div>
                <p className="mb-1 text-xs text-[var(--color-text-secondary,#64748b)]">Severity</p>
                <StatusBadge status={entry.severity || "Low"} />
              </div>
            </div>

            {/* Explanation */}
            {entry.explanation && (
              <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-bg,#0f1115)] px-3 py-2.5">
                <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{entry.explanation}</p>
              </div>
            )}

            {/* Suggested fix */}
            {entry.recommended_action && (
              <div className="flex items-start gap-2">
                <PiWrenchBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
                <div>
                  <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Suggested Fix</p>
                  <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {entry.recommended_action}
                  </p>
                </div>
              </div>
            )}

            <p className="text-right text-[11px] text-[var(--color-text-secondary,#64748b)]">
              {formatTimestamp(entry.timestamp)}
            </p>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default RootCause;