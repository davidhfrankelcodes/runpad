import assert from "node:assert/strict";
import { test } from "node:test";
import { historyText, okPercent, withCheck, type TileHistory } from "./history.ts";

const history = (buckets: TileHistory["buckets"], ok_percent: number | null = 100): TileHistory => ({
  bucket_seconds: 1800,
  buckets,
  ok_percent,
});

test("a check counts in the last bar only if it is worse", () => {
  assert.deepEqual(withCheck(history(["good", "good"]), "bad").buckets, ["good", "bad"]);
  assert.deepEqual(withCheck(history(["good", "bad"]), "good").buckets, ["good", "bad"]);
  assert.deepEqual(withCheck(history(["good", "good"]), "unknown").buckets, ["good", "unknown"]);
  assert.deepEqual(withCheck(history(["good", "warn"]), "unknown").buckets, ["good", "warn"]);
  assert.deepEqual(withCheck(history([null, null]), "good").buckets, [null, "good"]);
});

test("the share of time rounds down, so a red blip never shows 100%", () => {
  assert.equal(okPercent(100), "100%");
  assert.equal(okPercent(99.99), "99.9%");
  assert.equal(okPercent(87.5), "87.5%");
});

test("the tooltip says what the bars mean", () => {
  assert.equal(
    historyText(history([], 99.31)),
    "The last 24 hours, one bar per half an hour, colored by its worst check. Not red 99.3% of the checked time.",
  );
  assert.match(historyText(history([], null)), /Nothing checked yet\.$/);
});
