import { useEffect, useRef, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { PiChartLineBold } from "react-icons/pi";

import Card from "../components/Card.jsx";

import { getLatestMetrics } from "../services/api.js";

const MAX_POINTS = 30;
const POLL_INTERVAL_MS = 5000;

const AXIS_COLOR = "#64748b";
const GRID_COLOR = "#232733";

function formatTimeLabel(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function normalizeSample(sample) {
  return {
    timestamp: sample.timestamp,
    time: formatTimeLabel(sample.timestamp),
    cpu: sample.cpu_usage ?? 0,
    ram: sample.ram_usage ?? 0,
    disk: sample.disk_usage ?? 0,
    networkIn: sample.network_in_bps ?? 0,
    networkOut: sample.network_out_bps ?? 0,
  };
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-[var(--color-text-secondary,#94a3b8)]">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(1) : entry.value}
        </p>
      ))}
    </div>
  );
}

/**
 * Graphs — live-updating resource trend graphs (CPU, RAM, Disk,
 * Network) rendered with Recharts. Seeds from the `metrics` prop
 * (Monitoring.jsx) and appends new samples polled from
 * services/api.js, keeping a rolling window. No aggregation or
 * threshold logic lives here.
 *
 * Props:
 *   metrics (array) — historical metric samples (oldest → newest).
 */
function Graphs({ metrics = [] }) {
  const [data, setData] = useState(() => metrics.slice(-MAX_POINTS).map(normalizeSample));
  const lastTimestampRef = useRef(data[data.length - 1]?.timestamp ?? null);

  useEffect(() => {
    if (metrics.length) {
      const normalized = metrics.slice(-MAX_POINTS).map(normalizeSample);
      setData(normalized);
      lastTimestampRef.current = normalized[normalized.length - 1]?.timestamp ?? null;
    }
  }, [metrics]);

  useEffect(() => {
    let isMounted = true;

    async function pollLatest() {
      try {
        const latest = await getLatestMetrics({ limit: 1 });
        const sample = Array.isArray(latest) ? latest[latest.length - 1] : latest;
        if (!isMounted || !sample) return;

        if (sample.timestamp === lastTimestampRef.current) return;
        lastTimestampRef.current = sample.timestamp;

        setData((prev) => {
          const next = [...prev, normalizeSample(sample)];
          return next.length > MAX_POINTS ? next.slice(next.length - MAX_POINTS) : next;
        });
      } catch {
        // Silently skip a failed poll; the next interval will retry.
      }
    }

    const intervalId = setInterval(pollLatest, POLL_INTERVAL_MS);
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const hasData = data.length > 0;

  return (
    <Card title="Resource Graphs" icon={PiChartLineBold} className="min-h-[420px]">
      {!hasData ? (
        <p className="py-10 text-center text-sm text-[var(--color-text-secondary,#64748b)]">
          No graph data yet. Start a monitoring session to begin plotting trends.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              CPU Usage (%)
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} domain={[0, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="cpu"
                  name="CPU"
                  stroke="#8b5cf6"
                  fill="url(#cpuGradient)"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              RAM Usage (%)
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="ramGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} domain={[0, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="ram"
                  name="RAM"
                  stroke="#22d3ee"
                  fill="url(#ramGradient)"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              Disk Usage (%)
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="diskGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} domain={[0, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="disk"
                  name="Disk"
                  stroke="#f59e0b"
                  fill="url(#diskGradient)"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              Network I/O (B/s)
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={data}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Line
                  type="monotone"
                  dataKey="networkIn"
                  name="Inbound"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="networkOut"
                  name="Outbound"
                  stroke="#f472b6"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Card>
  );
}

export default Graphs;