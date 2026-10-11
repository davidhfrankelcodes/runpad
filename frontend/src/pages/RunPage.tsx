import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router";
import { useCancelRun, useRun } from "../actions";
import { RunStatus } from "../components/RunStatus";
import { duration } from "../format";
import { Button, ErrorMessage } from "../components/ui";
import { useRunStream } from "../runStream";

export default function RunPage() {
  const { id = "" } = useParams();
  return <RunView key={id} id={id} />;
}

function RunView({ id }: { id: string }) {
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
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">{current.action_name}</h1>
            <RunStatus status={current.status} />
          </div>
          <p className="text-sm text-zinc-400">
            Started by {current.triggered_by} at {new Date(current.started_at).toLocaleString()}
            {current.finished_at && ` · took ${duration(current)}`}
            {current.exit_code !== null && ` · exit code ${current.exit_code}`}
          </p>
          {Object.keys(current.args).length > 0 && (
            <p className="font-mono text-xs text-zinc-400">
              {Object.entries(current.args)
                .map(([name, value]) => `${name}=${String(value)}`)
                .join("  ")}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {running && (
            <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(id)}>
              Cancel
            </Button>
          )}
          {current.action_id && (
            <Link to={`/runs?action=${current.action_id}`}>
              <Button variant="secondary">History</Button>
            </Link>
          )}
        </div>
      </div>
      {current.error && <ErrorMessage error={new Error(current.error)} />}
      <ErrorMessage error={cancel.error} />
      <pre
        ref={outputRef}
        className="max-h-[60vh] min-h-48 overflow-auto rounded-lg border border-zinc-800 bg-black p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-200"
      >
        {stream.output || (running ? "Waiting for output..." : "(no output)")}
      </pre>
      {current.output_truncated && (
        <p className="text-sm text-amber-400">Output was truncated at 512 KiB.</p>
      )}
    </div>
  );
}
