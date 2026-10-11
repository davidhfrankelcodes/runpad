import type { RunSummary } from "../actions";

const styles: Record<RunSummary["status"], string> = {
  running: "bg-sky-900 text-sky-200",
  succeeded: "bg-emerald-900 text-emerald-200",
  failed: "bg-red-900 text-red-200",
  timed_out: "bg-amber-900 text-amber-200",
  cancelled: "bg-raised-hover text-soft",
  interrupted: "bg-raised-hover text-soft",
};

export function RunStatus({ status }: { status: RunSummary["status"] }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${styles[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
