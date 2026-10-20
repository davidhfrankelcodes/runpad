import type { PadTile, TileState } from "./pads";

export type TileHistory = PadTile["history"];
type Tone = TileState["tone"];

// Worst first: a bar shows the worst tone checked in its half hour.
const SEVERITY: Tone[] = ["bad", "warn", "unknown", "neutral", "good"];

function worse(a: Tone | null, b: Tone): Tone {
  return a !== null && SEVERITY.indexOf(a) < SEVERITY.indexOf(b) ? a : b;
}

/** The history with a new check counted in its last (current) bar, as a State event arrives.
 * The share of time is the server's; it catches up when the tile is fetched again. */
export function withCheck(history: TileHistory, tone: Tone): TileHistory {
  const buckets = [...history.buckets];
  const last = buckets.length - 1;
  if (last >= 0) buckets[last] = worse(buckets[last] ?? null, tone);
  return { ...history, buckets };
}

/** "99.8%": rounded down, so a tile that was ever red never shows 100%. */
export function okPercent(percent: number): string {
  return `${Math.floor(percent * 10) / 10}%`;
}

/** What the history strip shows, for its tooltip. */
export function historyText(history: TileHistory): string {
  const bar = history.bucket_seconds === 1800 ? "half an hour" : `${history.bucket_seconds / 60} minutes`;
  const share =
    history.ok_percent === null
      ? "Nothing checked yet."
      : `Not red ${okPercent(history.ok_percent)} of the checked time.`;
  return `The last 24 hours, one bar per ${bar}, colored by its worst check. ${share}`;
}
