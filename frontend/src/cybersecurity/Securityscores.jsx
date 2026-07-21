import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiShieldStarBold,
  PiGaugeBold,
  PiChartBarBold,
  PiFingerprintBold,
  PiPathBold,
  PiListChecksBold,
  PiWarningOctagonBold,
  PiClockBold,
  PiArrowsClockwiseBold,
} from "react-icons/pi";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from "recharts";

import Card from "../components/Card.jsx";
import ProgressRing from "../components/ProgressRing.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import {
  getSecurityScore,
  getThreatClassificationSummary,
  getAttackPatternSummary,
  getSecurityRecommendations,
} from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;
const TOP_RECOMMENDATIONS_LIMIT = 6;

const PRIORITY_ORDER = ["Low", "Medium", "High", "Critical"];

const PRIORITY_COLOR = {
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

const CLASSIFICATION_COLORS = ["#b4a7f5", "#a3c266", "#e879c9", "#f87171", "#7c8cf8", "#94a3b8"];

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function priorityRank(priority) {
  const index = PRIORITY_ORDER.indexOf(priority);
  return index === -1 ? 0 : index;
}

/**
 * SecurityScore — the Explainable AI Security Score workspace.
 * Summarizes the overall 0-100 security score, its explainable
 * breakdown, threat classification and attack pattern summaries, and
 * the top prioritized security recommendations - all sourced from
 * security_score.py, threat_classifier.py, attack_patterns.py and
 * security_recommendations.py via services/api.js. Purely
 * presentational: it renders and charts scores/priorities the backend
 * already computed and assigns none of its own.
 */
function SecurityScore() {
  const [scoreResult, setScoreResult] = useState(null);
  const [classificationSummary, setClassificationSummary] = useState(null);
  const [patternSummary, setPatternSummary] = useState(null);
  const [recommendations, setRecommendations] = useState([]);

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
        getSecurityScore(),
        getThreatClassificationSummary(),
        getAttackPatternSummary(),
        getSecurityRecommendations({ limit: TOP_RECOMMENDATIONS_LIMIT }),
      ]);
      if (!isMountedRef.current) return;

      const [scoreRes, classificationRes, patternRes, recommendationRes] = results;
      if (scoreRes.status === "fulfilled") setScoreResult(scoreRes.value);
      if (classificationRes.status === "fulfilled") setClassificationSummary(classificationRes.value);
      if (patternRes.status === "fulfilled") setPatternSummary(patternRes.value);
      if (recommendationRes.status === "fulfilled") setRecommendations(recommendationRes.value || []);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some security score data could not be loaded.");
        if (!silent) toast.error("Some security score data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load the security score workspace.");
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

  const score = scoreResult?.score ?? 0;
  const grade = scoreResult?.grade ?? "Unknown";
  const factors = scoreResult?.factors ?? [];
  const delta = scoreResult?.delta;
  const deltaExplanation = scoreResult?.delta_explanation;

  const breakdownData = useMemo(
    () =>
      [...factors]
        .sort((a, b) => (b.deduction || 0) - (a.deduction || 0))
        .map((f) => ({
          category: f.category,
          deduction: f.deduction || 0,
          weight: f.weight || 0,
          reason: f.reason,
        })),
    [factors]
  );

  const classificationData = useMemo(() => {
    const counts = classificationSummary?.counts ?? {};
    return Object.entries(counts)
      .filter(([, count]) => count > 0)
      .map(([category, count]) => ({ category, count }));
  }, [classificationSummary]);

  const patternCategoryData = useMemo(() => {
    const counts = patternSummary?.category_counts ?? {};
    return Object.entries(counts).map(([category, count]) => ({ category, count }));
  }, [patternSummary]);

  const priorityOverviewData = useMemo(() => {
    const counts = {};
    PRIORITY_ORDER.forEach((level) => {
      counts[level] = 0;
    });
    recommendations.forEach((rec) => {
      const level = rec.priority || "Low";
      counts[level] = (counts[level] || 0) + 1;
    });
    return PRIORITY_ORDER.map((level) => ({ priority: level, count: counts[level] || 0 }));
  }, [recommendations]);

  const sortedRecommendations = useMemo(
    () =>
      [...recommendations]
        .sort((a, b) => priorityRank(b.priority) - priorityRank(a.priority))
        .slice(0, TOP_RECOMMENDATIONS_LIMIT),
    [recommendations]
  );

  if (isLoading) {
    return (
      <Card title="Security Score" icon={PiShieldStarBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading security score..." />
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
            <PiShieldStarBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Explainable AI Security Score
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

      {/* Security Score + Status */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Security Score" icon={PiGaugeBold} className="lg:col-span-1">
          <div className="flex items-center gap-4">
            <ProgressRing
              value={score}
              size={104}
              color={GRADE_TO_RING_COLOR[grade] || "lavender"}
              label={grade}
            />
            <div className="flex flex-col gap-1.5">
              <StatusBadge status={grade} />
              {typeof delta === "number" && (
                <p
                  className={`text-xs font-medium ${
                    delta > 0 ? "text-[#a3c266]" : delta < 0 ? "text-[#f87171]" : "text-[var(--color-text-secondary,#64748b)]"
                  }`}
                >
                  {delta > 0 ? "▲" : delta < 0 ? "▼" : "—"} {Math.abs(delta).toFixed(1)} pts vs last cycle
                </p>
              )}
              {deltaExplanation && (
                <p className="text-xs text-[var(--color-text-secondary,#64748b)]">{deltaExplanation}</p>
              )}
            </div>
          </div>
          <p className="mt-3 flex items-center gap-1 text-xs text-[var(--color-text-secondary,#64748b)]">
            <PiClockBold className="h-3.5 w-3.5" />
            Last updated {formatTimestamp(scoreResult?.timestamp)}
          </p>
        </Card>

        {/* Score Breakdown */}
        <Card title="Score Breakdown" icon={PiChartBarBold} className="lg:col-span-2">
          {breakdownData.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No score breakdown available yet.
            </p>
          ) : (
            <>
              <div className="h-52 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breakdownData} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" horizontal={false} />
                    <XAxis
                      type="number"
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="category"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      axisLine={{ stroke: "var(--color-border,#232733)" }}
                      tickLine={false}
                      width={110}
                    />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      formatter={(value) => [`${Number(value).toFixed(1)} pts deducted`, "Deduction"]}
                      contentStyle={{
                        background: "var(--color-bg-elevated,#161922)",
                        border: "1px solid var(--color-border,#232733)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="deduction" radius={[0, 4, 4, 0]}>
                      {breakdownData.map((entry) => (
                        <Cell
                          key={entry.category}
                          fill={entry.deduction > 0 ? "#f87171" : "#a3c266"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 flex flex-col gap-1.5">
                {breakdownData.map((factor) => (
                  <div
                    key={factor.category}
                    className="flex flex-col gap-0.5 rounded-lg border border-[var(--color-border,#232733)] p-2.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="text-xs font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {factor.category}
                    </span>
                    <span className="text-xs text-[var(--color-text-secondary,#94a3b8)]">{factor.reason}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Threat Classification Summary + Attack Pattern Summary */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Threat Classification Summary" icon={PiFingerprintBold}>
          {classificationData.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No classified threats in the recent window.
            </p>
          ) : (
            <div className="flex flex-col items-center gap-3 sm:flex-row">
              <div className="h-44 w-44 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={classificationData}
                      dataKey="count"
                      nameKey="category"
                      innerRadius={40}
                      outerRadius={68}
                      paddingAngle={2}
                    >
                      {classificationData.map((entry, index) => (
                        <Cell
                          key={entry.category}
                          fill={CLASSIFICATION_COLORS[index % CLASSIFICATION_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "var(--color-bg-elevated,#161922)",
                        border: "1px solid var(--color-border,#232733)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-1 flex-col gap-1.5">
                {classificationData.map((entry, index) => (
                  <div key={entry.category} className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex items-center gap-1.5 text-[var(--color-text-secondary,#94a3b8)]">
                      <span
                        className="h-2 w-2 flex-shrink-0 rounded-full"
                        style={{ backgroundColor: CLASSIFICATION_COLORS[index % CLASSIFICATION_COLORS.length] }}
                      />
                      {entry.category}
                    </span>
                    <span className="font-medium text-[var(--color-text-primary,#f1f5f9)]">{entry.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Attack Pattern Summary" icon={PiPathBold}>
          <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {patternSummary?.total ?? 0}
          </p>
          <p className="mb-3 text-xs text-[var(--color-text-secondary,#64748b)]">
            correlated attack pattern(s) identified
          </p>
          {patternCategoryData.length === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
              No recurring or correlated attack patterns detected.
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {patternCategoryData.map((entry) => (
                <div
                  key={entry.category}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border,#232733)] px-3 py-2 text-xs"
                >
                  <span className="text-[var(--color-text-secondary,#94a3b8)]">{entry.category}</span>
                  <span className="font-medium text-[var(--color-text-primary,#f1f5f9)]">{entry.count}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Threat Priority Overview */}
      <Card title="Threat Priority Overview" icon={PiWarningOctagonBold}>
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={priorityOverviewData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" vertical={false} />
              <XAxis
                dataKey="priority"
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
                {priorityOverviewData.map((entry) => (
                  <Cell key={entry.priority} fill={PRIORITY_COLOR[entry.priority]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Top Security Recommendations */}
      <Card title="Top Security Recommendations" icon={PiListChecksBold}>
        {sortedRecommendations.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No active recommendations — current posture does not require action.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {sortedRecommendations.map((rec) => (
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

export default SecurityScore;