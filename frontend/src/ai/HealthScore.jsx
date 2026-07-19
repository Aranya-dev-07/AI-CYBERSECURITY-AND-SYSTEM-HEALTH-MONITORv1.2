import { PiHeartbeatBold, PiClockBold } from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import ProgressRing from "../components/ProgressRing.jsx";

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function factorBarColor(subScore) {
  if (subScore == null) return "bg-[var(--color-border,#232733)]";
  if (subScore >= 75) return "bg-emerald-400";
  if (subScore >= 50) return "bg-amber-400";
  return "bg-rose-400";
}

/**
 * HealthScore — displays the explainable AI health score, its status,
 * per-factor breakdown, and the natural-language explanation produced
 * by the backend (ai/health_score.py). Performs no scoring or
 * calculation itself — purely renders what the API returns.
 *
 * Props:
 *   score (number)   — composite health score (0-100).
 *   status (string)  — Excellent | Good | Fair | Poor | Critical.
 *   details (object) — full HealthScoreResult dict: timestamp,
 *                       contributing_factors, explanation, etc.
 */
function HealthScore({ score, status, details }) {
  const resolvedScore = details?.score ?? score;
  const resolvedStatus = details?.status ?? status;
  const factors = details?.contributing_factors || [];
  const explanation = details?.explanation;

  if (resolvedScore == null && !factors.length) {
    return (
      <Card title="Health Score" icon={PiHeartbeatBold}>
        <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
          No health score available yet. Start a monitoring session to generate one.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Hero: score ring + status + last updated */}
      <Card title="AI Health Score" icon={PiHeartbeatBold}>
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-5">
            <ProgressRing value={resolvedScore ?? 0} />
            <div>
              <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                {resolvedScore != null ? `${resolvedScore}` : "—"}
                <span className="text-base font-normal text-[var(--color-text-secondary,#64748b)]">
                  /100
                </span>
              </p>
              <div className="mt-1">
                <StatusBadge status={resolvedStatus || "Unknown"} />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
            <PiClockBold className="h-3.5 w-3.5" />
            Last updated {formatTimestamp(details?.timestamp)}
          </div>
        </div>
      </Card>

      {/* Explanation */}
      {explanation && (
        <Card title="Explanation">
          <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{explanation}</p>
        </Card>
      )}

      {/* Score breakdown */}
      <Card title="Score Breakdown">
        {factors.length ? (
          <div className="flex flex-col gap-4">
            {factors.map((factor) => (
              <div key={factor.name}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="font-medium capitalize text-[var(--color-text-primary,#f1f5f9)]">
                    {factor.name}
                  </span>
                  <span className="text-[var(--color-text-secondary,#94a3b8)]">
                    {factor.sub_score != null ? `${factor.sub_score.toFixed?.(1) ?? factor.sub_score}/100` : "—"}
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-bg,#0f1115)]">
                  <div
                    className={`h-full rounded-full ${factorBarColor(factor.sub_score)}`}
                    style={{ width: `${Math.min(100, Math.max(0, factor.sub_score ?? 0))}%` }}
                  />
                </div>
                {factor.detail && (
                  <p className="mt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                    {factor.detail}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No contributing factor breakdown available.
          </p>
        )}
      </Card>
    </div>
  );
}

export default HealthScore;