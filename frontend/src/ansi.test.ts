import assert from "node:assert/strict";
import { test } from "node:test";
import { parseAnsi, stripAnsi } from "./ansi.ts";

const E = "\x1b";

test("plain text is one unstyled segment", () => {
  assert.deepEqual(parseAnsi("hello\nworld\n"), [{ text: "hello\nworld\n", style: {} }]);
  assert.deepEqual(parseAnsi(""), []);
});

test("colors and styles start and reset", () => {
  const segments = parseAnsi(`ok ${E}[32mPASSED${E}[0m and ${E}[1;31mFAILED${E}[m.`);
  assert.deepEqual(segments, [
    { text: "ok ", style: {} },
    { text: "PASSED", style: { fg: "#4ade80" } },
    { text: " and ", style: {} },
    { text: "FAILED", style: { bold: true, fg: "#f87171" } },
    { text: ".", style: {} },
  ]);
});

test("bright, background, 256-color, and true color", () => {
  const [bright, bg, c256, gray, rgb] = parseAnsi(
    `${E}[93ma${E}[0m${E}[44mb${E}[0m${E}[38;5;208mc${E}[0m${E}[38;5;244md${E}[0m${E}[38;2;10;20;30;48;2;255;255;255me`,
  );
  assert.deepEqual(bright?.style, { fg: "#fde047" });
  assert.deepEqual(bg?.style, { bg: "#60a5fa" });
  assert.deepEqual(c256?.style, { fg: "#ff8700" });
  assert.deepEqual(gray?.style, { fg: "#808080" });
  assert.deepEqual(rgb?.style, { fg: "#0a141e", bg: "#ffffff" });
});

test("partial resets leave the rest", () => {
  const segments = parseAnsi(`${E}[1;4;33mA${E}[22mB${E}[39mC${E}[24mD`);
  assert.deepEqual(
    segments.map((s) => [s.text, s.style]),
    [
      ["A", { bold: true, underline: true, fg: "#facc15" }],
      ["B", { underline: true, fg: "#facc15" }],
      ["C", { underline: true }],
      ["D", {}],
    ],
  );
});

test("other escape sequences are removed", () => {
  // Cursor moves, erase line, window title (OSC with BEL), a link (OSC with ESC \), charset.
  const bel = "\x07";
  const input = `${E}[2K${E}[1Gtitle:${E}]0;my title${bel}${E}]8;;https://x.test${E}\\link${E}]8;;${E}\\ ${E}(Bdone${E}[?25h`;
  assert.equal(stripAnsi(input), "title:link done");
});

test("a line rewritten with carriage returns shows its last version", () => {
  const progress = "Downloading 10%\rDownloading 55%\rDownloading 100%\nDone\n";
  assert.equal(stripAnsi(progress), "Downloading 100%\nDone\n");
  // Windows line endings are just line endings.
  assert.equal(stripAnsi("a\r\nb\r\n"), "a\nb\n");
  // A colored progress line keeps its last color.
  const segments = parseAnsi(`${E}[33m 50%${E}[0m\r${E}[32m100%${E}[0m\n`);
  assert.deepEqual(segments, [
    { text: "100%\n", style: { fg: "#4ade80" } },
  ]);
});

test("real tool output: apt and docker compose", () => {
  const apt = `Reading package lists... 0%\rReading package lists... 100%\rReading package lists... Done\r\n${E}[1;31mE: ${E}[0mUnable to locate package nope\n`;
  assert.equal(stripAnsi(apt), "Reading package lists... Done\nE: Unable to locate package nope\n");
  const compose = `${E}[36mweb-1  | ${E}[0mlistening on :80\n${E}[33mdb-1   | ${E}[0mready\n`;
  const segments = parseAnsi(compose);
  assert.equal(segments[0]?.style.fg, "#22d3ee");
  assert.equal(stripAnsi(compose), "web-1  | listening on :80\ndb-1   | ready\n");
});

test("an escape cut off at the end of streamed output is not shown", () => {
  assert.equal(stripAnsi(`half${E}[3`), "half");
  assert.equal(stripAnsi(`half${E}`), "half");
});
