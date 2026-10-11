import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-emerald-600 text-white hover:bg-emerald-500",
    secondary: "bg-zinc-800 text-zinc-100 hover:bg-zinc-700",
    danger: "bg-red-700 text-white hover:bg-red-600",
  }[variant];
  return (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
}

export function TextField({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-zinc-300">{label}</span>
      <input
        className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100 outline-none focus:border-emerald-500"
        {...props}
      />
      {hint && <span className="text-xs text-zinc-500">{hint}</span>}
    </label>
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
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5">
      <h2 className="mb-4 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function CenteredPage({ children }: { children: ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-6">{children}</main>;
}

export const PASSWORD_HINT = "At least 12 characters.";
