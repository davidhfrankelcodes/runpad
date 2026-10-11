import type { RunSummary } from "./actions";

export function duration(run: Pick<RunSummary, "started_at" | "finished_at">): string {
  if (!run.finished_at) return "";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}
