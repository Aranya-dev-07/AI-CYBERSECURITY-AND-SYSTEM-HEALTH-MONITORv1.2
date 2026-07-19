import { useEffect } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { PiXBold } from "react-icons/pi";

const SIZE_CLASSES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
};

const ACTION_VARIANT_CLASSES = {
  primary: "bg-violet-600 text-white hover:bg-violet-500 disabled:hover:bg-violet-600",
  danger: "bg-rose-600/15 text-rose-300 hover:bg-rose-600/25 disabled:hover:bg-rose-600/15",
  secondary:
    "bg-white/5 text-[var(--color-text-primary,#f1f5f9)] hover:bg-white/10 disabled:hover:bg-white/5",
};

function ActionButton({ label, onClick, variant = "secondary", disabled, isLoading }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isLoading}
      className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${ACTION_VARIANT_CLASSES[variant] ?? ACTION_VARIANT_CLASSES.secondary}`}
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {label}
    </button>
  );
}

/**
 * Modal — reusable animated dialog for confirmations, alerts, and
 * future settings panels. Handles overlay click-to-close, Escape key
 * dismissal, body scroll locking, and open/close animation. Purely
 * presentational/interactional — no business logic.
 *
 * Props:
 *   isOpen (bool)              — controls mount/visibility.
 *   onClose (function)         — called on overlay click, Escape, or close button.
 *   title (node)               — header title.
 *   children (node)            — modal body content.
 *   footer (node)              — fully custom footer; overrides `actions` if provided.
 *   actions (array)            — [{ label, onClick, variant, disabled, isLoading }],
 *                                 rendered as the default footer when `footer` is omitted.
 *   size ("sm"|"md"|"lg")      — dialog width, default "md".
 *   closeOnOverlayClick (bool) — default true.
 *   closeOnEscape (bool)       — default true.
 *   showCloseButton (bool)     — default true.
 *   className (string)        — additional classes on the dialog panel.
 */
function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  actions,
  size = "md",
  closeOnOverlayClick = true,
  closeOnEscape = true,
  showCloseButton = true,
  className = "",
}) {
  useEffect(() => {
    if (!isOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event) {
      if (closeOnEscape && event.key === "Escape") {
        onClose?.();
      }
    }

    if (closeOnEscape) {
      document.addEventListener("keydown", handleKeyDown);
    }

    return () => {
      document.body.style.overflow = previousOverflow;
      if (closeOnEscape) {
        document.removeEventListener("keydown", handleKeyDown);
      }
    };
  }, [isOpen, closeOnEscape, onClose]);

  const hasHeader = Boolean(title) || showCloseButton;
  const hasDefaultFooter = !footer && Array.isArray(actions) && actions.length > 0;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            key="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={closeOnOverlayClick ? onClose : undefined}
          />

          <motion.div
            key="modal-panel"
            role="dialog"
            aria-modal="true"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={{ type: "spring", stiffness: 340, damping: 28 }}
            className={`relative z-10 w-full ${SIZE_CLASSES[size] ?? SIZE_CLASSES.md} max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--color-border,#232733)] bg-[var(--color-surface,#171923)] shadow-2xl ${className}`}
          >
            {hasHeader && (
              <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border,#232733)] px-5 py-4">
                {title && (
                  <h2 className="text-base font-semibold text-[var(--color-text-primary,#f1f5f9)]">
                    {title}
                  </h2>
                )}
                {showCloseButton && (
                  <button
                    type="button"
                    onClick={onClose}
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-[var(--color-text-secondary,#94a3b8)] transition-colors hover:bg-white/5 hover:text-[var(--color-text-primary,#f1f5f9)]"
                    aria-label="Close dialog"
                  >
                    <PiXBold className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}

            <div className="px-5 py-4 text-sm text-[var(--color-text-primary,#f1f5f9)]">
              {children}
            </div>

            {footer ? (
              <div className="border-t border-[var(--color-border,#232733)] px-5 py-4">{footer}</div>
            ) : hasDefaultFooter ? (
              <div className="flex justify-end gap-2 border-t border-[var(--color-border,#232733)] px-5 py-4">
                {actions.map((action) => (
                  <ActionButton key={action.label} {...action} />
                ))}
              </div>
            ) : null}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export default Modal;