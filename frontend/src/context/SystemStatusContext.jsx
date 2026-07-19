import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getSystemStatus, getDashboardStatistics } from "../services/api.js";

const REFRESH_INTERVAL_MS = 15000;

/**
 * Default/idle shape of the status slice distributed to every consumer
 * (Sidebar, Topbar, Dashboard, Monitoring, AIWorkspace, Cybersecurity,
 * Reports, Settings). Field names are intentionally stable so
 * consumers can destructure `status` without null-checking every key.
 */
const INITIAL_STATUS = {
  aiEngine: "offline",
  database: "offline",
  api: "offline",
  monitoring: "offline",
  security: "unknown",
  currentTestRun: null,
  activeAlertsCount: 0,
  aiHealthScore: null,
  currentWorkspace: "dashboard",
  lastUpdated: null,
};

const SystemStatusContext = createContext(undefined);

/**
 * normalizeStatusPayload — maps the backend's SystemStatusResponse
 * (backend/api/schemas.py: { api, ai, monitoring, database }) plus the
 * optional dashboard statistics aggregate (database/crud.py::
 * get_dashboard_statistics) onto this context's stable field names.
 * Pure data reshaping only — no status evaluation or business logic.
 */
function normalizeStatusPayload(statusResponse, statsResponse, previousWorkspace) {
  return {
    aiEngine: statusResponse?.ai ?? "unknown",
    database: statusResponse?.database ?? "unknown",
    api: statusResponse?.api ?? "unknown",
    monitoring: statusResponse?.monitoring ?? "unknown",
    security: statusResponse?.security ?? statusResponse?.cybersecurity ?? "unknown",
    currentTestRun: statsResponse?.latest_run ?? null,
    activeAlertsCount: statsResponse?.total_alerts ?? 0,
    aiHealthScore: statsResponse?.latest_health_score ?? null,
    currentWorkspace: previousWorkspace ?? INITIAL_STATUS.currentWorkspace,
    lastUpdated: new Date().toISOString(),
  };
}

/**
 * SystemStatusProvider — the single source of truth for
 * application-wide system status. Wraps the app (via App.jsx) and
 * centrally manages AI engine / database / API / monitoring /
 * cybersecurity status, the active test run, active alert count, AI
 * health score, the current workspace, and loading/error/timestamp
 * state. All data is retrieved exclusively through services/api.js —
 * this provider never talks to the backend directly and contains no
 * business logic (no threshold evaluation, no scoring, no alerting).
 *
 * WebSocket-ready: `wsRef` and `isRealtimeConnected` are reserved for
 * a future live-push status channel. When implemented, incoming
 * WebSocket frames should be normalized through the same
 * `normalizeStatusPayload` shape and applied via `updateStatus` so
 * every consumer keeps working unchanged.
 */
export function SystemStatusProvider({ children }) {
  const [status, setStatus] = useState(INITIAL_STATUS);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Reserved for future WebSocket support — intentionally unused today.
  const wsRef = useRef(null);
  const [isRealtimeConnected, setIsRealtimeConnected] = useState(false);

  const isMountedRef = useRef(true);
  const currentWorkspaceRef = useRef(INITIAL_STATUS.currentWorkspace);

  /**
   * refreshStatus — fetches the latest status + statistics through
   * services/api.js and merges the normalized result into state.
   * Fetches run independently (Promise.allSettled) so a failure in
   * one endpoint doesn't blank out data from the other.
   */
  const refreshStatus = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setIsLoading(true);

    const [statusResult, statsResult] = await Promise.allSettled([
      getSystemStatus(),
      getDashboardStatistics(),
    ]);

    if (!isMountedRef.current) return;

    const statusResponse = statusResult.status === "fulfilled" ? statusResult.value : null;
    const statsResponse = statsResult.status === "fulfilled" ? statsResult.value : null;

    if (statusResult.status === "rejected" && statsResult.status === "rejected") {
      setError(
        statusResult.reason?.message ||
          statsResult.reason?.message ||
          "Failed to refresh system status."
      );
    } else {
      setError(null);
    }

    setStatus((prev) =>
      normalizeStatusPayload(statusResponse, statsResponse, currentWorkspaceRef.current ?? prev.currentWorkspace)
    );
    setIsLoading(false);
  }, []);

  /**
   * updateStatus — applies a partial status patch without a network
   * round-trip. Intended for future WebSocket push updates or
   * optimistic UI updates from other components.
   */
  const updateStatus = useCallback((patch) => {
    setStatus((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
      lastUpdated: new Date().toISOString(),
    }));
  }, []);

  /**
   * resetStatus — restores the context to its initial idle shape.
   * Useful for logout flows or hard resets without a full page reload.
   */
  const resetStatus = useCallback(() => {
    setStatus(INITIAL_STATUS);
    currentWorkspaceRef.current = INITIAL_STATUS.currentWorkspace;
    setError(null);
    setIsLoading(false);
  }, []);

  /**
   * updateWorkspace — records which top-level workspace (dashboard,
   * monitoring, ai-workspace, cybersecurity, reports, settings) is
   * currently active, for consumers like Topbar/Sidebar that display
   * workspace-aware UI.
   */
  const updateWorkspace = useCallback((workspace) => {
    currentWorkspaceRef.current = workspace;
    setStatus((prev) => ({ ...prev, currentWorkspace: workspace }));
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    refreshStatus();

    const intervalId = setInterval(() => refreshStatus({ silent: true }), REFRESH_INTERVAL_MS);

    return () => {
      isMountedRef.current = false;
      clearInterval(intervalId);
      // Future: tear down the WebSocket connection here (wsRef.current?.close()).
    };
  }, [refreshStatus]);

  const value = useMemo(
    () => ({
      status,
      isLoading,
      error,
      isRealtimeConnected,
      refreshStatus,
      updateStatus,
      resetStatus,
      updateWorkspace,
    }),
    [status, isLoading, error, isRealtimeConnected, refreshStatus, updateStatus, resetStatus, updateWorkspace]
  );

  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}

/**
 * useSystemStatus — the single hook every consumer (Sidebar, Topbar,
 * Dashboard, Monitoring, AIWorkspace, Cybersecurity, Reports,
 * Settings) uses to read and interact with global system status.
 * Throws if used outside SystemStatusProvider so misconfiguration
 * fails fast during development.
 */
export function useSystemStatus() {
  const context = useContext(SystemStatusContext);
  if (context === undefined) {
    throw new Error("useSystemStatus must be used within a SystemStatusProvider");
  }
  return context;
}

export default SystemStatusContext;