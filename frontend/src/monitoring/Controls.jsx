import { useState } from "react";
import toast from "react-hot-toast";
import {
  PiPlayBold,
  PiStopBold,
  PiArrowCounterClockwiseBold,
  PiArrowsClockwiseBold,
  PiPulseBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

import {
  startMonitoring,
  stopMonitoring,
  resetMonitoringSession,
  refreshMetrics,
} from "../services/api.js";

const ACTIONS = {
  START: "start",
  STOP: "stop",
  RESET: "reset",
  REFRESH: "refresh",
};

/**
 * Controls — monitoring control panel. Dispatches Start/Stop/Reset/
 * Refresh actions to the backend via services/api.js and reflects the
 * current monitoring status passed down from Monitoring.jsx. Contains
 * no monitoring logic itself — collection, session lifecycle, and
 * report generation are entirely owned by the backend (main.py,
 * monitoring/*.py).
 *
 * Props:
 *   isMonitoringActive (bool) — current monitoring session state.
 */
function Controls({ isMonitoringActive = false }) {
  const [pendingAction, setPendingAction] = useState(null);

  const runAction = async (action, apiCall, { successMessage, confirmMessage } = {}) => {
    if (confirmMessage && !window.confirm(confirmMessage)) return;

    setPendingAction(action);
    try {
      await apiCall();
      toast.success(successMessage || "Action completed.");
    } catch {
      toast.error("Action failed. Please try again.");
    } finally {
      setPendingAction(null);
    }
  };

  const handleStart = () =>
    runAction(ACTIONS.START, startMonitoring, { successMessage: "Monitoring started." });

  const handleStop = () =>
    runAction(ACTIONS.STOP, stopMonitoring, { successMessage: "Monitoring stopped. Report generated." });

  const handleReset = () =>
    runAction(ACTIONS.RESET, resetMonitoringSession, {
      successMessage: "Session reset.",
      confirmMessage: "Reset the current monitoring session? This clears in-memory alert counters.",
    });

  const handleRefresh = () =>
    runAction(ACTIONS.REFRESH, refreshMetrics, { successMessage: "Metrics refreshed." });

  const isPending = (action) => pendingAction === action;
  const isAnyPending = pendingAction !== null;

  return (
    <Card title="Monitoring Controls" icon={PiPulseBold}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--color-text-secondary,#94a3b8)]">Status:</span>
          <StatusBadge status={isMonitoringActive ? "online" : "offline"} />
        </div>

        <div className="flex flex-wrap gap-2">
          <ControlButton
            label="Start Monitoring"
            icon={PiPlayBold}
            onClick={handleStart}
            disabled={isMonitoringActive || isAnyPending}
            isLoading={isPending(ACTIONS.START)}
            variant="primary"
          />
          <ControlButton
            label="Stop Monitoring"
            icon={PiStopBold}
            onClick={handleStop}
            disabled={!isMonitoringActive || isAnyPending}
            isLoading={isPending(ACTIONS.STOP)}
            variant="danger"
          />
          <ControlButton
            label="Reset Session"
            icon={PiArrowCounterClockwiseBold}
            onClick={handleReset}
            disabled={isMonitoringActive || isAnyPending}
            isLoading={isPending(ACTIONS.RESET)}
            variant="secondary"
          />
          <ControlButton
            label="Refresh Metrics"
            icon={PiArrowsClockwiseBold}
            onClick={handleRefresh}
            disabled={isAnyPending}
            isLoading={isPending(ACTIONS.REFRESH)}
            variant="secondary"
          />
        </div>
      </div>
    </Card>
  );
}

const VARIANT_CLASSES = {
  primary:
    "bg-violet-600 text-white hover:bg-violet-500 disabled:hover:bg-violet-600",
  danger:
    "bg-rose-600/15 text-rose-300 hover:bg-rose-600/25 disabled:hover:bg-rose-600/15",
  secondary:
    "bg-white/5 text-[var(--color-text-primary,#f1f5f9)] hover:bg-white/10 disabled:hover:bg-white/5",
};

function ControlButton({ label, icon: Icon, onClick, disabled, isLoading, variant }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${VARIANT_CLASSES[variant]}`}
    >
      {isLoading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <Icon className="h-4 w-4" />
      )}
      {label}
    </button>
  );
}

export default Controls;