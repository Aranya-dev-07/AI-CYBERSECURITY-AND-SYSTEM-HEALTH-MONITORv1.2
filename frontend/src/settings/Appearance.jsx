import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  PiPaintBrushBold,
  PiMoonBold,
  PiSunBold,
  PiArrowsOutLineHorizontalBold,
  PiSquaresFourBold,
  PiSparkleBold,
  PiTextAaBold,
  PiPaletteBold,
  PiFloppyDiskBold,
  PiArrowCounterClockwiseBold,
  PiLockBold,
} from "react-icons/pi";

import Card from "../components/Card.jsx";
import Loader from "../components/Loader.jsx";
import { getAppearanceSettings, updateAppearanceSettings } from "../services/api.js";

const DEFAULT_APPEARANCE = {
  theme_mode: "dark",
  sidebar_width: "comfortable",
  card_density: "comfortable",
  animations_enabled: true,
  font_size: "medium",
  accent_color: "lavender",
};

const THEME_OPTIONS = [
  { value: "dark", label: "Dark", icon: PiMoonBold, available: true },
  { value: "light", label: "Light", icon: PiSunBold, available: false },
];

const SIDEBAR_WIDTH_OPTIONS = [
  { value: "compact", label: "Compact" },
  { value: "comfortable", label: "Comfortable" },
  { value: "wide", label: "Wide" },
];

const CARD_DENSITY_OPTIONS = [
  { value: "compact", label: "Compact" },
  { value: "comfortable", label: "Comfortable" },
  { value: "spacious", label: "Spacious" },
];

const FONT_SIZE_OPTIONS = [
  { value: "small", label: "Small", scale: "text-xs" },
  { value: "medium", label: "Medium", scale: "text-sm" },
  { value: "large", label: "Large", scale: "text-base" },
];

const ACCENT_COLOR_OPTIONS = [
  { value: "lavender", label: "Lavender", swatch: "#8b5cf6", available: true },
  { value: "sky", label: "Sky", swatch: "#38bdf8", available: false },
  { value: "emerald", label: "Emerald", swatch: "#34d399", available: false },
  { value: "amber", label: "Amber", swatch: "#fbbf24", available: false },
];

const DENSITY_PADDING = {
  compact: "p-2",
  comfortable: "p-4",
  spacious: "p-6",
};

const FONT_SIZE_CLASS = {
  small: "text-xs",
  medium: "text-sm",
  large: "text-base",
};

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
 * Appearance — the workspace appearance settings panel. Loads the
 * current display preferences (theme mode, sidebar width, card
 * density, animation toggle, font size, accent color) from the
 * backend via services/api.js, lets the user preview and edit them
 * locally, and persists changes back through services/api.js.
 * Implements no global theming/CSS-variable application itself — that
 * responsibility belongs to AppShell.jsx and the Lavender Trinetra
 * Design System's root styles; this panel only edits and previews the
 * stored configuration.
 */
function Appearance() {
  const [settings, setSettings] = useState(DEFAULT_APPEARANCE);
  const [savedSettings, setSavedSettings] = useState(DEFAULT_APPEARANCE);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;

    async function loadSettings() {
      setIsLoading(true);
      try {
        const data = await getAppearanceSettings();
        if (!isMountedRef.current) return;
        const merged = { ...DEFAULT_APPEARANCE, ...data };
        setSettings(merged);
        setSavedSettings(merged);
        setError(null);
      } catch (err) {
        if (!isMountedRef.current) return;
        setError(err?.message || "Failed to load appearance settings. Showing defaults.");
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    }

    loadSettings();
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const updateField = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(savedSettings);

  const handleReset = () => {
    setSettings(savedSettings);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const result = await updateAppearanceSettings(settings);
      const merged = { ...DEFAULT_APPEARANCE, ...settings, ...(result || {}) };
      setSettings(merged);
      setSavedSettings(merged);
      toast.success("Appearance settings saved.");
    } catch (err) {
      toast.error(err?.message || "Failed to save appearance settings.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader label="Loading appearance settings..." />
      </div>
    );
  }

  const selectedAccent = ACCENT_COLOR_OPTIONS.find((a) => a.value === settings.accent_color);

  return (
    <div className="flex flex-col gap-5">
      <h3 className="flex items-center gap-2 text-lg font-semibold text-[var(--color-text-primary,#f1f5f9)]">
        <PiPaintBrushBold className="h-5 w-5 text-violet-400" />
        Appearance
      </h3>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      {/* Theme mode */}
      <Card title="Theme Mode">
        <div className="flex flex-wrap gap-2">
          {THEME_OPTIONS.map(({ value, label, icon: Icon, available }) => (
            <button
              key={value}
              type="button"
              disabled={!available}
              onClick={() => available && updateField("theme_mode", value)}
              title={!available ? `${label} theme coming soon` : label}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                settings.theme_mode === value
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)]"
              } ${!available ? "cursor-not-allowed opacity-50" : "hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"}`}
            >
              <Icon className="h-4 w-4" />
              {label}
              {!available && <PiLockBold className="h-3 w-3" />}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-[var(--color-text-secondary,#64748b)]">
          The Lavender Trinetra Design System currently ships dark mode only. Light mode is
          future-ready.
        </p>
      </Card>

      {/* Sidebar width */}
      <Card title="Sidebar Width">
        <div className="flex flex-wrap gap-2">
          {SIDEBAR_WIDTH_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => updateField("sidebar_width", opt.value)}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                settings.sidebar_width === opt.value
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
              }`}
            >
              <PiArrowsOutLineHorizontalBold className="h-4 w-4" />
              {opt.label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex items-stretch gap-2 rounded-lg border border-[var(--color-border,#232733)] p-2">
          <div
            className={`flex flex-shrink-0 items-center justify-center rounded-md bg-white/5 text-[10px] text-[var(--color-text-secondary,#64748b)] transition-all ${
              settings.sidebar_width === "compact"
                ? "w-10"
                : settings.sidebar_width === "wide"
                ? "w-24"
                : "w-16"
            }`}
          >
            Sidebar
          </div>
          <div className="flex flex-1 items-center justify-center rounded-md bg-white/[0.03] text-[10px] text-[var(--color-text-secondary,#64748b)]">
            Content
          </div>
        </div>
      </Card>

      {/* Card density */}
      <Card title="Card Density">
        <div className="flex flex-wrap gap-2">
          {CARD_DENSITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => updateField("card_density", opt.value)}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                settings.card_density === opt.value
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
              }`}
            >
              <PiSquaresFourBold className="h-4 w-4" />
              {opt.label}
            </button>
          ))}
        </div>
        <div
          className={`mt-3 rounded-lg border border-[var(--color-border,#232733)] bg-white/[0.03] ${DENSITY_PADDING[settings.card_density]}`}
        >
          <p className="text-xs text-[var(--color-text-secondary,#64748b)]">Preview Card</p>
          <p className="mt-1 text-sm font-medium text-[var(--color-text-primary,#f1f5f9)]">
            System Health: 94/100
          </p>
        </div>
      </Card>

      {/* Animations */}
      <Card title="Animations">
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-1.5 text-sm text-[var(--color-text-primary,#f1f5f9)]">
            <PiSparkleBold className="h-4 w-4 text-[var(--color-text-secondary,#64748b)]" />
            Enable interface animations
          </label>
          <ToggleSwitch
            checked={settings.animations_enabled}
            onChange={(v) => updateField("animations_enabled", v)}
          />
        </div>
      </Card>

      {/* Font size */}
      <Card title="Font Size">
        <div className="flex flex-wrap gap-2">
          {FONT_SIZE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => updateField("font_size", opt.value)}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                settings.font_size === opt.value
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)] hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
              }`}
            >
              <PiTextAaBold className="h-4 w-4" />
              {opt.label}
            </button>
          ))}
        </div>
        <p className={`mt-3 rounded-lg border border-[var(--color-border,#232733)] bg-white/[0.03] p-3 text-[var(--color-text-primary,#f1f5f9)] ${FONT_SIZE_CLASS[settings.font_size]}`}>
          The quick brown fox jumps over the lazy dog.
        </p>
      </Card>

      {/* Accent color */}
      <Card title="Accent Color">
        <div className="flex flex-wrap gap-2">
          {ACCENT_COLOR_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              disabled={!opt.available}
              onClick={() => opt.available && updateField("accent_color", opt.value)}
              title={!opt.available ? `${opt.label} accent coming soon` : opt.label}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                settings.accent_color === opt.value
                  ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
                  : "border-[var(--color-border,#232733)] text-[var(--color-text-secondary,#94a3b8)]"
              } ${!opt.available ? "cursor-not-allowed opacity-50" : "hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"}`}
            >
              <span
                className="h-3.5 w-3.5 rounded-full border border-white/20"
                style={{ backgroundColor: opt.swatch }}
              />
              {opt.label}
              {!opt.available && <PiLockBold className="h-3 w-3" />}
            </button>
          ))}
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-xs text-[var(--color-text-secondary,#64748b)]">
          <PiPaletteBold className="h-3.5 w-3.5" />
          Currently locked to Lavender ({selectedAccent?.swatch}), the design system default.
          Additional accents are future-ready.
        </p>
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

export default Appearance;