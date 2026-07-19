import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { PiFileTextBold } from "react-icons/pi";

import TestRuns from "../reports/TestRuns.jsx";
import Database from "../reports/Database.jsx";
import Export from "../reports/Export.jsx";
import ReportHistory from "../reports/ReportHistory.jsx";

import Loader from "../components/Loader.jsx";

import { getReports, getDashboardStatistics } from "../services/api.js";

/**
 * Reports — the reports workspace. Pure orchestration: fetches session
 * report data and dashboard statistics from the backend and hands them
 * to TestRuns, Database, Export, and ReportHistory. No report
 * generation, aggregation, or file-writing logic lives here — that is
 * owned entirely by the backend (monitoring/reports.py, crud.py).
 */
function Reports() {
  const [reports, setReports] = useState([]);
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadReportsData() {
      setIsLoading(true);
      try {
        const [reportsRes, statsRes] = await Promise.allSettled([
          getReports({ limit: 50 }),
          getDashboardStatistics(),
        ]);

        if (!isMounted) return;

        if (reportsRes.status === "fulfilled") setReports(reportsRes.value || []);
        if (statsRes.status === "fulfilled") setStats(statsRes.value);

        if ([reportsRes, statsRes].some((r) => r.status === "rejected")) {
          toast.error("Some report data could not be loaded.");
        }
      } catch {
        if (isMounted) toast.error("Failed to load reports.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadReportsData();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          <PiFileTextBold className="h-6 w-6 text-violet-400" />
          Reports
        </h2>
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
          Session summaries, database records, and exportable monitoring history.
        </p>
      </section>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader label="Loading reports..." />
        </div>
      ) : (
        <>
          {/* Test run summaries */}
          <TestRuns reports={reports} stats={stats} />

          {/* Database + Export */}
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Database stats={stats} />
            <Export reports={reports} />
          </section>

          {/* Historical record */}
          <ReportHistory reports={reports} />
        </>
      )}
    </div>
  );
}

export default Reports;