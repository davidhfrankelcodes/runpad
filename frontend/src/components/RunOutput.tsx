import { useEffect, useRef } from "react";
import { useCancelRun, useRun } from "../actions";
import { duration } from "../format";
import { useRunStream } from "../runStream";
import { RunStatus } from "./RunStatus";
import { Button, ErrorMessage } from "./ui";

/** A Run's status and live output, with a Cancel button while it runs. */
export function RunOutput({ id, compact = false }: { id: string; compact?: boolean }) {
  const run = useRun(id);
  const stream = useRunStream(id);
  const cancel = useCancelRun();
  const outputRef = useRef<HTMLPreElement>(null);

  // Keep the newest output in view.
  useEffect(() => {
    const element = outputRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [stream.output]);

  const current = stream.end ?? run.data;
  if (!current) return <ErrorMessage error={run.error} />;
  const running = current.status === "running";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className={compact ? "font-medium" : "text-lg font-semibold"}>
              {current.action_name}
            </h2>
            <RunStatus status={current.status} />
          </div>
          <p className="text-sm text-muted">
            Started by {current.triggered_by} at {new Date(current.started_at).toLocaleString()}
            {current.finished_at && ` · took ${duration(current)}`}
            {current.exit_code !== null && ` · exit code ${current.exit_code}`}
          </p>
          {Object.keys(current.args).length > 0 && (
            <p className="font-mono text-xs text-muted">
              {Object.entries(current.args)
                .map(([name, value]) => `${name}=${String(value)}`)
                .join("  ")}
            </p>
          )}
        </div>
        {running && (
          <Button
            variant="danger"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate(id)}
            tooltip="Stop this run and everything it started."
          >
            Cancel
          </Button>
        )}
      </div>
      {current.error && <ErrorMessage error={new Error(current.error)} />}
      <ErrorMessage error={cancel.error} />
      <pre
        ref={outputRef}
        className={`${compact ? "max-h-64" : "max-h-[60vh] min-h-48"} overflow-auto rounded-lg border border-zinc-800 bg-black p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-200`}
      >
        {stream.output || (running ? "Waiting for output..." : "(no output)")}
      </pre>
      {current.output_truncated && (
        <p className="text-sm text-amber-400">Output was truncated at 512 KiB.</p>
      )}
    </div>
  );
}
