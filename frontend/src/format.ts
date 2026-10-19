import type { RunSummary } from "./actions";

export function duration(run: Pick<RunSummary, "started_at" | "finished_at">): string {
  if (!run.finished_at) return "";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** "just now", "5 min ago", "3 h ago", or a date. */
export function ago(timestamp: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(timestamp).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return new Date(timestamp).toLocaleString();
}

/** "just now", "5 min ago", "3 h ago", "2 d ago", or a date: short enough for a button. */
export function since(timestamp: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(timestamp).getTime()) / 1000));
  if (seconds < 86400) return ago(timestamp, now);
  const days = Math.floor(seconds / 86400);
  return days < 30 ? `${days} d ago` : new Date(timestamp).toLocaleDateString();
}
