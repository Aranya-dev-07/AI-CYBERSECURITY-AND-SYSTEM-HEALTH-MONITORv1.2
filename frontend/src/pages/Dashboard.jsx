import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import {
  PiActivityBold,
  PiBrainBold,
  PiWarningBold,
  PiPulseBold,
  PiShieldCheckeredBold,
  PiSparkleBold,
  PiFileTextBold,
  PiPlayBold,
  PiArrowRightBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";
import {
  getDashboardStatistics,
  getLatestAIResult,
  getReports,
} from "../services/api.js";

const QUICK_ACTIONS = [
  { label: "Start Monitoring", to: "/monitoring", icon: PiPlayBold },
  { label: "Open Trinetra AI", to: "/ai-workspace", icon: PiBrainBold },
  { label: "Run Security Scan", to: "/cybersecurity", icon: PiShieldCheckeredBold },
  { label: "View Reports", to: "/reports", icon: PiFileTextBold },
];

/**
 * Dashboard — executive landing page. Pure orchestration: fetches
 * summary data on mount and hands it to reusable presentational
 * widgets. No business logic (scoring, aggregation, thresholds) lives
 * here — that all happens server-side (ai_engine.py, crud.py).
 */
function Dashboard() {
  const navigate = useNavigate();
  const { status } = useSystemStatus();

  const [stats, setStats] = useState(null);
  const [aiResult, setAiResult] = useState(null);
  const [reports, setReports] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadDashboardData() {
      setIsLoading(true);
      try {
        const [statsRes, aiRes, reportsRes] = await Promise.allSettled([
          getDashboardStatistics(),
          getLatestAIResult(),
          getReports({ limit: 5 }),
        ]);

        if (!isMounted) return;

        if (statsRes.status === "fulfilled") setStats(statsRes.value);
        if (aiRes.status === "fulfilled") setAiResult(aiRes.value);
        if (reportsRes.status === "fulfilled") setReports(reportsRes.value || []);

        if ([statsRes, aiRes, reportsRes].some((r) => r.status === "rejected")) {
          toast.error("Some dashboard data could not be loaded.");
        }
      } catch {
        if (isMounted) toast.error("Failed to load dashboard data.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadDashboardData();
    return () => {
      isMounted = false;
    };
  }, []);

  const healthScore = aiResult?.health_score ?? stats?.latest_health_score ?? null;
  const healthStatus = aiResult?.health_status ?? stats?.latest_health_status ?? "Unknown";

  return (
    <div className="flex flex-col gap-6">
      {/* Welcome section */}
      <section className="flex flex-col gap-1">
        <h2 className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          Welcome back 👋
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Here&apos;s what&apos;s happening across your systems right now.
        </p>
      </section>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader label="Loading dashboard..." />
        </div>
      ) : (
        <>
          {/* System Overview */}
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card
              title="CPU Usage"
              icon={PiActivityBold}
              value={stats?.avg_cpu != null ? `${stats.avg_cpu}%` : "—"}
              subtitle={`Peak ${stats?.peak_cpu != null ? `${stats.peak_cpu}%` : "—"}`}
            />
            <Card
              title="RAM Usage"
              icon={PiPulseBold}
              value={stats?.avg_ram != null ? `${stats.avg_ram}%` : "—"}
              subtitle={`Peak ${stats?.peak_ram != null ? `${stats.peak_ram}%` : "—"}`}
            />
            <Card
              title="Disk Usage"
              icon={PiActivityBold}
              value={stats?.avg_disk_usage != null ? `${stats.avg_disk_usage}%` : "—"}
              subtitle="Average across sessions"
            />
            <Card
              title="Total Alerts"
              icon={PiWarningBold}
              value={stats?.total_alerts ?? "—"}
              subtitle={`Across ${stats?.total_runs ?? 0} session(s)`}
              accent="warning"
            />
          </section>

          {/* AI Health + Cybersecurity + Monitoring status */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card
              title="AI Health Score"
              icon={PiBrainBold}
              value={healthScore != null ? `${healthScore}/100` : "—"}
              footer={<StatusBadge status={healthStatus} />}
              onClick={() => navigate("/ai-workspace")}
            />
            <Card
              title="Monitoring Status"
              icon={PiPulseBold}
              value={status?.monitoring === "online" ? "Active" : "Idle"}
              footer={<StatusBadge status={status?.monitoring ?? "offline"} />}
              onClick={() => navigate("/monitoring")}
            />
            <Card
              title="Cybersecurity Status"
              icon={PiShieldCheckeredBold}
              value={status?.security ?? "Unknown"}
              footer={<StatusBadge status={status?.security ?? "offline"} />}
              onClick={() => navigate("/cybersecurity")}
            />
          </section>

          {/* Latest AI Insights + Recent Reports */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card title="Latest AI Insights" icon={PiSparkleBold} className="min-h-[220px]">
              {aiResult?.recommendations?.length ? (
                <ul className="flex flex-col gap-3">
                  {aiResult.recommendations.slice(0, 4).map((rec) => (
                    <li
                      key={rec.recommendation_id}
                      className="rounded-lg border border-[var(--color-border,#232733)] bg-[var(--color-bg,#0f1115)] px-3 py-2"
                    >
                      <p className="text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                        {rec.title}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                        {rec.reasoning}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
                  No AI insights available yet. Start a monitoring session to generate them.
                </p>
              )}
            </Card>

            <Card title="Recent Reports" icon={PiFileTextBold} className="min-h-[220px]">
              {reports.length ? (
                <ul className="flex flex-col divide-y divide-[var(--color-border,#232733)]">
                  {reports.map((report) => (
                    <li
                      key={report.start_time}
                      className="flex items-center justify-between py-2.5 text-sm"
                    >
                      <div>
                        <p className="font-medium text-[var(--color-text-primary,#f1f5f9)]">
                          {new Date(report.start_time).toLocaleString()}
                        </p>
                        <p className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
                          Avg CPU {report.avg_cpu}% · {report.total_alerts} alert(s)
                        </p>
                      </div>
                      <PiArrowRightBold className="h-4 w-4 flex-shrink-0 text-[var(--color-text-secondary,#64748b)]" />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
                  No reports yet. Reports are generated automatically when a monitoring session ends.
                </p>
              )}
            </Card>
          </section>

          {/* Quick Actions */}
          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)]">
              Quick Actions
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {QUICK_ACTIONS.map(({ label, to, icon: Icon }) => (
                <button
                  key={to}
                  type="button"
                  onClick={() => navigate(to)}
                  className="flex flex-col items-center gap-2 rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] px-4 py-4 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)] transition-all hover:-translate-y-0.5 hover:border-violet-500/40 hover:shadow-lg hover:shadow-violet-900/10"
                >
                  <Icon className="h-5 w-5 text-violet-400" />
                  {label}
                </button>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default Dashboard;