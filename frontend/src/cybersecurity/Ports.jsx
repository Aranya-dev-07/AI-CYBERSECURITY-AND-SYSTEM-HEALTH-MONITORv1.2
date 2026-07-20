import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiPlugsConnectedBold,
  PiDoorOpenBold,
  PiWarningCircleBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiCpuBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { getListeningPorts, getSuspiciousPorts, getRecentPortEvents } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;
const EVENTS_LIMIT = 50;

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function portLabel(port) {
  return `${port.protocol || "?"}/${port.local_port ?? "?"}`;
}

/**
 * Ports — displays monitored network ports for the Cybersecurity
 * workspace: currently active listening ports, their protocol and
 * associated process, newly opened ports, and suspicious ports.
 * Sourced entirely from port_monitor.py via services/api.js. Purely
 * presentational — implements no port scanning or risk assessment of
 * its own.
 */
function Ports() {
  const [listeningPorts, setListeningPorts] = useState([]);
  const [suspiciousPorts, setSuspiciousPorts] = useState([]);
  const [recentEvents, setRecentEvents] = useState([]);

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
        getListeningPorts(),
        getSuspiciousPorts(),
        getRecentPortEvents(EVENTS_LIMIT),
      ]);
      if (!isMountedRef.current) return;

      const [listeningRes, suspiciousRes, eventsRes] = results;
      if (listeningRes.status === "fulfilled") setListeningPorts(listeningRes.value || []);
      if (suspiciousRes.status === "fulfilled") setSuspiciousPorts(suspiciousRes.value || []);
      if (eventsRes.status === "fulfilled") setRecentEvents(eventsRes.value || []);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some port data could not be loaded.");
        if (!silent) toast.error("Some port data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load port information.");
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

  const newlyOpenedPorts = useMemo(
    () =>
      recentEvents
        .filter((e) => e.type === "port_opened")
        .slice()
        .reverse(),
    [recentEvents]
  );

  const sortedListeningPorts = useMemo(
    () =>
      [...listeningPorts].sort((a, b) => {
        const rank = { high: 0, medium: 1, low: 2, none: 3 };
        return (rank[a.risk_level] ?? 9) - (rank[b.risk_level] ?? 9);
      }),
    [listeningPorts]
  );

  if (isLoading) {
    return (
      <Card title="Ports" icon={PiPlugsConnectedBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading port information..." />
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
            <PiPlugsConnectedBold className="h-5 w-5 text-violet-400" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              Ports
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

      {/* Active Ports */}
      <Card title="Active Ports" icon={PiPlugsConnectedBold}>
        {sortedListeningPorts.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No listening ports observed.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--color-border,#232733)]">
                  {["Port", "Protocol", "Local Address", "Process", "Exposure", "Risk"].map((h) => (
                    <th
                      key={h}
                      className="py-2 pr-4 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary,#64748b)]"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedListeningPorts.map((port, index) => (
                  <tr
                    key={`${port.protocol}-${port.local_port}-${port.pid}-${index}`}
                    className="border-b border-white/5"
                  >
                    <td className="py-2 pr-4 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {port.local_port ?? "—"}
                    </td>
                    <td className="py-2 pr-4 text-sm text-[var(--color-text-secondary,#94a3b8)]">
                      {port.protocol || "—"}
                    </td>
                    <td className="py-2 pr-4 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      {port.local_ip || "—"}
                    </td>
                    <td className="py-2 pr-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                      <span className="flex items-center gap-1.5">
                        <PiCpuBold className="h-3.5 w-3.5 text-[var(--color-text-secondary,#64748b)]" />
                        {port.process_name || (port.pid != null ? `pid ${port.pid}` : "unknown")}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge
                        status={port.exposed_all_interfaces ? "warning" : "healthy"}
                        size="sm"
                      />
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge status={port.risk_level || "none"} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Newly Opened Ports */}
        <Card title="Newly Opened Ports" icon={PiDoorOpenBold}>
          {newlyOpenedPorts.length === 0 ? (
            <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
              No ports have opened recently.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {newlyOpenedPorts.slice(0, 8).map((event, index) => (
                <div
                  key={`${event.timestamp}-${index}`}
                  className="flex items-center justify-between rounded-lg border border-[var(--color-border,#232733)] px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <StatusBadge status={event.risk_level || "none"} size="sm" />
                    <span className="text-sm text-[var(--color-text-primary,#f1f5f9)]">
                      {portLabel(event)}
                    </span>
                    <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
                      {event.process_name || "unknown"}
                    </span>
                  </div>
                  <span className="text-xs text-[var(--color-text-secondary,#64748b)]">
                    {formatTimestamp(event.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Suspicious Ports */}
        <Card title="Suspicious Ports" icon={PiWarningCircleBold}>
          {suspiciousPorts.length === 0 ? (
            <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
              No suspicious ports flagged.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {suspiciousPorts.map((port, index) => (
                <div
                  key={`${port.protocol}-${port.local_port}-${index}`}
                  className="rounded-lg border border-[var(--color-border,#232733)] p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
                      {portLabel(port)}
                      <span className="text-xs font-normal text-[var(--color-text-secondary,#64748b)]">
                        {port.process_name || "unknown process"}
                      </span>
                    </span>
                    <StatusBadge status={port.risk_level || "none"} size="sm" />
                  </div>
                  {(port.risk_reasons || []).length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-0.5">
                      {port.risk_reasons.map((reason, reasonIndex) => (
                        <li
                          key={reasonIndex}
                          className="text-xs text-[var(--color-text-secondary,#94a3b8)]"
                        >
                          • {reason}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export default Ports;