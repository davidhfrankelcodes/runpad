import assert from "node:assert/strict";
import { test } from "node:test";
import { since } from "./format.ts";

const NOW = Date.parse("2026-10-19T12:00:00Z");
const before = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

test("since counts up in steps short enough for a button", () => {
  assert.equal(since(before(5), NOW), "just now");
  assert.equal(since(before(5 * 60 + 30), NOW), "5 min ago");
  assert.equal(since(before(3 * 3600 + 10), NOW), "3 h ago");
  assert.equal(since(before(2 * 86400 + 60), NOW), "2 d ago");
  assert.equal(since(before(29 * 86400), NOW), "29 d ago");
});

test("since gives a date after a month, and never counts down", () => {
  assert.equal(since(before(40 * 86400), NOW), new Date(NOW - 40 * 86400 * 1000).toLocaleDateString());
  assert.equal(since(new Date(NOW + 60_000).toISOString(), NOW), "just now");
});
