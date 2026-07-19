import { motion } from "framer-motion";

const SPINNER_SIZES = {
  sm: 16,
  md: 28,
  lg: 44,
};

/**
 * Spinner — the core rotating indicator used by every other Loader
 * variant, in the Lavender Trinetra brand accent color.
 */
function Spinner({ size = "md" }) {
  const diameter = SPINNER_SIZES[size] ?? SPINNER_SIZES.md;
  const borderWidth = Math.max(2, Math.round(diameter * 0.12));

  return (
    <motion.span
      role="status"
      aria-label="Loading"
      className="inline-block flex-shrink-0 rounded-full"
      style={{
        width: diameter,
        height: diameter,
        borderWidth,
        borderStyle: "solid",
        borderColor: "rgba(180,167,245,0.2)",
        borderTopColor: "#b4a7f5",
      }}
      animate={{ rotate: 360 }}
      transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}
    />
  );
}

/**
 * Skeleton — pulsing placeholder blocks for content that hasn't
 * loaded yet. Supports simple text-line skeletons or a single
 * block/circle shape.
 *
 * Props:
 *   shape ("text"|"block"|"circle") — default "text".
 *   lines (number)                  — number of bars when shape="text", default 3.
 *   className (string)              — sizing overrides (e.g. "h-24 w-24" for a circle).
 */
export function Skeleton({ shape = "text", lines = 3, className = "" }) {
  if (shape === "circle") {
    return (
      <div
        className={`animate-pulse rounded-full bg-white/5 ${className || "h-12 w-12"}`}
      />
    );
  }

  if (shape === "block") {
    return <div className={`animate-pulse rounded-lg bg-white/5 ${className || "h-24 w-full"}`} />;
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className="h-3 animate-pulse rounded-full bg-white/5"
          style={{ width: index === lines - 1 ? "60%" : "100%" }}
        />
      ))}
    </div>
  );
}

/**
 * Loader — reusable loading indicator with five presentation modes.
 * Purely presentational; carries no data-fetching or business logic.
 *
 * Props:
 *   variant ("spinner"|"inline"|"card"|"fullpage"|"skeleton") — default "spinner".
 *   label (string)     — optional loading text.
 *   size ("sm"|"md"|"lg") — spinner size, default "md" ("lg" for fullpage).
 *   lines (number)     — skeleton line count, passed through when variant="skeleton".
 *   className (string) — additional classes on the outer wrapper.
 */
function Loader({ variant = "spinner", label, size = "md", lines = 3, className = "" }) {
  if (variant === "skeleton") {
    return <Skeleton lines={lines} className={className} />;
  }

  if (variant === "inline") {
    return (
      <span className={`inline-flex items-center gap-2 ${className}`}>
        <Spinner size="sm" />
        {label && <span className="text-sm text-[var(--color-text-secondary,#94a3b8)]">{label}</span>}
      </span>
    );
  }

  if (variant === "card") {
    return (
      <div
        className={`flex min-h-[160px] flex-col items-center justify-center gap-3 rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] p-8 ${className}`}
      >
        <Spinner size={size} />
        {label && <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">{label}</p>}
      </div>
    );
  }

  if (variant === "fullpage") {
    return (
      <div
        className={`fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-[var(--color-bg,#0f1115)]/80 backdrop-blur-sm ${className}`}
      >
        <Spinner size="lg" />
        {label && (
          <p className="text-sm font-medium text-[var(--color-text-secondary,#94a3b8)]">{label}</p>
        )}
      </div>
    );
  }

  // Default: "spinner" — compact, drop-in centered loader for
  // sections/pages (matches existing `<Loader label="..." />` usage).
  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <Spinner size={size} />
      {label && <p className="text-sm text-[var(--color-text-secondary,#94a3b8)]">{label}</p>}
    </div>
  );
}

export default Loader;