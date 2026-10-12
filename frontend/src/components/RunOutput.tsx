import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import { useCancelRun, useRerun, useRun, type RunDetail } from "../actions";
import { parseAnsi, type Style } from "../ansi";
import { duration } from "../format";
import { useRunStream } from "../runStream";
import { RunStatus } from "./RunStatus";
import { Button, CopyButton, ErrorMessage } from "./ui";

/** A file name like "restart-plex-2026-10-11-1432.txt", from the action and start time. */
function outputFileName(actionName: string, startedAt: string): string {
  const slug = actionName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "run";
  const started = new Date(startedAt);
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${started.getFullYear()}-${pad(started.getMonth() + 1)}-${pad(started.getDate())}-${pad(started.getHours())}${pad(started.getMinutes())}`;
  return `${slug}-${stamp}.txt`;
}

function download(text: string, fileName: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

// The terminal's own colors, which ANSI "default" and inverse fall back to.
const TERMINAL_FG = "#e4e4e7";
const TERMINAL_BG = "#000000";

function css(style: Style): CSSProperties {
  const fg = style.inverse ? (style.bg ?? TERMINAL_BG) : style.fg;
  const bg = style.inverse ? (style.fg ?? TERMINAL_FG) : style.bg;
  return {
    color: fg,
    backgroundColor: bg,
    fontWeight: style.bold ? 700 : undefined,
    opacity: style.dim ? 0.7 : undefined,
    fontStyle: style.italic ? "italic" : undefined,
    textDecoration: style.underline ? "underline" : undefined,
  };
}

/** A Run's status and live output, with a Cancel button while it runs. */
export function RunOutput({
  id,
  compact = false,
  onRerun,
}: {
  id: string;
  compact?: boolean;
  /** Called with the new Run after "Run again"; without it the button is not shown. */
  onRerun?: (run: RunDetail) => void;
}) {
  const run = useRun(id);
  const stream = useRunStream(id);
  const cancel = useCancelRun();
  const rerun = useRerun();
  const outputRef = useRef<HTMLPreElement>(null);

  // Keep the newest output in view.
  useEffect(() => {
    const element = outputRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [stream.output]);

  // Terminal colors become styled text; copies and downloads get the plain text.
  const segments = useMemo(() => parseAnsi(stream.output), [stream.output]);
  const plain = useMemo(() => segments.map((segment) => segment.text).join(""), [segments]);

  const current = stream.end ?? run.data;
  if (!current) return <ErrorMessage error={run.error} />;
  const running = current.status === "running";
  // Whether you may run it again comes from the run's own page, not the stream.
  const again = run.data?.rerun;
  const argText = Object.entries(current.args)
    .map(([name, value]) => `${name}=${String(value)}`)
    .join(", ");

  function runAgain() {
    if (!again || !onRerun || !current) return;
    if (again.confirm && !window.confirm(`Run ${current.action_name} again? It asks for confirmation first.`)) {
      return;
    }
    rerun.mutate(id, { onSuccess: onRerun });
  }

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
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          <CopyButton
            value={plain}
            disabled={!stream.output}
            tooltip={
              running
                ? "Copy the output so far to the clipboard."
                : "Copy the whole output to the clipboard."
            }
          />
          <Button
            variant="secondary"
            disabled={!stream.output}
            onClick={() =>
              download(plain, outputFileName(current.action_name, current.started_at))
            }
            tooltip={
              running
                ? "Save the output so far as a text file."
                : "Save the whole output as a text file."
            }
          >
            Download
          </Button>
          {!running && again && onRerun && (
            <Button
              variant="secondary"
              disabled={rerun.isPending}
              onClick={runAgain}
              tooltip={
                argText
                  ? `Run ${current.action_name} again with the same arguments: ${argText}.`
                  : `Run ${current.action_name} again.`
              }
            >
              <span className="flex items-center gap-1.5">
                <svg
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />
                </svg>
                Run again
              </span>
            </Button>
          )}
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
      </div>
      {current.error && <ErrorMessage error={new Error(current.error)} />}
      <ErrorMessage error={cancel.error ?? rerun.error} />
      <pre
        ref={outputRef}
        className={`${compact ? "max-h-64" : "max-h-[60vh] min-h-48"} overflow-auto rounded-lg border border-zinc-800 bg-black p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-200`}
      >
        {segments.length
          ? segments.map((segment, index) =>
              Object.keys(segment.style).length ? (
                <span key={index} style={css(segment.style)}>
                  {segment.text}
                </span>
              ) : (
                segment.text
              ),
            )
          : running
            ? "Waiting for output..."
            : "(no output)"}
      </pre>
      {current.output_truncated && (
        <p className="text-sm text-amber-400">Output was truncated at 512 KiB.</p>
      )}
    </div>
  );
}
