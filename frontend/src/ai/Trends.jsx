import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import {
  PiTrendUpBold,
  PiCpuBold,
  PiMemoryBold,
  PiHardDriveBold,
  PiWifiHighBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiNotePencilBold,
} from "react-icons/pi";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";
import { getTrendAnalysis } from "../services/api.js";

const REFRESH_INTERVAL_MS = 30000;

const METRIC_CONFIG = {
  cpu_usage: { label: "CPU Trend", icon: PiCpuBold, color: "#38bdf8", unit: "%" },
  ram_usage: { label: "RAM Trend", icon: PiMemoryBold, color: "#a78bfa", unit: "%" },
  disk_usage: { label: "Disk Trend", icon: PiHardDriveBold, color: "#fbbf24", unit: "%" },
  network_in_bps: { label: "Network In Trend", icon: PiWifiHighBold, color: "#34d399", unit: "bps" },
  network_out_bps: { label: "Network Out Trend", icon: PiWifiHighBold, color: "#f472b6", unit: "bps" },
};

const NETWORK_METRICS = new Set(["network_in_bps", "network_out_bps"]);

function metricMeta(metricName) {
  return (
    METRIC_CONFIG[metricName] || {
      label: metricName,
      icon: PiTrendUpBold,
      color: "#94a3b8",
      unit: "",
    }
  );
}

function formatValue(value, unit) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  if (unit === "bps") {
    if (value >= 1e6) return `${(value / 1e6).toFixed(2)} Mbps`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(2)} Kbps`;
    return `${value.toFixed(0)} bps`;
  }
  return `${Number(value).toFixed(1)}${unit || ""}`;
}

function formatAxisTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function directionStatus(direction) {
  return direction || "Stable";
}

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-bg-elevated,#161922)] px-3 py-2 text-xs shadow-lg">
      <p className="text-[var(--color-text-secondary,#64748b)]">{formatAxisTime(label)}</p>
      <p className="font-medium text-[var(--color-text-primary,#f1f5f9)]">
        {formatValue(payload[0]?.value, unit)}
      </p>
    </div>
  );
}

/**
 * MetricTrendChart — renders a single metric's historical series as an
 * area chart plus its explainable classification (direction/severity).
 * Consumes a TrendSeries object as returned by GET /api/ai/trends
 * (backend/api/schemas.py -> TrendSeries) and, when available, the
 * matching TrendResult explanation supplied via AIWorkspace. Performs
 * no trend computation itself.
 */
function MetricTrendChart({ series, trendResult }) {
  const meta = metricMeta(series.metric_name);
  const Icon = meta.icon;
  const points = (series.points || []).map((p) => ({
    timestamp: p.timestamp,
    value: p.value,
  }));
  const direction = series.direction || trendResult?.direction;

  return (
    <Card title={meta.label} icon={Icon}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <StatusBadge status={directionStatus(direction)} />
        {trendResult?.severity && <StatusBadge status={trendResult.severity} />}
        <span className="ml-auto text-xs text-[var(--color-text-secondary,#64748b)]">
          {points.length ? `${points.length} samples` : "No data"}
        </span>
      </div>

      {points.length ? (
        <div className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`gradient-${series.metric_name}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={meta.color} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={meta.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#232733)" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatAxisTime}
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={{ stroke: "var(--color-border,#232733)" }}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={NETWORK_METRICS.has(series.metric_name) ? 56 : 36}
                tickFormatter={(v) => formatValue(v, meta.unit)}
              />
              <Tooltip content={<ChartTooltip unit={meta.unit} />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={meta.color}
                strokeWidth={2}
                fill={`url(#gradient-${series.metric_name})`}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-48 items-center justify-center">
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            Not enough historical data to chart this metric yet.
          </p>
        </div>
      )}

      {trendResult && (
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-white/10 pt-2 text-xs sm:grid-cols-4">
          <div>
            <p className="text-[var(--color-text-secondary,#64748b)]">Current</p>
            <p className="text-[var(--color-text-primary,#f1f5f9)]">
              {formatValue(trendResult.current_value, meta.unit)}
            </p>
          </div>
          <div>
            <p className="text-[var(--color-text-secondary,#64748b)]">Window Start</p>
            <p className="text-[var(--color-text-primary,#f1f5f9)]">
              {formatValue(trendResult.window_start_value, meta.unit)}
            </p>
          </div>
          <div>
            <p className="text-[var(--color-text-secondary,#64748b)]">R²</p>
            <p className="text-[var(--color-text-primary,#f1f5f9)]">
              {trendResult.r_squared != null ? trendResult.r_squared.toFixed(3) : "—"}
            </p>
          </div>
          <div>
            <p className="text-[var(--color-text-secondary,#64748b)]">Samples</p>
            <p className="text-[var(--color-text-primary,#f1f5f9)]">
              {trendResult.window_samples ?? "—"}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}

/**
 * Trends — displays AI trend analysis produced by the backend
 * (ai/trend_analysis.py -> analyze_all_trends / run_trend_analysis),
 * fetched via GET /api/ai/trends. Renders per-metric charts (CPU, RAM,
 * Disk, Network) with Recharts and surfaces the backend's natural
 * language trend explanation/summary. No trend detection, slope
 * calculation, or classification logic lives here.
 *
 * Props:
 *   trends (array)             — optional pre-fetched TrendResult[]
 *                                 (e.g. AIWorkspace's latestResult.trends),
 *                                 matched to series by metric name.
 *   resourceGrowth (array)     — optional TrendResult[] flagged as
 *                                 sustained resource growth.
 *   processMemoryLeaks (array) — optional MemoryLeakResult[].
 *   autoRefresh (bool)         — enable/disable polling. Default true.
 *   refreshInterval (number)   — ms between polls. Default 30000.
 */
function Trends({
  trends: initialTrends = [],
  resourceGrowth = [],
  processMemoryLeaks = [],
  autoRefresh = true,
  refreshInterval = REFRESH_INTERVAL_MS,
}) {
  const [series, setSeries] = useState([]);
  const [trendResults, setTrendResults] = useState(initialTrends || []);
  const [summary, setSummary] = useState(null);
  const [window_, setWindow] = useState("24h");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFetched, setLastFetched] = useState(null);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  const fetchTrends = useCallback(async ({ silent } = {}) => {
    if (!silent) setIsLoading(true);
    setIsRefreshing(true);
    try {
      const data = await getTrendAnalysis();
      if (!isMountedRef.current) return;
      setSeries(data?.series || []);
      setSummary(data?.summary ?? null);
      setWindow(data?.window || "24h");
      if (data?.trends) setTrendResults(data.trends);
      setLastFetched(new Date());
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load trend analysis.");
    } finally {
      if (!isMountedRef.current) return;
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    fetchTrends();

    let intervalId;
    if (autoRefresh) {
      intervalId = setInterval(() => fetchTrends({ silent: true }), refreshInterval);
    }

    return () => {
      isMountedRef.current = false;
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, fetchTrends]);

  const trendByMetric = useMemo(() => {
    const map = new Map();
    (trendResults || []).forEach((t) => map.set(t.metric, t));
    return map;
  }, [trendResults]);

  const orderedSeries = useMemo(() => {
    const known = Object.keys(METRIC_CONFIG);
    return [...(series || [])].sort((a, b) => {
      const ai = known.indexOf(a.metric_name);
      const bi = known.indexOf(b.metric_name);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [series]);

  if (isLoading) {
    return (
      <Card title="AI Trend Analysis" icon={PiTrendUpBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading trend analysis..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="AI Trend Analysis" icon={PiTrendUpBold}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
            Analysis window: <span className="text-[var(--color-text-primary,#f1f5f9)]">{window_}</span>
          </p>
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
              onClick={() => fetchTrends({ silent: true })}
              className="rounded-md border border-[var(--color-border,#232733)] px-2 py-1 font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
            >
              Refresh
            </button>
          </div>
        </div>
        {error && (
          <p className="mt-3 text-xs text-rose-400">{error} — showing last known data.</p>
        )}
      </Card>

      {summary && (
        <Card title="Trend Explanation" icon={PiNotePencilBold}>
          <p className="text-sm text-[var(--color-text-primary,#f1f5f9)]">{summary}</p>
        </Card>
      )}

      {orderedSeries.length === 0 ? (
        <Card>
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No trend data available yet. More monitoring history is needed to identify trends.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {orderedSeries.map((s) => (
            <MetricTrendChart
              key={s.metric_name}
              series={s}
              trendResult={trendByMetric.get(s.metric_name)}
            />
          ))}
        </div>
      )}

      {(resourceGrowth?.length > 0 || processMemoryLeaks?.length > 0) && (
        <Card title="Sustained Growth & Memory Leak Signals">
          <div className="flex flex-col gap-3">
            {resourceGrowth?.map((g) => (
              <div key={g.trend_id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {metricMeta(g.metric).label}
                  </span>
                  <StatusBadge status={g.severity} />
                </div>
                <p className="mt-1 text-xs text-[var(--color-text-secondary,#94a3b8)]">{g.explanation}</p>
                <p className="mt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatTimestamp(g.timestamp)}
                </p>
              </div>
            ))}
            {processMemoryLeaks?.map((leak) => (
              <div key={leak.leak_id} className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {leak.process_name}
                  </span>
                  <span className="text-xs text-rose-300">+{leak.growth_pct}% memory</span>
                </div>
                <p className="mt-1 text-xs text-[var(--color-text-secondary,#94a3b8)]">{leak.explanation}</p>
                <p className="mt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
                  {formatTimestamp(leak.timestamp)}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

export default Trends;