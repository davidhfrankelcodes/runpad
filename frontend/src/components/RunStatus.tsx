import type { RunSummary } from "../actions";
import { Tooltip } from "./ui";

const styles: Record<RunSummary["status"], string> = {
  running: "bg-sky-900 text-sky-200",
  succeeded: "bg-emerald-900 text-emerald-200",
  failed: "bg-red-900 text-red-200",
  timed_out: "bg-amber-900 text-amber-200",
  cancelled: "bg-raised-hover text-soft",
  interrupted: "bg-raised-hover text-soft",
};

const meanings: Record<RunSummary["status"], string> = {
  running: "Still running.",
  succeeded: "Finished with exit code 0 (for HTTP: a 2xx response).",
  failed: "Finished with a non-zero exit code, an HTTP error, or could not start.",
  timed_out: "Stopped because it ran longer than the action's timeout.",
  cancelled: "Stopped by a user before it finished.",
  interrupted: "runpad stopped or restarted while this was running.",
};

export function RunStatus({ status }: { status: RunSummary["status"] }) {
  return (
    <Tooltip text={meanings[status]}>
      <span
        tabIndex={0}
        className={`rounded px-1.5 py-0.5 text-xs font-medium ${styles[status]}`}
      >
        {status.replace("_", " ")}
      </span>
    </Tooltip>
  );
}
