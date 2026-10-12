import type { TileState } from "./pads";

/** What each State tone means, for tooltips. */
export const TONE_MEANING: Record<TileState["tone"], string> = {
  good: "Green: as it should be.",
  warn: "Amber: working, but needs attention soon, such as a disk filling up.",
  bad: "Red: stopped, down, or missing.",
  neutral: "Blue: in between, such as starting or partly up.",
  unknown: "Grey: the last check could not tell.",
};

/** The dot shown next to a State's value. */
export const TONE_DOT: Record<TileState["tone"], string> = {
  good: "bg-emerald-400",
  warn: "bg-amber-400",
  bad: "bg-red-500",
  neutral: "bg-sky-400",
  unknown: "bg-zinc-500",
};
