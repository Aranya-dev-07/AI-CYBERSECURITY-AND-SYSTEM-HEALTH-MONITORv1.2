import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  PiSlidersHorizontalBold,
  PiTimerBold,
  PiArrowsClockwiseBold,
  PiGaugeBold,
  PiHouseBold,
  PiBellBold,
  PiClockBold,
  PiFloppyDiskBold,
  PiArrowCounterClockwiseBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import Loader from "../components/Loader.jsx";
import { getPreferences, updatePreferences } from "../services/api.js";

const DEFAULT_PREFERENCES = {
  monitoring_interval: 5,
  auto_refresh: true,
  dashboard_refresh_rate: 5,
  default_landing_page: "dashboard",
  time_format: "24h",
  notifications: {
    critical_alerts: true,
    high_alerts: true,
    medium_alerts: false,
    low_alerts: false,
    email_notifications: false,
    desktop_notifications: true,
  },
};

const LANDING_PAGE_OPTIONS = [
  { value: "dashboard", label: "Dashboard" },
  { value: "monitoring", label: "Monitoring" },
  { value: "ai", label: "AI Workspace" },
  { value: "cybersecurity", label: "Cybersecurity" },
  { value: "reports", label: "Reports" },
];

const MONITORING_INTERVAL_OPTIONS = [1, 5, 10, 15, 30, 60];
const REFRESH_RATE_OPTIONS = [2, 5, 10, 15, 30, 60];

const TIME_FORMAT_OPTIONS = [
  { value: "24h", label: "24-Hour (14:30)" },
  { value: "12h", label: "12-Hour (2:30 PM)" },
];

const NOTIFICATION_TOGGLES = [
  { key: "critical_alerts", label: "Critical Alerts" },
  { key: "high_alerts", label: "High Severity Alerts" },
  { key: "medium_alerts", label: "Medium Severity Alerts" },
  { key: "low_alerts", label: "Low Severity Alerts" },
  { key: "email_notifications", label: "Email Notifications" },
  { key: "desktop_notifications", label: "Desktop Notifications" },
];

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

/**
 * Preferences — the user preferences panel. Loads the current
 * monitoring/refresh/notification/display preferences from the
 * backend via services/api.js, lets the user edit them locally, and
 * persists changes back through services/api.js. Implements no
 * monitoring, refresh, or notification dispatch logic itself — those
 * live in the backend (config.py::MONITOR_INTERVAL and the monitoring
 * engine) and in the frontend components that consume these settings.
 */
function Preferences() {
  const [prefs, setPrefs] = useState(DEFAULT_PREFERENCES);
  const [savedPrefs, setSavedPrefs] = useState(DEFAULT_PREFERENCES);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    async function loadPreferences() {
      setIsLoading(true);
      try {
        const data = await getPreferences();
        if (!isMountedRef.current) return;
        const merged = {
          ...DEFAULT_PREFERENCES,
          ...data,
          notifications: { ...DEFAULT_PREFERENCES.notifications, ...(data?.notifications || {}) },
        };
        setPrefs(merged);
        setSavedPrefs(merged);
        setError(null);
      } catch (err) {
        if (!isMountedRef.current) return;
        setError(err?.message || "Failed to load preferences. Showing defaults.");
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    }

    loadPreferences();
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const updateField = (key, value) => {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  };

  const toggleNotification = (key) => {
    setPrefs((prev) => ({
      ...prev,
      notifications: { ...prev.notifications, [key]: !prev.notifications[key] },
    }));
  };

  const hasChanges = JSON.stringify(prefs) !== JSON.stringify(savedPrefs);

  const handleReset = () => {
    setPrefs(savedPrefs);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const result = await updatePreferences(prefs);
      const merged = {
        ...DEFAULT_PREFERENCES,
        ...prefs,
        ...(result || {}),
      };
      setPrefs(merged);
      setSavedPrefs(merged);
      toast.success("Preferences saved.");
    } catch (err) {
      toast.error(err?.message || "Failed to save preferences.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader label="Loading preferences..." />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
        <PiSlidersHorizontalBold className="h-5 w-5 text-violet-400" />
        Preferences
      </h3>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      {/* Monitoring & refresh */}
      <Card title="Monitoring & Refresh">
        <div className="flex flex-col gap-5">
          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
              <PiTimerBold className="h-3.5 w-3.5" />
              Monitoring Interval
            </label>
            <select
              value={prefs.monitoring_interval}
              onChange={(e) => updateField("monitoring_interval", Number(e.target.value))}
              className="w-full max-w-xs rounded-md border border-[var(--color-border,#232733)] bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500 sm:w-auto"
            >
              {MONITORING_INTERVAL_OPTIONS.map((seconds) => (
                <option key={seconds} value={seconds} className="bg-[var(--color-bg,#0f1115)]">
                  Every {seconds}s
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
              <PiArrowsClockwiseBold className="h-3.5 w-3.5" />
              Auto Refresh
            </label>
            <ToggleSwitch
              checked={prefs.auto_refresh}
              onChange={(v) => updateField("auto_refresh", v)}
            />
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
              <PiGaugeBold className="h-3.5 w-3.5" />
              Dashboard Refresh Rate
            </label>
            <select
              value={prefs.dashboard_refresh_rate}
              disabled={!prefs.auto_refresh}
              onChange={(e) => updateField("dashboard_refresh_rate", Number(e.target.value))}
              className="w-full max-w-xs rounded-md border border-[var(--color-border,#232733)] bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {REFRESH_RATE_OPTIONS.map((seconds) => (
                <option key={seconds} value={seconds} className="bg-[var(--color-bg,#0f1115)]">
                  Every {seconds}s
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Display */}
      <Card title="Display">
        <div className="flex flex-col gap-5">
          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
              <PiHouseBold className="h-3.5 w-3.5" />
              Default Landing Page
            </label>
            <select
              value={prefs.default_landing_page}
              onChange={(e) => updateField("default_landing_page", e.target.value)}
              className="w-full max-w-xs rounded-md border border-[var(--color-border,#232733)] bg-transparent px-3 py-2 text-sm text-[var(--color-text-primary,#f1f5f9)] focus:outline-none focus:ring-1 focus:ring-violet-500 sm:w-auto"
            >
              {LANDING_PAGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} className="bg-[var(--color-bg,#0f1115)]">
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-secondary,#94a3b8)]">
              <PiClockBold className="h-3.5 w-3.5" />
              Time Format
            </label>
            <div className="flex gap-2">
              {TIME_FORMAT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => updateField("time_format", opt.value)}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    prefs.time_format === opt.value
                      ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                      : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Notifications */}
      <Card title="Notification Preferences">
        <div className="flex flex-col divide-y divide-[var(--color-border,#232733)]">
          {NOTIFICATION_TOGGLES.map(({ key, label }) => (
            <div key={key} className="flex items-center justify-between py-2.5">
              <span className="flex items-center gap-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
                <PiBellBold className="h-3.5 w-3.5 text-[var(--color-text-secondary,#64748b)]" />
                {label}
              </span>
              <ToggleSwitch
                checked={Boolean(prefs.notifications[key])}
                onChange={() => toggleNotification(key)}
              />
            </div>
          ))}
        </div>
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

export default Preferences;