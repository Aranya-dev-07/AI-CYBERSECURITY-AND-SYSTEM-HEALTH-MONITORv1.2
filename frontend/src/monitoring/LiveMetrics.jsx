 import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  PiCpuBold,
  PiMemoryBold,
  PiHardDriveBold,
  PiWifiHighBold,
  PiClockCountdownBold,
  PiThermometerSimpleBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import ProgressRing from "../components/ProgressRing.jsx";
import Loader from "../components/Loader.jsx";

import { getLatestMetrics } from "../services/api.js";

const POLL_INTERVAL_MS = 5000;

function formatBytesPerSecond(bytesPerSecond) {
  if (bytesPerSecond == null || Number.isNaN(bytesPerSecond)) return "—";
  if (bytesPerSecond >= 1_000_000) return `${(bytesPerSecond / 1_000_000).toFixed(1)} MB/s`;
  if (bytesPerSecond >= 1_000) return `${(bytesPerSecond / 1_000).toFixed(1)} KB/s`;
  return `${Math.round(bytesPerSecond)} B/s`;
}

function formatUptime(firstTimestamp) {
  if (!firstTimestamp) return "—";
  const start = new Date(firstTimestamp).getTime();
  if (Number.isNaN(start)) return "—";

  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = elapsedSeconds % 60;

  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function usagePillColor(value) {
  if (value == null) return "text-[var(--color-text-secondary,#94a3b8)]";
  if (value >= 90) return "text-rose-400";
  if (value >= 75) return "text-amber-400";
  return "text-emerald-400";
}

/**
 * LiveMetrics — real-time CPU/RAM/Disk/Network/Uptime/Temperature
 * snapshot cards. Polls services/api.js for the latest sample while
 * monitoring is active, falling back to the most recent entry of the
 * `metrics` prop (supplied by Monitoring.jsx) until the first poll
 * resolves. No collection, aggregation, or threshold logic lives here.
 *
 * Props:
 *   metrics (array)            — historical metric samples (oldest → newest).
 *   isMonitoringActive (bool)  — whether polling should be active.
 */
function LiveMetrics({ metrics = [], isMonitoringActive = false }) {
  const [current, setCurrent] = useState(() => metrics[metrics.length - 1] || null);
  const [isLoading, setIsLoading] = useState(!current);
  const [hasError, setHasError] = useState(false);
  const hasWarnedRef = useRef(false);

  useEffect(() => {
    if (!current && metrics.length) {
      setCurrent(metrics[metrics.length - 1]);
      setIsLoading(false);
    }
  }, [metrics, current]);

  useEffect(() => {
    let isMounted = true;
    let intervalId;

    async function pollLatest() {
      try {
        const latest = await getLatestMetrics({ limit: 1 });
        if (!isMounted) return;

        const sample = Array.isArray(latest) ? latest[latest.length - 1] : latest;
        if (sample) {
          setCurrent(sample);
          setHasError(false);
        }
      } catch {
        if (!isMounted) return;
        setHasError(true);
        if (!hasWarnedRef.current) {
          toast.error("Live metrics feed interrupted.");
          hasWarnedRef.current = true;
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    if (isMonitoringActive) {
      pollLatest();
      intervalId = setInterval(pollLatest, POLL_INTERVAL_MS);
    } else {
      setIsLoading(false);
    }

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [isMonitoringActive]);

  const uptimeLabel = useMemo(() => formatUptime(metrics[0]?.timestamp), [metrics]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Loader label="Loading live metrics..." />
      </div>
    );
  }

  if (!current) {
    return (
      <Card title="Live Metrics" icon={PiCpuBold}>
        <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
          {hasError
            ? "Unable to reach the metrics feed. Retrying automatically..."
            : "No live metrics yet. Start a monitoring session to begin collecting data."}
        </p>
      </Card>
    );
  }

  const totalNetworkBps = (current.network_in_bps || 0) + (current.network_out_bps || 0);

  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Card title="CPU Usage" icon={PiCpuBold}>
        <div className="flex items-center gap-4">
          <ProgressRing value={current.cpu_usage ?? 0} />
          <div>
            <p className={`text-2xl font-semibold ${usagePillColor(current.cpu_usage)}`}>
              {current.cpu_usage != null ? `${current.cpu_usage.toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Current load</p>
          </div>
        </div>
      </Card>

      <Card title="RAM Usage" icon={PiMemoryBold}>
        <div className="flex items-center gap-4">
          <ProgressRing value={current.ram_usage ?? 0} />
          <div>
            <p className={`text-2xl font-semibold ${usagePillColor(current.ram_usage)}`}>
              {current.ram_usage != null ? `${current.ram_usage.toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Memory in use</p>
          </div>
        </div>
      </Card>

      <Card title="Disk Usage" icon={PiHardDriveBold}>
        <div className="flex items-center gap-4">
          <ProgressRing value={current.disk_usage ?? 0} />
          <div>
            <p className={`text-2xl font-semibold ${usagePillColor(current.disk_usage)}`}>
              {current.disk_usage != null ? `${current.disk_usage.toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Storage consumed</p>
          </div>
        </div>
      </Card>

      <Card title="Network I/O" icon={PiWifiHighBold}>
        <div className="flex flex-col gap-1">
          <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
            {formatBytesPerSecond(totalNetworkBps)}
          </p>
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
            ↓ {formatBytesPerSecond(current.network_in_bps)} · ↑{" "}
            {formatBytesPerSecond(current.network_out_bps)}
          </p>
        </div>
      </Card>

      <Card title="System Uptime" icon={PiClockCountdownBold}>
        <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          {uptimeLabel}
        </p>
        <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Since session start</p>
      </Card>

      <Card title="CPU Temperature" icon={PiThermometerSimpleBold}>
        <p className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          {current.cpu_temperature != null ? `${current.cpu_temperature.toFixed(1)}°C` : "N/A"}
        </p>
        <p className="text-xs text-[var(--color-text-secondary,#64748b)]">
          {current.cpu_temperature != null ? "Sensor reading" : "Not available on this system"}
        </p>
      </Card>
    </section>
  );
}

export default LiveMetrics;