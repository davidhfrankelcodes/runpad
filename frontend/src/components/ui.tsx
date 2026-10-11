import {
  cloneElement,
  useId,
  useState,
  type ReactElement,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { copyText } from "../clipboard";

/** A short explanation shown on hover and keyboard focus (Escape hides it), and given to
 * screen readers as the description of the element it wraps. */
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
  const [dismissed, setDismissed] = useState(false);
  const position = side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5";
  return (
    <span
      className={`group/tip relative ${className}`}
      onKeyDown={(e) => e.key === "Escape" && setDismissed(true)}
      onMouseLeave={() => setDismissed(false)}
      onBlur={() => setDismissed(false)}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span
        role="tooltip"
        id={id}
        // display: none while hidden, so tips near an edge do not widen the page.
        className={`pointer-events-none absolute left-1/2 z-30 hidden w-max max-w-64 -translate-x-1/2 rounded-md border border-line-strong bg-card px-2 py-1 text-left text-xs font-normal text-fg shadow-lg backdrop-blur-md ${position} ${
          dismissed
            ? ""
            : // Keyboard focus only: a clicked button keeps focus, and its tip should not linger.
              "group-hover/tip:block group-has-[:focus-visible]/tip:block"
        }`}
      >
        {text}
      </span>
    </span>
  );
}

export function Button({
  variant = "primary",
  className = "",
  tooltip,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  tooltip?: string;
}) {
  const styles = {
    primary: "bg-button text-button-fg hover:bg-button-hover hover:text-button-fg-hover",
    secondary: "bg-raised text-fg hover:bg-raised-hover",
    danger: "bg-red-700 text-white hover:bg-red-600",
  }[variant];
  const button = (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
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

export function CopyableText({ value, label }: { value: string; label?: string }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      {label && <span className="text-soft">{label}</span>}
      <div className="flex gap-2">
        <input
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

export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-card p-5">
      <h2 className="mb-4 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function CenteredPage({ children }: { children: ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-6">{children}</main>;
}

export const PASSWORD_HINT = "At least 12 characters.";
