import test from "node:test";
import assert from "node:assert/strict";
import { summarize } from "../../src/index.js";

test("summarizes trimmed items", () => {
  assert.equal(summarize([" alpha ", "beta"]), "2: alpha, beta");
});
