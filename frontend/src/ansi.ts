/** Terminal output to styled text: ANSI colors and text styles (SGR), with every other escape
 * sequence (cursor movement, erasing, titles, links) removed, and lines rewritten with a
 * carriage return (progress bars) shown as their last version. */

export type Style = {
  fg?: string;
  bg?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
  inverse?: boolean;
};

export type Segment = { text: string; style: Style };

// Tuned for the run output's black background: "black" stays visible, and every color
// reads against black.
const PALETTE = [
  "#52525b", "#f87171", "#4ade80", "#facc15", "#60a5fa", "#e879f9", "#22d3ee", "#e4e4e7",
  "#71717a", "#fca5a5", "#86efac", "#fde047", "#93c5fd", "#f0abfc", "#67e8f9", "#ffffff",
];
const CUBE = [0, 95, 135, 175, 215, 255];

function hex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0")).join("")}`;
}

/** One of the 256 xterm colors. */
function color256(n: number): string | undefined {
  if (n < 0 || n > 255 || !Number.isInteger(n)) return undefined;
  if (n < 16) return PALETTE[n];
  if (n < 232) {
    const i = n - 16;
    return hex(CUBE[Math.floor(i / 36)] ?? 0, CUBE[Math.floor(i / 6) % 6] ?? 0, CUBE[i % 6] ?? 0);
  }
  const gray = 8 + 10 * (n - 232);
  return hex(gray, gray, gray);
}

/** Apply one SGR ("ESC [ ... m") parameter list to a style. */
function applySgr(style: Style, params: number[]): Style {
  let next = { ...style };
  const codes = params.length ? params : [0];
  for (let i = 0; i < codes.length; i++) {
    const code = codes[i] ?? 0;
    if (code === 0) next = {};
    else if (code === 1) next.bold = true;
    else if (code === 2) next.dim = true;
    else if (code === 3) next.italic = true;
    else if (code === 4) next.underline = true;
    else if (code === 7) next.inverse = true;
    else if (code === 22) next = { ...next, bold: undefined, dim: undefined };
    else if (code === 23) next.italic = undefined;
    else if (code === 24) next.underline = undefined;
    else if (code === 27) next.inverse = undefined;
    else if (code >= 30 && code <= 37) next.fg = PALETTE[code - 30];
    else if (code === 39) next.fg = undefined;
    else if (code >= 40 && code <= 47) next.bg = PALETTE[code - 40];
    else if (code === 49) next.bg = undefined;
    else if (code >= 90 && code <= 97) next.fg = PALETTE[code - 90 + 8];
    else if (code >= 100 && code <= 107) next.bg = PALETTE[code - 100 + 8];
    else if (code === 38 || code === 48) {
      // 38;5;n (256 colors) or 38;2;r;g;b (true color); 48 for the background.
      let color: string | undefined;
      if (codes[i + 1] === 5) {
        color = color256(codes[i + 2] ?? -1);
        i += 2;
      } else if (codes[i + 1] === 2) {
        color = hex(codes[i + 2] ?? 0, codes[i + 3] ?? 0, codes[i + 4] ?? 0);
        i += 4;
      }
      if (code === 38) next.fg = color;
      else next.bg = color;
    }
  }
  // Only what is set, so equal styles compare equal.
  return Object.fromEntries(Object.entries(next).filter(([, value]) => value !== undefined));
}

function sameStyle(a: Style, b: Style): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof Style>;
  for (const key of keys) if (a[key] !== b[key]) return false;
  return true;
}

const ESC = "\x1b";
const BEL = "\x07";

/** Styled segments of terminal output. Joining their text gives the plain text. */
export function parseAnsi(input: string): Segment[] {
  const lines: Segment[][] = [[]];
  let style: Style = {};
  let text = "";

  const current = () => lines[lines.length - 1] as Segment[];
  const flush = () => {
    if (!text) return;
    const line = current();
    const last = line[line.length - 1];
    if (last && sameStyle(last.style, style)) last.text += text;
    else line.push({ text, style });
    text = "";
  };

  let i = 0;
  while (i < input.length) {
    const ch = input[i] as string;
    if (ch === ESC) {
      flush();
      const kind = input[i + 1];
      if (kind === "[") {
        // CSI: parameters, then one final byte in @..~.
        let end = i + 2;
        while (end < input.length && !/[@-~]/.test(input[end] as string)) end++;
        if (input[end] === "m") {
          const raw = input.slice(i + 2, end);
          if (/^[\d;:]*$/.test(raw)) {
            style = applySgr(style, raw ? raw.split(/[;:]/).map((p) => Number(p || 0)) : []);
          }
        }
        i = end + 1;
      } else if (kind === "]") {
        // OSC (window titles, links): up to BEL or ESC \.
        let end = i + 2;
        while (end < input.length && input[end] !== BEL && !(input[end] === ESC && input[end + 1] === "\\")) end++;
        i = input[end] === BEL ? end + 1 : end + 2;
      } else if (kind === "(" || kind === ")") {
        i += 3; // Character set selection.
      } else {
        i += 2;
      }
      continue;
    }
    if (ch === "\r") {
      if (input[i + 1] === "\n") {
        i++;
        continue; // A Windows line ending: the \n ends the line.
      }
      // The line is about to be written again: keep only what comes next.
      text = "";
      lines[lines.length - 1] = [];
      i++;
      continue;
    }
    if (ch === "\n") {
      flush();
      lines.push([]);
      i++;
      continue;
    }
    if (ch === "\b" || ch === BEL) {
      i++;
      continue;
    }
    text += ch;
    i++;
  }
  flush();

  // One list again, newlines included, with neighbours of the same style merged.
  const segments: Segment[] = [];
  const add = (segment: Segment) => {
    const last = segments[segments.length - 1];
    if (last && sameStyle(last.style, segment.style)) last.text += segment.text;
    else segments.push({ ...segment });
  };
  lines.forEach((line, index) => {
    line.forEach(add);
    if (index < lines.length - 1) {
      // The newline takes the style of the text before it, so it does not split a run.
      const before = line[line.length - 1];
      add({ text: "\n", style: before ? before.style : {} });
    }
  });
  return segments;
}

/** The plain text of terminal output, as copied or downloaded. */
export function stripAnsi(input: string): string {
  return parseAnsi(input)
    .map((segment) => segment.text)
    .join("");
}
