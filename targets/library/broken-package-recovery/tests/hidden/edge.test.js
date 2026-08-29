import test from "node:test";
import assert from "node:assert/strict";
import { summarize } from "../../src/index.js";

test("drops blank values and stringifies values", () => {
  assert.equal(summarize(["", "  ", 7, "x"]), "2: 7, x");
});

test("handles empty input", () => {
  assert.equal(summarize([]), "0: ");
});
