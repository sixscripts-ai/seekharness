import { describe, expect, it } from "vitest";
import type { BattleDraftOut, BattleTemplate, FormatOut, TargetSummaryOut } from "./api";
import { buildChallengeCatalog, challengeCatalogPath } from "./challengeCatalog";

const target = {
  id: "authentication-gate",
  name: "Authentication Gate",
  description: "Secure the authentication service.",
  format: "builder_breaker",
  runtime: "python311-fastapi",
  difficulty: "advanced",
} as TargetSummaryOut;

const format = {
  id: "format-1",
  name: "Debugging race",
  description: "Repair the same program.",
  config: { test_code: "assert True" },
} as FormatOut;

const template = {
  id: "template-1",
  title: "API reliability",
  brief: "Build a resilient API.",
  category: "backend",
  mode: "verified",
} as BattleTemplate;

const draft = {
  id: "draft-1",
  mode: "quick",
  status: "ready",
  spec: { title: "My saved task", brief: "A private account challenge." },
} as BattleDraftOut;

describe("challenge catalog sections", () => {
  it("keeps account-owned drafts out of the Official catalog", () => {
    const entries = buildChallengeCatalog("official", {
      targets: [target], formats: [format], templates: [template], drafts: [draft],
    });

    expect(entries.map(entry => entry.key)).toEqual([
      "target:authentication-gate",
      "format:format-1",
      "template:template-1",
    ]);
    expect(entries.some(entry => entry.key === "draft:draft-1")).toBe(false);
  });

  it("shows only the signed-in user's saved drafts in the User catalog", () => {
    const entries = buildChallengeCatalog("user", {
      targets: [target], formats: [format], templates: [template], drafts: [draft],
    });

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({
      key: "draft:draft-1",
      title: "My saved task",
      href: "/battles/new?custom=1&draft=draft-1",
    });
  });

  it("gives each catalog a stable page URL", () => {
    expect(challengeCatalogPath("official")).toBe("/challenges/official");
    expect(challengeCatalogPath("user")).toBe("/challenges/user");
  });
});
