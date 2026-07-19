import toast, { Toaster } from "react-hot-toast";
import { motion } from "framer-motion";
import {
  PiCheckCircleBold,
  PiXCircleBold,
  PiWarningBold,
  PiInfoBold,
  PiBrainBold,
  PiXBold,
} from "react-icons/pi";

/**
 * Toast styling per notification type (Lavender Trinetra Design
 * System — same color language as components/StatusBadge.jsx):
 *   success    — Olive
 *   error      — Red
 *   warning    — Magenta
 *   info       — Gray (neutral)
 *   aiInsight  — Lavender (brand accent, for AI-generated notices)
 */
const TOAST_TYPES = {
  success: { icon: PiCheckCircleBold, color: "#a3c266", bg: "rgba(163,194,102,0.12)", duration: 4000 },
  error: { icon: PiXCircleBold, color: "#f87171", bg: "rgba(248,113,113,0.12)", duration: 6000 },
  warning: { icon: PiWarningBold, color: "#e879c9", bg: "rgba(232,121,201,0.12)", duration: 5000 },
  info: { icon: PiInfoBold, color: "#94a3b8", bg: "rgba(148,163,184,0.12)", duration: 4000 },
  aiInsight: { icon: PiBrainBold, color: "#b4a7f5", bg: "rgba(180,167,245,0.12)", duration: 6000 },
};

/**
 * ToastCard — the animated visual body rendered inside every toast
 * triggered by this module, via react-hot-toast's toast.custom().
 */
function ToastCard({ toastInstance, type, message, title }) {
  const config = TOAST_TYPES[type] ?? TOAST_TYPES.info;
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: -12, scale: 0.96 }}
      animate={{
        opacity: toastInstance.visible ? 1 : 0,
        y: toastInstance.visible ? 0 : -12,
        scale: toastInstance.visible ? 1 : 0.96,
      }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] p-3.5 shadow-lg"
    >
      <span
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg"
        style={{ backgroundColor: config.bg, color: config.color }}
      >
        <Icon className="h-4 w-4" />
      </span>

      <div className="min-w-0 flex-1 pt-0.5">
        {title && (
          <p className="text-sm font-semibold text-[var(--color-text-primary,#f1f5f9)]">{title}</p>
        )}
        <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">{message}</p>
      </div>

      <button
        type="button"
        onClick={() => toast.dismiss(toastInstance.id)}
        className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-[var(--color-text-secondary,#64748b)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
        aria-label="Dismiss notification"
      >
        <PiXBold className="h-3.5 w-3.5" />
      </button>
    </motion.div>
  );
}

function fireToast(type, message, options = {}) {
  const config = TOAST_TYPES[type] ?? TOAST_TYPES.info;
  const { title, duration, position, id } = options;

  return toast.custom(
    (toastInstance) => (
      <ToastCard toastInstance={toastInstance} type={type} message={message} title={title} />
    ),
    {
      duration: duration ?? config.duration,
      position,
      id,
    }
  );
}

/** showSuccessToast — Olive. For completed actions (e.g. "Monitoring started"). */
export function showSuccessToast(message, options) {
  return fireToast("success", message, options);
}

/** showErrorToast — Red. For failed requests/actions. */
export function showErrorToast(message, options) {
  return fireToast("error", message, options);
}

/** showWarningToast — Magenta. For degraded states or risky actions. */
export function showWarningToast(message, options) {
  return fireToast("warning", message, options);
}

/** showInfoToast — Gray. For neutral, informational notices. */
export function showInfoToast(message, options) {
  return fireToast("info", message, options);
}

/** showAIInsightToast — Lavender. For AI-generated insights/recommendations. */
export function showAIInsightToast(message, options) {
  return fireToast("aiInsight", message, { title: "Trinetra AI", ...options });
}

/** showToast — generic dispatcher: showToast("warning", "message"). */
export function showToast(type, message, options) {
  return fireToast(type, message, options);
}

/** dismissToast — manually close a toast by id (or all, if omitted). */
export function dismissToast(id) {
  toast.dismiss(id);
}

/**
 * AppToaster — the single <Toaster/> instance for the application.
 * Mount once near the root (e.g. in App.jsx) alongside the trigger
 * functions above; every toast fired via this module renders through
 * this instance. Default position can be overridden per-call.
 */
export function AppToaster({ position = "top-right" }) {
  return (
    <Toaster
      position={position}
      gutter={10}
      toastOptions={{
        className: "!bg-transparent !shadow-none !p-0",
      }}
    />
  );
}

export default AppToaster;