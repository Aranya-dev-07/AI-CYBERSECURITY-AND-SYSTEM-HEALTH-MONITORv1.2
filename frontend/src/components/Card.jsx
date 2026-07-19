import { motion } from "framer-motion";

const PADDING_CLASSES = {
  none: "p-0",
  sm: "p-3",
  md: "p-5",
  lg: "p-7",
};

/**
 * Card — the base reusable container used across every page and
 * feature widget in Lavender Trinetra. Supports a title/icon/action
 * header (or a fully custom header), an optional large `value`
 * display, arbitrary children, and an optional footer. Purely
 * presentational — no data fetching or business logic.
 *
 * Props:
 *   title (string)      — default header title.
 *   subtitle (string)   — small text under the title.
 *   icon (component)    — icon component rendered in a chip left of the title.
 *   action (node)       — rendered top-right of the header (e.g. a button/menu).
 *   header (node)       — fully custom header; overrides title/subtitle/icon/action.
 *   value (node|string) — large stat value rendered below the header.
 *   footer (node)       — rendered in a top-bordered footer section.
 *   padding ("none"|"sm"|"md"|"lg") — body padding, default "md".
 *   onClick (function)  — makes the whole card interactive/clickable.
 *   hoverEffect (bool)  — enable the hover lift animation, default true.
 *   className (string)  — additional classes merged onto the outer container.
 *   children (node)
 */
function Card({
  title,
  subtitle,
  icon: Icon,
  action,
  header,
  value,
  footer,
  padding = "md",
  onClick,
  hoverEffect = true,
  className = "",
  children,
}) {
  const isInteractive = Boolean(onClick);
  const paddingClass = PADDING_CLASSES[padding] ?? PADDING_CLASSES.md;
  const hasDefaultHeader = !header && (title || Icon || action);

  const MotionTag = isInteractive ? motion.button : motion.div;

  return (
    <MotionTag
      type={isInteractive ? "button" : undefined}
      onClick={onClick}
      whileHover={
        hoverEffect
          ? { y: -2, boxShadow: "0 12px 24px -8px rgba(124, 58, 237, 0.18)" }
          : undefined
      }
      whileTap={isInteractive ? { scale: 0.99 } : undefined}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
      className={[
        "w-full rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] shadow-sm",
        isInteractive ? "cursor-pointer text-left" : "",
        paddingClass,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {header ? (
        <div className="mb-4">{header}</div>
      ) : hasDefaultHeader ? (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {Icon && (
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-violet-600/15 text-violet-400">
                <Icon className="h-5 w-5" />
              </span>
            )}
            <div className="min-w-0">
              {title && (
                <h3 className="truncate text-sm font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="truncate text-xs text-[var(--color-text-secondary,#94a3b8)]">
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </div>
      ) : null}

      {value != null && (
        <p className="mb-1 text-2xl font-semibold text-[var(--color-text-primary,#f1f5f9)]">
          {value}
        </p>
      )}

      {children}

      {footer && (
        <div className="mt-4 border-t border-[var(--color-border,#232733)] pt-3">{footer}</div>
      )}
    </MotionTag>
  );
}

export default Card;