import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  PiBellRingingBold,
  PiCpuBold,
  PiMemoryBold,
  PiHardDriveBold,
  PiWifiHighBold,
  PiWarningCircleBold,
  PiClockBold,
  PiFloppyDiskBold,
  PiArrowCounterClockwiseBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import Loader from "../components/Loader.jsx";
import { getAlertPolicy, updateAlertPolicy } from "../services/api.js";

const DEFAULT_POLICY = {
  cpu_threshold: 85,
  ram_threshold: 85,
  disk_threshold: 90,
  network_threshold: 100,
  severity_levels: {
    Low: true,
    Medium: true,
    High: true,
    Critical: true,
  },
  alert_frequency: "immediate",
  alerts_enabled: true,
};

const FREQUENCY_OPTIONS = [
  { value: "immediate", label: "Immediate" },
  { value: "5min", label: "Every 5 Minutes" },
  { value: "15min", label: "Every 15 Minutes" },
  { value: "hourly", label: "Hourly" },
  { value: "daily", label: "Daily Digest" },
];

const SEVERITY_KEYS = ["Low", "Medium", "High", "Critical"];

function ToggleSwitch({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 flex-shrink-0 rounded-full transition-colors ${
        checked ? "bg-violet-500" : "bg-[var(--color-border,#232733)]"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

function ThresholdField({ icon: Icon, label, value, unit, onChange, disabled }) {
  return (
    <div>
      <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </label>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-[var(--color-border,#232733)] accent-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            max={100}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(Math.min(100, Math.max(0, Number(e.target.value))))}
            className="w-16 rounded-md border border-[var(--color-border,#232733)] bg-transparent px-2 py-1 text-right text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <span className="text-xs text-[var(--color-text-secondary,#64748b)]">{unit}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * AlertPolicy — the alert policy configuration panel. Loads the
 * current threshold/severity/frequency configuration from the
 * backend (mirroring backend/config.py's CPU_THRESHOLD,
 * RAM_THRESHOLD, NETWORK_THRESHOLD, etc.) via services/api.js, lets
 * the user edit it locally, and persists changes back through
 * services/api.js. Implements no alerting, threshold evaluation, or
 * notification logic itself — that lives entirely in the backend
 * (config.py::generate_alert and monitoring/alerts.py).
 */
function AlertPolicy() {
  const [policy, setPolicy] = useState(DEFAULT_POLICY);
  const [savedPolicy, setSavedPolicy] = useState(DEFAULT_POLICY);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    async function loadPolicy() {
      setIsLoading(true);
      try {
        const data = await getAlertPolicy();
        if (!isMountedRef.current) return;
        const merged = {
          ...DEFAULT_POLICY,
          ...data,
          severity_levels: { ...DEFAULT_POLICY.severity_levels, ...(data?.severity_levels || {}) },
        };
        setPolicy(merged);
        setSavedPolicy(merged);
        setError(null);
      } catch (err) {
        if (!isMountedRef.current) return;
        setError(err?.message || "Failed to load alert policy. Showing defaults.");
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    }

    loadPolicy();
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const updateField = (key, value) => {
    setPolicy((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSeverity = (level) => {
    setPolicy((prev) => ({
      ...prev,
      severity_levels: { ...prev.severity_levels, [level]: !prev.severity_levels[level] },
    }));
  };

  const hasChanges = JSON.stringify(policy) !== JSON.stringify(savedPolicy);

  const handleReset = () => {
    setPolicy(savedPolicy);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const result = await updateAlertPolicy(policy);
      const merged = {
        ...DEFAULT_POLICY,
        ...policy,
        ...(result || {}),
      };
      setPolicy(merged);
      setSavedPolicy(merged);
      toast.success("Alert policy saved.");
    } catch (err) {
      toast.error(err?.message || "Failed to save alert policy.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader label="Loading alert policy..." />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          <PiBellRingingBold className="h-5 w-5 text-violet-400" />
          Alert Policy
        </h3>

        <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary,#94a3b8)]">
          <span>{policy.alerts_enabled ? "Alerts Enabled" : "Alerts Disabled"}</span>
          <ToggleSwitch
            checked={policy.alerts_enabled}
            onChange={(v) => updateField("alerts_enabled", v)}
          />
        </label>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      {/* Thresholds */}
      <Card title="Resource Thresholds">
        <fieldset disabled={!policy.alerts_enabled} className="flex flex-col gap-5">
          <ThresholdField
            icon={PiCpuBold}
            label="CPU Threshold"
            value={policy.cpu_threshold}
            unit="%"
            onChange={(v) => updateField("cpu_threshold", v)}
            disabled={!policy.alerts_enabled}
          />
          <ThresholdField
            icon={PiMemoryBold}
            label="RAM Threshold"
            value={policy.ram_threshold}
            unit="%"
            onChange={(v) => updateField("ram_threshold", v)}
            disabled={!policy.alerts_enabled}
          />
          <ThresholdField
            icon={PiHardDriveBold}
            label="Disk Threshold"
            value={policy.disk_threshold}
            unit="%"
            onChange={(v) => updateField("disk_threshold", v)}
            disabled={!policy.alerts_enabled}
          />
          <ThresholdField
            icon={PiWifiHighBold}
            label="Network Threshold"
            value={policy.network_threshold}
            unit="MB"
            onChange={(v) => updateField("network_threshold", v)}
            disabled={!policy.alerts_enabled}
          />
        </fieldset>
      </Card>

      {/* Severity levels */}
      <Card title="Alert Severity Levels">
        <div className="flex flex-wrap gap-3">
          {SEVERITY_KEYS.map((level) => (
            <label
              key={level}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                policy.severity_levels[level]
                  ? "border-violet-500/40 bg-violet-500/10 text-[var(--color-text-primary,#f1f5f9)]"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#64748b)]"
              } ${!policy.alerts_enabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
            >
              <input
                type="checkbox"
                checked={Boolean(policy.severity_levels[level])}
                disabled={!policy.alerts_enabled}
                onChange={() => toggleSeverity(level)}
                className="h-3.5 w-3.5 accent-violet-500"
              />
              <PiWarningCircleBold className="h-3.5 w-3.5" />
              {level}
            </label>
          ))}
        </div>
      </Card>

      {/* Frequency */}
      <Card title="Alert Frequency">
        <label className="flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
          <PiClockBold className="h-3.5 w-3.5" />
          How often alerts should be dispatched
        </label>
        <select
          value={policy.alert_frequency}
          disabled={!policy.alerts_enabled}
          onChange={(e) => updateField("alert_frequency", e.target.value)}
          className="mt-2 w-full max-w-xs rounded-md border border-[var(--color-border,#232733)] bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {FREQUENCY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[var(--color-bg,#0f1115)]">
              {opt.label}
            </option>
          ))}
        </select>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border,#232733)] pt-4">
        <button
          type="button"
          onClick={handleReset}
          disabled={!hasChanges || isSaving}
          className="flex items-center gap-1.5 rounded-md border border-[var(--color-border,#232733)] px-3 py-1.5 text-sm font-medium text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <PiArrowCounterClockwiseBold className="h-3.5 w-3.5" />
          Reset
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!hasChanges || isSaving}
          className="flex items-center gap-1.5 rounded-md bg-violet-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSaving ? (
            <PiArrowCounterClockwiseBold className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <PiFloppyDiskBold className="h-3.5 w-3.5" />
          )}
          {isSaving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}

export default AlertPolicy;