import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import toast from "react-hot-toast";
import {
  PiBugBold,
  PiClockBold,
  PiArrowsClockwiseBold,
  PiNotePencilBold,
  PiLightbulbBold,
  PiTagBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Loader from "../components/Loader.jsx";

import { getRecentVulnerabilities, getVulnerabilitySummary } from "../services/api.js";

const REFRESH_INTERVAL_MS = 20000;
const FINDINGS_LIMIT = 100;

const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function formatCategory(category) {
  if (!category) return null;
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Vulnerabilities — displays local vulnerability scan findings for
 * the Cybersecurity workspace: severity, description, an explainable
 * recommended action, and scan time for each finding. Sourced
 * entirely from vulnerability_scan.py via services/api.js. Purely
 * presentational — implements no vulnerability assessment or scoring
 * logic of its own.
 */
function Vulnerabilities() {
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);

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
        getRecentVulnerabilities(FINDINGS_LIMIT),
        getVulnerabilitySummary(),
      ]);
      if (!isMountedRef.current) return;

      const [findingsRes, summaryRes] = results;
      if (findingsRes.status === "fulfilled") setFindings(findingsRes.value || []);
      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);

      if (results.some((r) => r.status === "rejected")) {
        setError("Some vulnerability data could not be loaded.");
        if (!silent) toast.error("Some vulnerability data could not be loaded.");
      } else {
        setError(null);
      }
      setLastFetched(new Date());
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(err?.message || "Failed to load vulnerability findings.");
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

  const sortedFindings = useMemo(() => {
    return [...findings].sort((a, b) => {
      const severityDiff =
        (SEVERITY_RANK[String(a.severity).toLowerCase()] ?? 9) -
        (SEVERITY_RANK[String(b.severity).toLowerCase()] ?? 9);
      if (severityDiff !== 0) return severityDiff;
      return new Date(b.timestamp || 0) - new Date(a.timestamp || 0);
    });
  }, [findings]);

  const severityCounts = summary?.severity_counts || {};

  if (isLoading) {
    return (
      <Card title="Vulnerabilities" icon={PiBugBold}>
        <div className="flex justify-center py-10">
          <Loader label="Loading vulnerability findings..." />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header / summary / refresh */}
      <Card title="Vulnerabilities" icon={PiBugBold}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-3xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
              {summary?.total ?? sortedFindings.length}
            </p>
            <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">
              vulnerability finding(s) identified
            </p>
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
              Last scan {formatTimestamp(summary?.generated_at || lastFetched)}
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

        {Object.keys(severityCounts).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(severityCounts).map(([level, count]) => (
              <span key={level} className="flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-1 text-xs">
                <StatusBadge status={level} size="sm" showLabel={false} />
                <span className="text-[var(--color-text-primary,#f1f5f9)]">{level}</span>
                <span className="text-[var(--color-text-secondary,#64748b)]">{count}</span>
              </span>
            ))}
          </div>
        )}

        {error && (
          <p className="mt-3 text-xs text-rose-400">{error} — showing last known data.</p>
        )}
      </Card>

      {sortedFindings.length === 0 ? (
        <Card>
          <p className="text-sm text-[var(--color-text-secondary,#64748b)]">
            No vulnerabilities found. Firewall, ports, services, and configuration all passed
            the most recent scan.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {sortedFindings.map((finding) => (
            <div
              key={finding.finding_id}
              className="rounded-xl border border-[var(--color-border,#232733)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <StatusBadge status={finding.severity || "unknown"} />
                  {finding.category && (
                    <span className="flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-text-secondary,#94a3b8)]">
                      <PiTagBold className="h-3 w-3" />
                      {formatCategory(finding.category)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
                  <PiClockBold className="h-3.5 w-3.5" />
                  {formatTimestamp(finding.timestamp)}
                </div>
              </div>

              <h3 className="mt-3 text-base font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                {finding.title}
              </h3>
              {finding.affected_asset && (
                <p className="mt-0.5 text-xs text-[var(--color-text-secondary,#64748b)]">
                  Affected: {finding.affected_asset}
                </p>
              )}

              {finding.description && (
                <div className="mt-3 flex items-start gap-2 rounded-lg bg-black/20 p-3">
                  <PiNotePencilBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-text-secondary,#64748b)]" />
                  <div>
                    <p className="text-xs font-medium text-[var(--color-text-secondary,#64748b)]">
                      Description
                    </p>
                    <p className="mt-0.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                      {finding.description}
                    </p>
                  </div>
                </div>
              )}

              {finding.recommendation && (
                <div className="mt-2 flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <PiLightbulbBold className="mt-0.5 h-4 w-4 flex-shrink-0 text-emerald-400" />
                  <div>
                    <p className="text-xs font-medium text-emerald-300">Recommended Action</p>
                    <p className="mt-0.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                      {finding.recommendation}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Vulnerabilities;