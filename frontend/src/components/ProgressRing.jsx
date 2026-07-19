import { motion } from "framer-motion";

const THEME_COLORS = {
  lavender: "#b4a7f5",
  olive: "#a3c266",
  magenta: "#e879c9",
  red: "#f87171",
};

/**
 * ProgressRing — reusable animated circular progress indicator.
 * Renders a value (0-100) as an arc with the percentage centered
 * inside. Purely presentational: it clamps and draws whatever value
 * it's given and never decides what that value means — callers choose
 * the color theme (e.g. "red" for a critical CPU reading, "lavender"
 * for a healthy AI score).
 *
 * Reusable for: AI Health Score, CPU/RAM/Disk Usage, Security Score.
 *
 * Props:
 *   value (number)               — 0-100, clamped internally.
 *   size (number)                — outer diameter in px, default 72.
 *   thickness (number)           — stroke width in px, default size * 0.11.
 *   color ("lavender"|"olive"|"magenta"|"red") — theme, default "lavender".
 *   showValue (bool)             — render the percentage inside the ring, default true.
 *   label (string)               — optional small text under the value (e.g. "%").
 *   className (string)
 */
function ProgressRing({
  value = 0,
  size = 72,
  thickness,
  color = "lavender",
  showValue = true,
  label,
  className = "",
}) {
  const clampedValue = Math.min(100, Math.max(0, Number(value) || 0));
  const strokeWidth = thickness ?? Math.max(4, Math.round(size * 0.11));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clampedValue / 100);
  const strokeColor = THEME_COLORS[color] ?? THEME_COLORS.lavender;

  const fontSize = Math.max(11, Math.round(size * 0.22));

  return (
    <div
      className={`relative flex-shrink-0 ${className}`}
      style={{ width: size, height: size, maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width="100%"
        height="100%"
        className="-rotate-90"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border, #232733)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={false}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ type: "spring", stiffness: 90, damping: 20 }}
        />
      </svg>

      {showValue && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-semibold leading-none text-[var(--color-text-primary,#f1f5f9)]"
            style={{ fontSize }}
          >
            {Math.round(clampedValue)}
            <span className="text-[0.6em] font-normal text-[var(--color-text-secondary,#94a3b8)]">
              %
            </span>
          </span>
          {label && (
            <span className="mt-0.5 text-[0.55em] text-[var(--color-text-secondary,#64748b)]">
              {label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default ProgressRing;