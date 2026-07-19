import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { PiChartPieSliceBold } from "react-icons/pi";

import Card from "../components/Card.jsx";

import { getLatestProcesses, getReports } from "../services/api.js";

const POLL_INTERVAL_MS = 10000;

const AXIS_COLOR = "#64748b";
const GRID_COLOR = "#232733";

const RESOURCE_COLORS = { CPU: "#8b5cf6", RAM: "#22d3ee", Disk: "#f59e0b" };
const ALERT_COLORS = { Warning: "#fbbf24", Critical: "#f43f5e", Normal: "#34d399" };

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-3 py-2 text-xs shadow-lg">
      {label && <p className="mb-1 font-medium text-[var(--color-text-secondary,#94a3b8)]">{label}</p>}
      {payload.map((entry) => (
        <p key={entry.dataKey || entry.name} style={{ color: entry.color || entry.payload?.fill }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(1) : entry.value}
        </p>
      ))}
    </div>
  );
}

function average(values) {
  const nums = values.filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (!nums.length) return 0;
  return nums.reduce((sum, v) => sum + v, 0) / nums.length;
}

function peak(values) {
  const nums = values.filter((v) => typeof v === "number" && !Number.isNaN(v));
  return nums.length ? Math.max(...nums) : 0;
}

/**
 * Charts — monitoring analytics: resource distribution, per-process
 * resource usage, alert distribution, and a historical usage summary.
 * Derives its distribution/summary views from the `metrics` prop
 * (Monitoring.jsx) and fetches supplementary process/report data from
 * services/api.js. No monitoring, alerting, or aggregation business
 * logic lives here — only chart-ready data shaping for display.
 *
 * Props:
 *   metrics (array) — historical metric samples (oldest → newest).
 */
function Charts({ metrics = [] }) {
  const [processes, setProcesses] = useState([]);
  const [latestReport, setLatestReport] = useState(null);

  useEffect(() => {
    let isMounted = true;

    async function loadAnalyticsData() {
      try {
        const [processesRes, reportsRes] = await Promise.allSettled([
          getLatestProcesses({ limit: 5 }),
          getReports({ limit: 1 }),
        ]);

        if (!isMounted) return;

        if (processesRes.status === "fulfilled") setProcesses(processesRes.value || []);
        if (reportsRes.status === "fulfilled") {
          const reports = reportsRes.value || [];
          setLatestReport(reports[0] || null);
        }
      } catch {
        // Non-fatal: charts simply render with whatever data is available.
      }
    }

    loadAnalyticsData();
    const intervalId = setInterval(loadAnalyticsData, POLL_INTERVAL_MS);
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const latestSample = metrics[metrics.length - 1];

  const resourceDistribution = useMemo(() => {
    if (!latestSample) return [];
    return [
      { name: "CPU", value: latestSample.cpu_usage ?? 0 },
      { name: "RAM", value: latestSample.ram_usage ?? 0 },
      { name: "Disk", value: latestSample.disk_usage ?? 0 },
    ];
  }, [latestSample]);

  const processUsage = useMemo(
    () =>
      processes.map((p) => ({
        name: p.name || "unknown",
        CPU: p.cpu_percent ?? 0,
        RAM: p.memory_percent ?? 0,
      })),
    [processes]
  );

  const alertDistribution = useMemo(() => {
    if (!latestReport) return [];
    const warning = latestReport.warning_alerts ?? 0;
    const critical = latestReport.critical_alerts ?? 0;
    const total = latestReport.total_alerts ?? warning + critical;
    const normal = Math.max(0, total - warning - critical);

    return [
      { name: "Warning", value: warning },
      { name: "Critical", value: critical },
      { name: "Normal", value: normal },
    ].filter((entry) => entry.value > 0);
  }, [latestReport]);

  const historicalSummary = useMemo(() => {
    const cpuValues = metrics.map((m) => m.cpu_usage);
    const ramValues = metrics.map((m) => m.ram_usage);
    const diskValues = metrics.map((m) => m.disk_usage);

    return [
      { name: "CPU", Average: average(cpuValues), Peak: peak(cpuValues) },
      { name: "RAM", Average: average(ramValues), Peak: peak(ramValues) },
      { name: "Disk", Average: average(diskValues), Peak: peak(diskValues) },
    ];
  }, [metrics]);

  return (
    <Card title="Monitoring Analytics" icon={PiChartPieSliceBold} className="min-h-[420px]">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Resource Distribution */}
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
            Resource Distribution
          </p>
          {resourceDistribution.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={resourceDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {resourceDistribution.map((entry) => (
                    <Cell key={entry.name} fill={RESOURCE_COLORS[entry.name] || "#8b5cf6"} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState />
          )}
        </div>

        {/* Process Resource Usage */}
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
            Process Resource Usage
          </p>
          {processUsage.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={processUsage}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
                <Bar dataKey="CPU" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="RAM" fill="#22d3ee" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState />
          )}
        </div>

        {/* Alert Distribution */}
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
            Alert Distribution
          </p>
          {alertDistribution.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={alertDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                >
                  {alertDistribution.map((entry) => (
                    <Cell key={entry.name} fill={ALERT_COLORS[entry.name] || "#94a3b8"} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState message="No alert data for the latest session yet." />
          )}
        </div>

        {/* Historical Usage Summary */}
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
            Historical Usage Summary
          </p>
          {metrics.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={historicalSummary}>
                <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke={AXIS_COLOR} fontSize={11} tickLine={false} />
                <YAxis stroke={AXIS_COLOR} fontSize={11} tickLine={false} domain={[0, 100]} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, color: AXIS_COLOR }} />
                <Bar dataKey="Average" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Peak" fill="#f472b6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState />
          )}
        </div>
      </div>
    </Card>
  );
}

function EmptyState({ message = "No data available yet." }) {
  return (
    <div className="flex h-[220px] items-center justify-center text-sm text-[var(--color-text-secondary,#64748b)]">
      {message}
    </div>
  );
}

export default Charts;