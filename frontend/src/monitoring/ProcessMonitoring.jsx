import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { PiListMagnifyingGlassBold, PiCaretUpBold, PiCaretDownBold } from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

import { getLatestProcesses } from "../services/api.js";

const POLL_INTERVAL_MS = 5000;

const COLUMNS = [
  { key: "name", label: "Process Name", sortable: true, align: "left" },
  { key: "pid", label: "PID", sortable: true, align: "left" },
  { key: "cpu_percent", label: "CPU Usage", sortable: true, align: "right" },
  { key: "memory_percent", label: "RAM Usage", sortable: true, align: "right" },
  { key: "disk_io", label: "Disk I/O", sortable: false, align: "right" },
  { key: "network_io", label: "Network I/O", sortable: false, align: "right" },
  { key: "status", label: "Status", sortable: false, align: "left" },
];

function formatBytesPerSecond(value) {
  if (value == null || Number.isNaN(value)) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB/s`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB/s`;
  return `${Math.round(value)} B/s`;
}

function usageColor(value) {
  if (value == null) return "text-[var(--color-text-secondary,#94a3b8)]";
  if (value >= 80) return "text-rose-400";
  if (value >= 50) return "text-amber-400";
  return "text-emerald-400";
}

/**
 * ProcessMonitoring — sortable, auto-refreshing table of the top
 * resource-consuming processes. Polls services/api.js on an interval
 * and re-sorts client-side on column click. No process ranking or
 * collection logic lives here — that is owned by
 * monitoring/processes.py.
 *
 * Props:
 *   processes (array) — initial/seed process samples from Monitoring.jsx.
 */
function ProcessMonitoring({ processes = [] }) {
  const [rows, setRows] = useState(processes);
  const [sortKey, setSortKey] = useState("cpu_percent");
  const [sortDirection, setSortDirection] = useState("desc");
  const hasWarnedRef = useRef(false);

  useEffect(() => {
    setRows(processes);
  }, [processes]);

  useEffect(() => {
    let isMounted = true;

    async function pollProcesses() {
      try {
        const latest = await getLatestProcesses({ limit: 5 });
        if (isMounted && Array.isArray(latest)) {
          setRows(latest);
        }
      } catch {
        if (isMounted && !hasWarnedRef.current) {
          toast.error("Process feed interrupted.");
          hasWarnedRef.current = true;
        }
      }
    }

    const intervalId = setInterval(pollProcesses, POLL_INTERVAL_MS);
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const handleSort = (key) => {
    if (key === sortKey) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  };

  const sortedRows = useMemo(() => {
    const sortable = COLUMNS.find((c) => c.key === sortKey)?.sortable;
    if (!sortable) return rows;

    const copy = [...rows];
    copy.sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];

      if (typeof aVal === "string" || typeof bVal === "string") {
        const result = String(aVal ?? "").localeCompare(String(bVal ?? ""));
        return sortDirection === "asc" ? result : -result;
      }

      const result = (aVal ?? 0) - (bVal ?? 0);
      return sortDirection === "asc" ? result : -result;
    });
    return copy;
  }, [rows, sortKey, sortDirection]);

  return (
    <Card title="Top Processes" icon={PiListMagnifyingGlassBold}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border,#232733)]">
              {COLUMNS.map(({ key, label, sortable, align }) => (
                <th
                  key={key}
                  onClick={() => sortable && handleSort(key)}
                  className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary,#64748b)] ${
                    align === "right" ? "text-right" : "text-left"
                  } ${sortable ? "cursor-pointer select-none hover:text-[var(--color-text-primary,#f1f5f9)]" : ""}`}
                >
                  <span className={`inline-flex items-center gap-1 ${align === "right" ? "flex-row-reverse" : ""}`}>
                    {label}
                    {sortable && sortKey === key && (
                      sortDirection === "asc" ? (
                        <PiCaretUpBold className="h-3 w-3" />
                      ) : (
                        <PiCaretDownBold className="h-3 w-3" />
                      )
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMNS.length}
                  className="px-3 py-8 text-center text-sm text-[var(--color-text-secondary,#64748b)]"
                >
                  No process data available yet.
                </td>
              </tr>
            ) : (
              sortedRows.map((proc) => (
                <tr
                  key={`${proc.pid}-${proc.name}`}
                  className="border-b border-[var(--color-border,#232733)] last:border-0 hover:bg-white/[0.03]"
                >
                  <td className="px-3 py-2.5 font-medium text-[var(--color-text-primary,#f1f5f9)]">
                    {proc.name || "unknown"}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--color-text-secondary,#94a3b8)]">
                    {proc.pid ?? "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-medium ${usageColor(proc.cpu_percent)}`}>
                    {proc.cpu_percent != null ? `${proc.cpu_percent.toFixed(1)}%` : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-medium ${usageColor(proc.memory_percent)}`}>
                    {proc.memory_percent != null ? `${proc.memory_percent.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-[var(--color-text-secondary,#94a3b8)]">
                    {formatBytesPerSecond(proc.disk_io_bps)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-[var(--color-text-secondary,#94a3b8)]">
                    {formatBytesPerSecond(proc.network_io_bps)}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={proc.status || "running"} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default ProcessMonitoring;