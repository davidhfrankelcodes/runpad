import {
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-button text-button-fg hover:bg-button-hover hover:text-button-fg-hover",
    secondary: "bg-raised text-fg hover:bg-raised-hover",
    danger: "bg-red-700 text-white hover:bg-red-600",
  }[variant];
  return (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
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
export function CopyableText({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const canCopy = typeof navigator !== "undefined" && Boolean(navigator.clipboard);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

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
        {canCopy && (
          <Button type="button" variant="secondary" onClick={() => void copy()}>
            {copied ? "Copied" : "Copy"}
          </Button>
        )}
      </div>
    </div>
  );
}

export function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-soft">
      {children}
    </span>
  );
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
