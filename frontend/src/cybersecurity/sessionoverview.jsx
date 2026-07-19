import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiShieldCheckBold,
  PiCpuBold,
  PiGlobeBold,
  PiPlugsConnectedBold,
  PiLockKeyBold,
  PiLockKeyOpenBold,
  PiUsersBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiShieldWarningBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import ProgressRing from "../components/ProgressRing.jsx";
import Loader from "../components/Loader.jsx";

import {
  getOverallSecurityStatus,
  getProcessSecurityEvents,
  getNetworkSecurityEvents,
  getPortSecurityEvents,
  getFirewallStatus,
  getActiveSessions,
} from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;

const RISK_ORDER = { high: 0, medium: 1, low: 2, none: 3 };

/** Maps backend vocabularies (risk levels, engine component status,
 * firewall enabled/available booleans) onto values StatusBadge already
 * understands, without modifying StatusBadge itself. */
function toBadgeStatus(raw) {
  const value = String(raw ?? "").toLowerCase();
  if (["operational", "true"].includes(value)) return "healthy";
  if (["unavailable", "false", "critical"].includes(value)) return "critical";
  if (["degraded", "warning"].includes(value)) return "warning";
  if (["stopped", "offline"].includes(value)) return "offline";
  if (["unknown", ""].includes(value)) return "unknown";
  return value; // "low" | "medium" | "high" | "none" already handled by StatusBadge's own aliases
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString();
}

function formatBps(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)} MB/s`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(2)} KB/s`;
  return `${Math.round(value)} B/s`;
}

function riskCounts(items) {
  const counts = { none: 0, low: 0, medium: 0, high: 0 };
  (items || []).forEach((item) => {
    const level = (item?.risk_level || "none").toLowerCase();
    if (counts[level] != null) counts[level] += 1;
  });
  return counts;
}

function overallScoreFromCounts(counts, total) {
  if (!total) return 100;
  const penalty = counts.low * 5 + counts.medium * 15 + counts.high * 30;
  return Math.max(0, Math.min(100, Math.round(100 - penalty / Math.max(1, total) * 4)));
}

/**
 * SecurityOverview — the landing view of the Cybersecurity workspace.
 * Summarizes process, network, port, firewall, and session security
 * state plus an overall status, all sourced from the backend
 * cybersecurity engine via services/api.js. Purely presentational:
 * it counts and displays risk levels the backend already computed
 * (process_monitor.py, network_monitor.py, port_monitor.py,
 * firewall_monitor.py, session_monitor.py, security_engine.py) — it
 * performs no scanning, detection, or risk scoring of its own.
 */
function SecurityOverview() {
  const [engineStatus, setEngineStatus] = useState(null);
  const [processEvents, setProcessEvents] = useState([]);
  const [networkEvents, setNetworkEvents] = useState([]);
  const [portEvents, setPortEvents] = useState([]);
  const [firewall, setFirewall] = useState(null);
  const [sessions, setSessions] = useState([]);

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
        getOverallSecurityStatus(),
        getProcessSecurityEvents(),
        getNetworkSecurityEvents(),
        getPortSecurityEvents(),
        getFirewallStatus(),
        getActiveSessions(),
      ]);
      if (!isMountedRef.current) return;

      const [statusRes, processRes, networkRes, portRes, firewallRes, sessionsRes] = results;

      if (statusRes.status === "fulfilled") setEngineStatus(statusRes.value);
      if (processRes.status === "fulfilled") setProcessEvents(processRes.value || []);
      if (networkRes.status === "fulfilled") setNetworkEvents(networkRes.value || []);
      if (portRes.status === "fulfilled") setPortEvents(portRes.value || []);
      if (firewallRes.status === "fulfilled") setFirewall(firewallRes.value);
      if (sessionsRes.status === "fulfilled") setSessions(sessionsRes.value || []);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some cybersecurity data could not be loaded.");
        if (!silent) toast.error("Some cybersecurity data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load cybersecurity overview.");
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

  const processObservations = useMemo(
    () => processEvents.filter((e) => !e?.type || e.type === "process"),
    [processEvents]
  );
  const processCounts = useMemo(() => riskCounts(processObservations), [processObservations]);

  const trafficSample = useMemo(
    () => networkEvents.find((e) => e.type === "traffic_io") || null,
    [networkEvents]
  );
  const connectionEvents = useMemo(
    () => networkEvents.filter((e) => e.type === "connection"),
    [networkEvents]
  );
  const connectionCounts = useMemo(() => riskCounts(connectionEvents), [connectionEvents]);

  const listeningPorts = useMemo(
    () => portEvents.filter((e) => e.type === "port_listening"),
    [portEvents]
  );
  const portCounts = useMemo(() => riskCounts(listeningPorts), [listeningPorts]);
  const recentPortChanges = useMemo(
    () => portEvents.filter((e) => e.type === "port_opened" || e.type === "port_closed").length,
    [portEvents]
  );

  const sessionCounts = useMemo(() => riskCounts(sessions), [sessions]);
  const sortedSessions = useMemo(
    () =>
      [...sessions].sort(
        (a, b) => (RISK_ORDER[a.risk_level] ?? 9) - (RISK_ORDER[b.risk_level] ?? 9)
      ),
    [sessions]
  );

  const overallScore = useMemo(() => {
    const combined = [
      ...processObservations,
      ...connectionEvents,
      ...listeningPorts,
      ...sessions,
    ];
    const counts = riskCounts(combined);
    const firewallPenalty = firewall && firewall.enabled === false ? 20 : firewall && !firewall.available ? 30 : 0;
    const base = overallScoreFromCounts(counts, combined.length);
    return Math.max(0, base - firewallPenalty);
  }, [processObservations, connectionEvents, listeningPorts, sessions, firewall]);

  const overallColor = overallScore >= 80 ? "olive" : overallScore >= 50 ? "magenta" : "red";
  const overallRingColor = overallScore >= 80 ? "olive" : overallScore >= 50 ? "magenta" : "red";

  if (isLoading) {
    return (
      <Card title="Security Overview" icon={PiShieldCheckBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading security overview..." />
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
            <PiShieldCheckBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Security Overview
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

      {/* Overall Security Status */}
      <Card title="Overall Security Status" icon={PiShieldCheckBold}>
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <ProgressRing value={overallScore} size={88} color={overallRingColor} />
            <div>
              <StatusBadge status={toBadgeStatus(engineStatus?.status)} />
              <p className="mt-1 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                Security cycle #{engineStatus?.cycle_count ?? 0}
              </p>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
                Last cycle: {formatTimestamp(engineStatus?.last_cycle_at)}
              </p>
            </div>
          </div>

          <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:grid-cols-5">
            {Object.entries(engineStatus?.components || {}).map(([name, status]) => (
              <div
                key={name}
                className="flex flex-col items-center gap-1 rounded-lg border border-[var(--color-border,#232733)] px-2 py-2"
              >
                <span className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]">
                  {name.replace(/_monitor$/, "").replace(/_/g, " ")}
                </span>
                <StatusBadge status={toBadgeStatus(status)} size="sm" />
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Summary grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {/* Process Monitoring Summary */}
        <Card title="Process Monitoring" icon={PiCpuBold}>
          <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {processObservations.length}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">processes observed</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusBadge status={processCounts.high ? "critical" : "healthy"} />
            <span className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
              {processCounts.high} high · {processCounts.medium} medium · {processCounts.low} low
            </span>
          </div>
        </Card>

        {/* Network Monitoring Summary */}
        <Card title="Network Monitoring" icon={PiGlobeBold}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Outbound</p>
              <p className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                {formatBps(trafficSample?.send_bps)}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Inbound</p>
              <p className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                {formatBps(trafficSample?.recv_bps)}
              </p>
            </div>
            <StatusBadge status={trafficSample?.is_spike ? "critical" : "healthy"} />
          </div>
          <p className="mt-3 text-xs text-[var(--color-text-secondary,#94a3b8)]">
            {connectionEvents.length} active connections · {connectionCounts.high + connectionCounts.medium} flagged
          </p>
        </Card>

        {/* Port Monitoring Summary */}
        <Card title="Port Monitoring" icon={PiPlugsConnectedBold}>
          <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {listeningPorts.length}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">listening ports</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusBadge status={portCounts.high ? "critical" : "healthy"} />
            <span className="text-xs text-[var(--color-text-secondary,#94a3b8)]">
              {recentPortChanges} change(s) this cycle
            </span>
          </div>
        </Card>

        {/* Firewall Status */}
        <Card title="Firewall Status" icon={firewall?.enabled ? PiLockKeyBold : PiLockKeyOpenBold}>
          <StatusBadge
            status={toBadgeStatus(!firewall?.available ? "unavailable" : firewall?.enabled)}
          />
          <p className="mt-2 text-sm text-[var(--color-text-primary,#f1f5f9)]">
            {firewall?.backend || "No backend detected"}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-secondary,#64748b)]">
            {firewall?.detail || "Firewall status unavailable"}
          </p>
        </Card>

        {/* Active User Sessions */}
        <Card title="Active User Sessions" icon={PiUsersBold}>
          <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {sessions.length}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">active sessions</p>
          <div className="mt-3 flex flex-col gap-1.5">
            {sortedSessions.slice(0, 3).map((session, index) => (
              <div
                key={`${session.username}-${session.terminal}-${index}`}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-[var(--color-text-primary,#f1f5f9)]">
                  {session.username || "unknown"}
                  <span className="text-[var(--color-text-secondary,#64748b)]"> @ {session.terminal || "—"}</span>
                </span>
                <StatusBadge status={toBadgeStatus(session.risk_level)} size="sm" />
              </div>
            ))}
            {sessions.length === 0 && (
              <p className="text-xs text-[var(--color-text-secondary,#64748b)]">No active sessions.</p>
            )}
          </div>
        </Card>

        {/* Combined risk callout */}
        <Card title="Flagged This Cycle" icon={PiShieldWarningBold}>
          <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {processCounts.high + connectionCounts.high + portCounts.high + sessionCounts.high}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">high-risk findings</p>
          <p className="mt-3 text-xs text-[var(--color-text-secondary,#94a3b8)]">
            {processCounts.medium + connectionCounts.medium + portCounts.medium + sessionCounts.medium} medium-risk
            findings also require review.
          </p>
        </Card>
      </div>
    </div>
  );
}

export default SecurityOverview;