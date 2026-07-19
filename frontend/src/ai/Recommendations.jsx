import { useMemo } from "react";
import { PiLightbulbBold, PiWrenchBold, PiTagBold } from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

function priorityTier(priorityScore) {
  if (priorityScore == null) return { label: "Unranked", className: "text-[var(--color-text-secondary,#94a3b8)]" };
  if (priorityScore >= 90) return { label: "Critical Priority", className: "text-rose-400" };
  if (priorityScore >= 70) return { label: "High Priority", className: "text-amber-400" };
  if (priorityScore >= 50) return { label: "Medium Priority", className: "text-sky-400" };
  return { label: "Low Priority", className: "text-emerald-400" };
}

/**
 * Recommendations — displays prioritized, explainable AI
 * recommendations produced by the backend (ai/recommendations.py).
 * One card per recommendation, showing its title, priority, severity,
 * reasoning, and suggested action. No prioritization or generation
 * logic lives here — recommendations arrive already ranked.
 *
 * Props:
 *   recommendations (array) — list of Recommendation dicts.
 */
function Recommendations({ recommendations = [] }) {
  const sorted = useMemo(
    () => [...recommendations].sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0)),
    [recommendations]
  );

  if (!sorted.length) {
    return (
      <Card title="Recommendations" icon={PiLightbulbBold}>
        <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
          No recommendations at this time. Everything looks healthy.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {sorted.map((rec) => {
        const tier = priorityTier(rec.priority_score);

        return (
          <Card key={rec.recommendation_id} title={rec.title} icon={PiLightbulbBold}>
            <div className="flex flex-col gap-4">
              {/* Category / Priority / Severity row */}
              <div className="flex flex-wrap items-center gap-3">
                {rec.category && (
                  <span className="flex items-center gap-1 rounded-full border border-[var(--color-border,#232733)] px-2.5 py-1 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                    <PiTagBold className="h-3 w-3" />
                    {rec.category}
                  </span>
                )}
                <span className={`text-xs font-semibold ${tier.className}`}>
                  {tier.label}
                  {rec.priority_score != null ? ` (${rec.priority_score})` : ""}
                </span>
                <StatusBadge status={rec.severity || "Low"} />
              </div>

              {/* Reasoning */}
              {rec.reasoning && (
                <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-bg,#0f1115)] px-3 py-2.5">
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
                    Reason
                  </p>
                  <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{rec.reasoning}</p>
                </div>
              )}

              {/* Suggested action */}
              {rec.recommended_action && (
                <div className="flex items-start gap-2">
                  <PiWrenchBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
                  <div>
                    <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                      Suggested Action
                    </p>
                    <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {rec.recommended_action}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

export default Recommendations;