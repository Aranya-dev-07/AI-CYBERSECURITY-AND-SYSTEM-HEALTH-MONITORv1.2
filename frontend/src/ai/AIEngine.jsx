import { useEffect, useState } from "react";
import {
  PiBrainBold,
  PiPulseBold,
  PiCircuitryBold,
  PiSparkleBold,
  PiClockClockwiseBold,
  PiCheckCircleBold,
  PiXCircleBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";
import { getAIResults } from "../services/api.js";

const POLL_INTERVAL_MS = 15000;
const RECENT_CYCLE_WINDOW_MS = 2 * 60 * 1000;

const MODULES = [
  { key: "anomaly_detection", label: "Anomaly Detection", dataKey: "anomalies" },
  { key: "health_score", label: "Health Score", dataKey: "health_score" },
  { key: "root_cause", label: "Root Cause Analysis", dataKey: "root_causes" },
  { key: "trend_analysis", label: "Trend Analysis", dataKey: "trends" },
  { key: "predictive_alerts", label: "Predictive Alerts", dataKey: "predictions" },
  { key: "recommendations", label: "Recommendations", dataKey: "recommendations" },
];

function moduleHasError(errors, moduleKey) {
  return (errors || []).some((message) =>
    typeof message === "string" ? message.startsWith(moduleKey) : false
  );
}

function deriveProcessingStatus(result, errors) {
  if (!result) return "idle";
  if (errors?.length) return "starting";

  const timestamp = result.timestamp ? new Date(result.timestamp).getTime() : null;
  if (timestamp && Date.now() - timestamp <= RECENT_CYCLE_WINDOW_MS) return "online";
  return "idle";
}

function formatRelativeTime(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";

  const diffSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  return date.toLocaleString();
}

/**
 * AIEngine — the Trinetra AI workspace overview. Displays overall
 * engine status, active subsystem status, the latest insight, and a
 * recent activity timeline. Pure orchestration/presentation — all
 * scoring, detection, and explanation logic lives in the backend
 * (ai/ai_engine.py and its subsystems).
 *
 * Props:
 *   result (object) — latest unified AI cycle result (AIWorkspace.jsx).
 *   errors (array)  — errors reported by the latest AI cycle, if any.
 */
function AIEngine({ result, errors = [] }) {
  const { status } = useSystemStatus();
  const [timeline, setTimeline] = useState([]);
  const [isTimelineLoading, setIsTimelineLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadTimeline() {
      try {
        const history = await getAIResults({ limit: 8 });
        if (isMounted) setTimeline(history || []);
      } catch {
        // Non-fatal: timeline simply stays empty/stale until the next poll.
      } finally {
        if (isMounted) setIsTimelineLoading(false);
      }
    }

    loadTimeline();
    const intervalId = setInterval(loadTimeline, POLL_INTERVAL_MS);
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const aiEngineStatus = status?.aiEngine ?? "offline";
  const processingStatus = deriveProcessingStatus(result, errors);

  const latestInsight =
    result?.recommendations?.[0]?.reasoning ||
    result?.health_details?.explanation ||
    "No AI insight available yet. Start a monitoring session to generate one.";

  return (
    <div className="flex flex-col gap-4">
      {/* Status row */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card title="AI Engine Status" icon={PiBrainBold}>
          <StatusBadge status={aiEngineStatus} />
        </Card>
        <Card title="Processing Status" icon={PiPulseBold}>
          <StatusBadge status={processingStatus} />
        </Card>
        <Card title="Active AI Modules" icon={PiCircuitryBold}>
          <ul className="flex flex-col gap-1.5">
            {MODULES.map(({ key, label }) => {
              const hasError = moduleHasError(errors, key);
              const isActive = Boolean(result) && !hasError;
              return (
                <li key={key} className="flex items-center justify-between text-xs">
                  <span className="text-[var(--color-text-secondary,#94a3b8)]">{label}</span>
                  {isActive ? (
                    <PiCheckCircleBold className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <PiXCircleBold className="h-4 w-4 text-rose-400" />
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      </section>

      {/* Latest insight */}
      <Card title="Latest AI Insight" icon={PiSparkleBold}>
        <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{latestInsight}</p>
      </Card>

      {/* Activity timeline */}
      <Card title="AI Activity Timeline" icon={PiClockClockwiseBold}>
        {isTimelineLoading ? (
          <div className="flex justify-center py-6">
            <Loader label="Loading activity..." />
          </div>
        ) : timeline.length ? (
          <ol className="flex flex-col divide-y divide-[var(--color-border,#232733)]">
            {timeline.map((entry) => (
              <li key={entry.id ?? entry.timestamp} className="flex items-center justify-between py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    Health {entry.health_status || "Unknown"}
                    {entry.health_score != null ? ` · ${entry.health_score}/100` : ""}
                  </p>
                  <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
                    {(entry.anomalies || []).length} anomaly(ies) ·{" "}
                    {(entry.recommendations || []).length} recommendation(s)
                  </p>
                </div>
                <span className="flex-shrink-0 text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatRelativeTime(entry.timestamp)}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No AI activity recorded yet.
          </p>
        )}
      </Card>
    </div>
  );
}

export default AIEngine;