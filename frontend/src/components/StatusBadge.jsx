import { AnimatePresence, motion } from "framer-motion";
import { PiCircleFill, PiCircleDashedBold } from "react-icons/pi";

/**
 * Canonical status colors (Lavender Trinetra Design System):
 *   Olive     — healthy / online / good states
 *   Magenta   — warning / starting / transitional states
 *   Red       — critical / severe states
 *   Lavender  — active AI processing (brand accent)
 *   Gray      — offline / idle / unknown states
 */
const COLORS = {
  olive: { text: "#a3c266", bg: "rgba(163,194,102,0.15)", dot: "#a3c266" },
  magenta: { text: "#e879c9", bg: "rgba(232,121,201,0.15)", dot: "#e879c9" },
  red: { text: "#f87171", bg: "rgba(248,113,113,0.15)", dot: "#f87171" },
  lavender: { text: "#b4a7f5", bg: "rgba(180,167,245,0.15)", dot: "#b4a7f5" },
  gray: { text: "#94a3b8", bg: "rgba(148,163,184,0.15)", dot: "#94a3b8" },
};

/** Canonical status set and their presentation. */
const STATUS_CONFIG = {
  healthy: { label: "Healthy", color: "olive", pulse: false },
  warning: { label: "Warning", color: "magenta", pulse: false },
  critical: { label: "Critical", color: "red", pulse: true },
  online: { label: "Online", color: "olive", pulse: false },
  offline: { label: "Offline", color: "gray", pulse: false },
  starting: { label: "Starting", color: "magenta", pulse: true },
  ai_processing: { label: "AI Processing", color: "lavender", pulse: true },
};

/**
 * Maps the many status vocabularies already in use across the app
 * (health statuses, severities, connection states, process states)
 * onto the canonical STATUS_CONFIG keys above. Unrecognized values
 * fall back to a neutral gray badge showing the raw text as-is.
 */
const ALIASES = {
  // Health status (ai/health_score.py)
  excellent: "healthy",
  good: "healthy",
  fair: "warning",
  poor: "warning",

  // Severity (root_cause.py, recommendations.py, anomaly_detection.py)
  low: "healthy",
  medium: "warning",
  high: "critical",

  // Connection / lifecycle
  connecting: "starting",
  reconnecting: "starting",
  idle: "offline",
  running: "healthy",
  active: "healthy",
  processing: "ai_processing",
  "ai processing": "ai_processing",
};

function resolveStatus(rawStatus) {
  const key = String(rawStatus ?? "").trim().toLowerCase();
  const canonicalKey = STATUS_CONFIG[key] ? key : ALIASES[key];

  if (canonicalKey && STATUS_CONFIG[canonicalKey]) {
    return { key: canonicalKey, ...STATUS_CONFIG[canonicalKey] };
  }

  return {
    key: key || "unknown",
    label: rawStatus ? String(rawStatus) : "Unknown",
    color: "gray",
    pulse: false,
  };
}

const SIZE_CLASSES = {
  sm: "gap-1 px-2 py-0.5 text-[11px]",
  md: "gap-1.5 px-2.5 py-1 text-xs",
};

/**
 * StatusBadge — reusable animated status indicator. Normalizes many
 * different status vocabularies (health status, severity, connection
 * state) onto a consistent color language and animates transitions
 * between statuses. Purely presentational — no business logic.
 *
 * Props:
 *   status (string)     — raw status value (e.g. "online", "Excellent", "High").
 *   showIcon (bool)      — show the leading dot/icon, default true.
 *   showLabel (bool)     — show the text label, default true.
 *   icon (component)     — override the default dot with a custom icon.
 *   size ("sm"|"md")     — badge size, default "md".
 *   className (string)   — additional classes.
 */
function StatusBadge({
  status,
  showIcon = true,
  showLabel = true,
  icon: CustomIcon,
  size = "md",
  className = "",
}) {
  const resolved = resolveStatus(status);
  const palette = COLORS[resolved.color];
  const sizeClass = SIZE_CLASSES[size] ?? SIZE_CLASSES.md;
  const Icon = CustomIcon || (resolved.pulse ? PiCircleDashedBold : PiCircleFill);

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={resolved.key}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        transition={{ duration: 0.15 }}
        className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${className}`}
        style={{ color: palette.text, backgroundColor: palette.bg }}
      >
        {showIcon && (
          <motion.span
            className="flex items-center justify-center"
            animate={resolved.pulse ? { opacity: [1, 0.35, 1] } : { opacity: 1 }}
            transition={
              resolved.pulse
                ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" }
                : { duration: 0.15 }
            }
          >
            <Icon className="h-2 w-2" style={{ color: palette.dot }} />
          </motion.span>
        )}
        {showLabel && <span>{resolved.label}</span>}
      </motion.span>
    </AnimatePresence>
  );
}

export default StatusBadge;