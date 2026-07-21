/**
 * api.js
 *
 * Centralized REST Communication Service — Lavender Trinetra Platform
 * =====================================================================
 *
 * The single REST HTTP client for the entire frontend. Every page and
 * component that needs data from the FastAPI backend imports named
 * functions from this file rather than calling axios/fetch directly —
 * this is the only module in the frontend that constructs HTTP
 * requests. Real-time/streaming data is handled exclusively by
 * services/websocket.js; this file never opens a socket.
 *
 * Contains no business logic — every function is a thin, typed wrapper
 * around one backend endpoint that returns already-unwrapped response
 * data (or throws a normalized error for the caller to handle).
 *
 * Compatible with:
 *   - context/SystemStatusContext.jsx (getSystemStatus, getDashboardStatistics)
 *   - pages/Dashboard.jsx
 *   - pages/Monitoring.jsx + monitoring/*.jsx
 *   - pages/AIWorkspace.jsx + ai/*.jsx
 *   - pages/Cybersecurity.jsx + cybersecurity/*.jsx
 *   - pages/Reports.jsx + reports/*.jsx
 */

import axios from "axios";

// =====================================================================
// CONFIGURATION
// =====================================================================

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 15000;

const logger = {
  error: (...args) => console.error("[api]", ...args),
};

// =====================================================================
// AXIOS INSTANCE
// =====================================================================

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * Centralized error normalization. Logs for diagnostics and rejects
 * with a consistent shape ({ message, status, data }) so every caller
 * can handle failures the same way, without duplicating parsing logic
 * across pages/components.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? null;
    const data = error.response?.data ?? null;
    const message =
      data?.detail || data?.message || error.message || "Unknown API error";

    logger.error(`${error.config?.method?.toUpperCase() ?? "REQUEST"} ${error.config?.url} failed:`, message);

    return Promise.reject({ message, status, data });
  }
);

function buildParams(params = {}) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null)
  );
}

// =====================================================================
// SYSTEM STATUS / DASHBOARD
// =====================================================================

/**
 * getSystemStatus — current liveness of core subsystems (AI engine,
 * database, API, monitoring session, security). Primary REST source
 * for context/SystemStatusContext.jsx on initial load; live updates
 * thereafter arrive via services/websocket.js (CHANNELS.SYSTEM_STATUS).
 */
export async function getSystemStatus() {
  const { data } = await apiClient.get("/system/status");
  return data;
}

/** getDashboardStatistics — aggregate cross-session dashboard metrics. */
export async function getDashboardStatistics() {
  const { data } = await apiClient.get("/dashboard/statistics");
  return data;
}

// =====================================================================
// MONITORING
// =====================================================================

/** getLatestMetrics — most recent system metric samples, newest last. */
export async function getLatestMetrics({ limit = 60 } = {}) {
  const { data } = await apiClient.get("/monitoring/metrics/latest", {
    params: buildParams({ limit }),
  });
  return data;
}

/** getLatestProcesses — most recent top-process snapshot. */
export async function getLatestProcesses({ limit = 5 } = {}) {
  const { data } = await apiClient.get("/monitoring/processes/latest", {
    params: buildParams({ limit }),
  });
  return data;
}

/** startMonitoring — begin a new monitoring session (creates a TestRun). */
export async function startMonitoring() {
  const { data } = await apiClient.post("/monitoring/start");
  return data;
}

/** stopMonitoring — end the active monitoring session and generate its report. */
export async function stopMonitoring() {
  const { data } = await apiClient.post("/monitoring/stop");
  return data;
}

/** resetMonitoringSession — clear in-memory alert counters for the current session. */
export async function resetMonitoringSession() {
  const { data } = await apiClient.post("/monitoring/reset");
  return data;
}

/** refreshMetrics — trigger an immediate out-of-cycle metrics collection. */
export async function refreshMetrics() {
  const { data } = await apiClient.post("/monitoring/refresh");
  return data;
}

// =====================================================================
// AI WORKSPACE
// =====================================================================

/** getLatestAIResult — most recent unified AI orchestration cycle result. */
export async function getLatestAIResult() {
  const { data } = await apiClient.get("/ai/results/latest");
  return data;
}

/** getAIResults — recent AI orchestration cycle results, newest first. */
export async function getAIResults({ limit = 20 } = {}) {
  const { data } = await apiClient.get("/ai/results", {
    params: buildParams({ limit }),
  });
  return data;
}

// =====================================================================
// CYBERSECURITY
// =====================================================================

/** getOverallSecurityStatus — cybersecurity engine + component status. */
export async function getOverallSecurityStatus() {
  const { data } = await apiClient.get("/cybersecurity/status");
  return data;
}

/** getProcessSecurityEvents — process-level security observations. */
export async function getProcessSecurityEvents() {
  const { data } = await apiClient.get("/cybersecurity/processes");
  return data;
}

/** getNetworkSecurityEvents — network connection and traffic-rate events. */
export async function getNetworkSecurityEvents() {
  const { data } = await apiClient.get("/cybersecurity/network");
  return data;
}

/** getPortSecurityEvents — listening-port observations and change events. */
export async function getPortSecurityEvents() {
  const { data } = await apiClient.get("/cybersecurity/ports");
  return data;
}

/** getFirewallStatus — firewall status snapshot and change events. */
export async function getFirewallStatus() {
  const { data } = await apiClient.get("/cybersecurity/firewall");
  return data;
}

/** getActiveSessions — active user session observations and login/logout events. */
export async function getActiveSessions() {
  const { data } = await apiClient.get("/cybersecurity/sessions");
  return data;
}

/**
 * getRecentFirewallEvents — same underlying data as getFirewallStatus
 * (firewall_monitor.py returns one combined list: current status
 * snapshot plus any change events this cycle); exposed under both
 * names since Firewall.jsx fetches status and recent events separately.
 */
export async function getRecentFirewallEvents() {
  const { data } = await apiClient.get("/cybersecurity/firewall");
  return data;
}

/** getListeningPorts — same underlying data as getPortSecurityEvents, filtered client-side by Ports.jsx. */
export async function getListeningPorts() {
  const { data } = await apiClient.get("/cybersecurity/ports");
  return data;
}

/** getSuspiciousPorts — same underlying data as getPortSecurityEvents, filtered client-side by Ports.jsx. */
export async function getSuspiciousPorts() {
  const { data } = await apiClient.get("/cybersecurity/ports");
  return data;
}

/** getRecentPortEvents — same underlying data as getPortSecurityEvents, filtered client-side by Ports.jsx. */
export async function getRecentPortEvents() {
  const { data } = await apiClient.get("/cybersecurity/ports");
  return data;
}

// =====================================================================
// CYBERSECURITY - THREAT DETECTION (threat_detector.py)
// =====================================================================

/** getThreatSummary — counts of recent threats by severity. */
export async function getThreatSummary() {
  const { data } = await apiClient.get("/cybersecurity/threats/summary");
  return data;
}

/** getActiveThreats — recent threats at or above the given severity ("Low"|"Medium"|"High"|"Critical"). */
export async function getActiveThreats(minSeverity = "Medium") {
  const { data } = await apiClient.get("/cybersecurity/threats/active", {
    params: buildParams({ min_severity: minSeverity }),
  });
  return data;
}

/** getRecentThreats — most recent threats, newest first. */
export async function getRecentThreats(limit = 100) {
  const { data } = await apiClient.get("/cybersecurity/threats/recent", {
    params: buildParams({ limit }),
  });
  return data;
}

// =====================================================================
// CYBERSECURITY - INTRUSION DETECTION (intrusion_detection.py)
// =====================================================================

/** getRecentIntrusions — most recent intrusion alerts, newest first. */
export async function getRecentIntrusions(limit = 100) {
  const { data } = await apiClient.get("/cybersecurity/intrusions", {
    params: buildParams({ limit }),
  });
  return data;
}

// =====================================================================
// CYBERSECURITY - VULNERABILITY SCAN (vulnerability_scan.py)
// =====================================================================

/** getRecentVulnerabilities — most recent vulnerability findings, newest first. */
export async function getRecentVulnerabilities(limit = 100) {
  const { data } = await apiClient.get("/cybersecurity/vulnerabilities", {
    params: buildParams({ limit }),
  });
  return data;
}

/** getVulnerabilitySummary — counts of recent vulnerability findings by severity. */
export async function getVulnerabilitySummary() {
  const { data } = await apiClient.get("/cybersecurity/vulnerabilities/summary");
  return data;
}

// =====================================================================
// CYBERSECURITY - EXPLAINABLE AI SECURITY SCORE
// (security_score.py, threat_classifier.py, attack_patterns.py,
// security_recommendations.py) — sole data source for SecurityScore.jsx.
// =====================================================================

/** getSecurityScore — latest explainable security score, grade and factor breakdown. */
export async function getSecurityScore() {
  const { data } = await apiClient.get("/cybersecurity/score");
  return data;
}

/** getSecurityScoreHistory — recent security score history, newest first. */
export async function getSecurityScoreHistory({ limit = 100 } = {}) {
  const { data } = await apiClient.get("/cybersecurity/score/history", {
    params: buildParams({ limit }),
  });
  return data;
}

/** getThreatClassificationSummary — counts of recent threat classifications by category. */
export async function getThreatClassificationSummary() {
  const { data } = await apiClient.get("/cybersecurity/classifications/summary");
  return data;
}

/** getThreatClassifications — most recent individual threat classifications, newest first. */
export async function getThreatClassifications({ limit = 100 } = {}) {
  const { data } = await apiClient.get("/cybersecurity/classifications", {
    params: buildParams({ limit }),
  });
  return data;
}

/** getAttackPatternSummary — counts of recent correlated attack patterns by severity/category. */
export async function getAttackPatternSummary() {
  const { data } = await apiClient.get("/cybersecurity/attack-patterns/summary");
  return data;
}

/** getRecentAttackPatterns — most recent correlated attack patterns, newest first. */
export async function getRecentAttackPatterns({ limit = 100 } = {}) {
  const { data } = await apiClient.get("/cybersecurity/attack-patterns/recent", {
    params: buildParams({ limit }),
  });
  return data;
}

/** getSecurityRecommendations — live, prioritized, explainable security recommendations. */
export async function getSecurityRecommendations({ limit = 100 } = {}) {
  const { data } = await apiClient.get("/cybersecurity/recommendations/live", {
    params: buildParams({ limit }),
  });
  return data;
}

// =====================================================================
// REPORTS
// =====================================================================

/** getReports — completed monitoring session reports, newest first. */
export async function getReports({ limit = 50 } = {}) {
  const { data } = await apiClient.get("/reports", {
    params: buildParams({ limit }),
  });
  return data;
}

// =====================================================================
// EXPORT
// =====================================================================

export default {
  getSystemStatus,
  getDashboardStatistics,
  getLatestMetrics,
  getLatestProcesses,
  startMonitoring,
  stopMonitoring,
  resetMonitoringSession,
  refreshMetrics,
  getLatestAIResult,
  getAIResults,
  getOverallSecurityStatus,
  getProcessSecurityEvents,
  getNetworkSecurityEvents,
  getPortSecurityEvents,
  getFirewallStatus,
  getActiveSessions,
  getRecentFirewallEvents,
  getListeningPorts,
  getSuspiciousPorts,
  getRecentPortEvents,
  getThreatSummary,
  getActiveThreats,
  getRecentThreats,
  getRecentIntrusions,
  getRecentVulnerabilities,
  getVulnerabilitySummary,
  getSecurityScore,
  getSecurityScoreHistory,
  getThreatClassificationSummary,
  getThreatClassifications,
  getAttackPatternSummary,
  getRecentAttackPatterns,
  getSecurityRecommendations,
  getReports,
};