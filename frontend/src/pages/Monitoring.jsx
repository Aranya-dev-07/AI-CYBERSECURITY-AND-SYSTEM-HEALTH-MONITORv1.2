import { useEffect, useState } from "react";
import toast from "react-hot-toast";

import LiveMetrics from "../monitoring/LiveMetrics.jsx";
import ProcessMonitoring from "../monitoring/ProcessMonitoring.jsx";
import Graphs from "../monitoring/Graphs.jsx";
import Charts from "../monitoring/Charts.jsx";
import Controls from "../monitoring/Controls.jsx";

import Loader from "../components/Loader.jsx";

import { useSystemStatus } from "../context/SystemStatusContext.jsx";
import { getLatestMetrics, getLatestProcesses } from "../services/api.js";

/**
 * Monitoring — the live monitoring workspace. Pure orchestration: lays
 * out LiveMetrics, ProcessMonitoring, Graphs, Charts, and Controls in a
 * responsive grid, and hands each widget the data/context it needs.
 * No collection, aggregation, or threshold logic lives here — that is
 * owned by the backend (monitoring/*.py) and the widgets themselves.
 */
function Monitoring() {
  const { status } = useSystemStatus();

  const [metrics, setMetrics] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadInitialData() {
      setIsLoading(true);
      try {
        const [metricsRes, processesRes] = await Promise.allSettled([
          getLatestMetrics({ limit: 60 }),
          getLatestProcesses({ limit: 5 }),
        ]);

        if (!isMounted) return;

        if (metricsRes.status === "fulfilled") setMetrics(metricsRes.value || []);
        if (processesRes.status === "fulfilled") setProcesses(processesRes.value || []);

        if ([metricsRes, processesRes].some((r) => r.status === "rejected")) {
          toast.error("Some monitoring data could not be loaded.");
        }
      } catch {
        if (isMounted) toast.error("Failed to load monitoring data.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadInitialData();
    return () => {
      isMounted = false;
    };
  }, []);

  const isMonitoringActive = status?.monitoring === "online";

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h2 className="text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          Monitoring
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Live CPU, RAM, disk, and network telemetry with top process activity.
        </p>
      </section>

      {/* Controls */}
      <Controls isMonitoringActive={isMonitoringActive} />

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader label="Loading monitoring data..." />
        </div>
      ) : (
        <>
          {/* Live snapshot metrics */}
          <LiveMetrics metrics={metrics} isMonitoringActive={isMonitoringActive} />

          {/* Charts + Graphs */}
          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Graphs metrics={metrics} />
            <Charts metrics={metrics} />
          </section>

          {/* Process activity */}
          <ProcessMonitoring processes={processes} />
        </>
      )}
    </div>
  );
}

export default Monitoring;