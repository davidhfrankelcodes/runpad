import {
  cloneElement,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { copyText } from "../clipboard";

/** Room kept between a tooltip and the edge of the screen, in pixels. */
const TIP_MARGIN = 8;

/** A short explanation shown on hover and keyboard focus (Escape hides it), and given to
 * screen readers as the description of the element it wraps. It is drawn over the whole
 * page (a portal), so a card or table that clips its content never cuts it off, and it is
 * kept on screen near the edges. */
export function Tooltip({
  text,
  children,
  side = "top",
  className = "inline-flex",
}: {
  text: string;
  children: ReactElement<{ "aria-describedby"?: string }>;
  side?: "top" | "bottom";
  /** For the wrapper; use "flex" for an element that should fill its grid cell. */
  className?: string;
}) {
  const id = useId();
  const wrapper = useRef<HTMLSpanElement>(null);
  const tip = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const open = (hovered || focused) && !dismissed;

  useLayoutEffect(() => {
    // Placed before the browser paints, so an old position never shows.
    if (!open) return;
    function place() {
      const anchor = wrapper.current?.getBoundingClientRect();
      const box = tip.current?.getBoundingClientRect();
      if (!anchor || !box) return;
      const gap = 6;
      const above = anchor.top - gap - box.height;
      const below = anchor.bottom + gap;
      // The preferred side, unless the tip does not fit there and does on the other.
      const top =
        side === "top"
          ? above >= TIP_MARGIN || below + box.height > window.innerHeight - TIP_MARGIN
            ? above
            : below
          : below + box.height <= window.innerHeight - TIP_MARGIN || above < TIP_MARGIN
            ? below
            : above;
      const centered = anchor.left + anchor.width / 2 - box.width / 2;
      const left = Math.max(
        TIP_MARGIN,
        Math.min(centered, window.innerWidth - TIP_MARGIN - box.width),
      );
      setPosition({ left, top: Math.max(TIP_MARGIN, top) });
    }
    place();
    // Scrolling or resizing moves what it points at.
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, side, text]);

  return (
    <span
      ref={wrapper}
      className={`relative ${className}`}
      onKeyDown={(e) => e.key === "Escape" && setDismissed(true)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false);
        setDismissed(false);
      }}
      // Keyboard focus only: a clicked button keeps focus, and its tip should not linger.
      onFocus={(e) => setFocused(e.target.matches(":focus-visible"))}
      onBlur={() => {
        setFocused(false);
        setDismissed(false);
      }}
    >
      {cloneElement(children, { "aria-describedby": id })}
      {/* The description screen readers get; always present, never shown. */}
      <span id={id} role="tooltip" className="sr-only">
        {text}
      </span>
      {open &&
        createPortal(
          <span
            ref={tip}
            aria-hidden="true"
            style={position ?? { left: 0, top: 0, visibility: "hidden" }}
            className="pointer-events-none fixed z-50 block w-max max-w-64 rounded-md border border-line-strong bg-card px-2 py-1 text-left text-xs font-normal text-fg shadow-lg backdrop-blur-md"
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  tooltip,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  /** danger: Delete, Remove, Revoke. danger-solid: only to confirm a destructive run. */
  variant?: "primary" | "secondary" | "danger" | "danger-solid";
  /** sm: for buttons in dense lists. */
  size?: "md" | "sm";
  tooltip?: string;
}) {
  const styles = {
    primary: "bg-button text-button-fg hover:bg-button-hover hover:text-button-fg-hover",
    secondary: "bg-raised text-fg hover:bg-raised-hover",
    danger: "bg-raised text-red-500 hover:bg-red-700 hover:text-white",
    "danger-solid": "bg-red-700 text-white hover:bg-red-600",
  }[variant];
  const button = (
    <button
      className={`rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-2 text-sm"} ${styles} ${className}`}
      {...props}
    />
  );
  return tooltip ? <Tooltip text={tooltip}>{button}</Tooltip> : button;
}

/** A labelled form control. The hint is linked with aria-describedby rather than placed
 * inside the label, so the control's accessible name is just the label. */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: (ids: { id: string; hintId?: string }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="text-soft">
        {label}
      </label>
      {children({ id, hintId })}
      {hint && (
        <span id={hintId} className="text-xs text-faint">
          {hint}
        </span>
      )}
    </div>
  );
}

export function TextField({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      {({ id, hintId }) => (
        <input
          id={id}
          aria-describedby={hintId}
          className="rounded-md border border-line-strong bg-input px-3 py-2 text-fg outline-none focus:border-accent"
          {...props}
        />
      )}
    </Field>
  );
}

export function TextArea({
  label,
  hint,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      {({ id, hintId }) => (
        <textarea
          id={id}
          aria-describedby={hintId}
          className="rounded-md border border-line-strong bg-input px-3 py-2 font-mono text-xs text-fg outline-none focus:border-accent"
          rows={6}
          spellCheck={false}
          {...props}
        />
      )}
    </Field>
  );
}

export function SelectField({
  label,
  hint,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: ReactNode }) {
  return (
    <Field label={label} hint={hint}>
      {({ id, hintId }) => (
        <select
          id={id}
          aria-describedby={hintId}
          className="rounded-md border border-line-strong bg-input px-3 py-2 text-fg outline-none focus:border-accent"
          {...props}
        >
          {children}
        </select>
      )}
    </Field>
  );
}

/** Read-only text with a copy button. Falls back to select-on-focus where the
 * clipboard API is unavailable (plain-HTTP origins other than localhost). */
/** A button that copies `value` and briefly says so. */
export function CopyButton({
  value,
  label = "Copy",
  tooltip = "Copy to the clipboard",
  disabled,
}: {
  value: string;
  label?: string;
  tooltip?: string;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  function copy() {
    copyText(value).then(
      () => setState("copied"),
      () => setState("failed"),
    );
    setTimeout(() => setState("idle"), 1500);
  }

  return (
    <Button type="button" variant="secondary" tooltip={tooltip} disabled={disabled} onClick={copy}>
      {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
    </Button>
  );
}

/** "✕ Close", for buttons that dismiss a panel or page. */
export function CloseLabel() {
  return (
    <span className="flex items-center gap-1.5">
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="h-3.5 w-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
      >
        <path d="M6 6l12 12M18 6 6 18" />
      </svg>
      Close
    </span>
  );
}

export function CopyableText({ value, label }: { value: string; label?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      {label && (
        <label htmlFor={id} className="text-soft">
          {label}
        </label>
      )}
      <div className="flex gap-2">
        <input
          id={id}
          readOnly
          value={value}
          onFocus={(e) => e.currentTarget.select()}
          className="min-w-0 flex-1 rounded-md border border-line-strong bg-input px-3 py-2 font-mono text-xs text-soft"
        />
        <CopyButton value={value} />
      </div>
    </div>
  );
}

/** "51–100 of 120 · ← Newer · Page 2 of 3 · Older →" for a list shown a page at a time. */
export function Pager({
  page,
  pageSize,
  total,
  onPage,
  previous = "Previous",
  next = "Next",
  previousTip,
  nextTip,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  previous?: string;
  next?: string;
  previousTip?: string;
  nextTip?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-muted">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          tooltip={previousTip}
        >
          ← {previous}
        </Button>
        <span className="text-muted">
          Page {page} of {pages}
        </span>
        <Button
          variant="secondary"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          tooltip={nextTip}
        >
          {next} →
        </Button>
      </div>
    </nav>
  );
}

export function Badge({ children, tooltip }: { children: ReactNode; tooltip?: string }) {
  const badge = (
    <span
      tabIndex={tooltip ? 0 : undefined}
      className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-soft"
    >
      {children}
    </span>
  );
  return tooltip ? <Tooltip text={tooltip}>{badge}</Tooltip> : badge;
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <p role="alert" className="rounded-md bg-red-950 px-3 py-2 text-sm text-red-300">
      {message}
    </p>
  );
}

/** The buttons that end a form, the same everywhere: the main action last on the right,
 * Cancel before it, and a destructive action (Delete) alone on the left. */
export function FormActions({ start, children }: { start?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
      {start}
      {children && <div className="ml-auto flex flex-wrap justify-end gap-2">{children}</div>}
    </div>
  );
}

/** A titled panel. `actions` go at the right of the title, for what applies to the whole
 * panel (Close, or a link to make something new). */
export function Card({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-card p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {actions && <div className="flex gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function CenteredPage({ children }: { children: ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-6">{children}</main>;
}

export const PASSWORD_HINT = "At least 12 characters.";
