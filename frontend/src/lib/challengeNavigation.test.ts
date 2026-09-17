import { afterEach, describe, expect, it, vi } from "vitest";
import type { BattleOut, FormatOut, ProviderOut, TargetDetailOut } from "./api";
import {
  battleCreatedAt, challengeRoles, formatScoring, legacyCustomUrl, legacyTargetUrl,
  forgetChallenge, modelSlots, rememberChallenge, savedChallengeIds, validModelSlots,
} from "./challengeNavigation";

const providers = ["host:a", "host:b", "personal:c"].map(id => ({ id, name: id, model_name: id })) as ProviderOut[];
const target = (id: string, format: string) => ({ id, format }) as TargetDetailOut;

afterEach(() => vi.unstubAllGlobals());

describe("challenge-driven model slots", () => {
  it.each(["authentication-gate", "fullstack-bank-vault", "sql-login-service"])("%s has fixed Builder and Breaker roles", id => {
    expect(challengeRoles(target(id, "builder_breaker"), undefined, "solo")).toEqual(["Builder", "Breaker"]);
    expect(challengeRoles(target(id, "builder_breaker"), undefined, "race")).toEqual(["Builder", "Breaker"]);
  });
  it.each(["broken-package-recovery", "tinyshop", "migration-disaster"])("%s supports one model or a two-model race", id => {
    expect(challengeRoles(target(id, "solo"), undefined, "solo")).toEqual(["Model"]);
    expect(challengeRoles(target(id, "solo"), undefined, "race")).toEqual(["Model A", "Model B"]);
  });
  it("reads roles from preset contracts and excludes the judge", () => {
    expect(challengeRoles(null, { roles: ["builder", "breaker", "judge"] } as FormatOut, "solo")).toEqual(["builder", "breaker"]);
    expect(challengeRoles(null, { config: JSON.stringify({ roles: ["solver", "judge"] }) } as FormatOut, "solo")).toEqual(["solver"]);
    expect(challengeRoles(null, undefined, "solo")).toEqual([]);
  });
  it("preserves selected models when adding or removing slots", () => {
    expect(modelSlots(["host:b"], providers, 2)).toEqual(["host:b", "host:a"]);
    expect(modelSlots(["host:b", "host:a"], providers, 1)).toEqual(["host:b"]);
  });
  it("does not invent models or fill missing slots with duplicates", () => {
    expect(modelSlots([], [], 2)).toEqual(["", ""]);
    expect(modelSlots([], providers.slice(0, 1), 2)).toEqual(["host:a", ""]);
    expect(validModelSlots(["host:a", "host:a"], providers, 2)).toBe(false);
    expect(validModelSlots(["host:made-up"], providers, 1)).toBe(false);
    expect(validModelSlots(["host:a", "host:b"], providers, 2)).toBe(true);
    expect(validModelSlots([], providers, 0)).toBe(false);
  });
});

describe("legacy bookmarks", () => {
  it("redirects custom setup and keeps scoring, template and draft selection", () => {
    const url = new URL(legacyCustomUrl("?mode=verified&draft=d1&source=custom"), "https://example.test");
    expect(url.pathname).toBe("/battles/new");
    expect(Object.fromEntries(url.searchParams)).toEqual({ mode: "verified", draft: "d1", custom: "1" });
    expect(legacyCustomUrl("")).toBe("/battles/new?custom=1");
  });
  it("redirects target library and detail links without losing search/hash", () => {
    expect(legacyTargetUrl("/targets")).toBe("/challenges");
    expect(legacyTargetUrl("/targets/authentication-gate", "?version=1", "#objectives")).toBe("/challenges/authentication-gate?version=1#objectives");
    expect(legacyTargetUrl("/targets-other")).toBe("/targets-other");
  });
});

describe("honest metadata", () => {
  it("does not turn unknown scoring into a verified label", () => {
    expect(formatScoring({ config: {} } as FormatOut)).toBe("Scoring defined by template");
    expect(formatScoring({ config: { judge_only: true } } as FormatOut)).toBe("Judge-scored");
    expect(formatScoring({ config: JSON.stringify({ test_code: "assert True" }) } as FormatOut)).toBe("Test-scored");
  });
  it("sorts actual creation dates, not time limits", () => {
    expect(battleCreatedAt({ created_at: 1_789_600_000 } as BattleOut)).toBe(1_789_600_000_000);
    expect(battleCreatedAt({ created_at: "2026-09-16T12:00:00Z" } as BattleOut)).toBe(Date.parse("2026-09-16T12:00:00Z"));
    expect(battleCreatedAt({ created_at: "invalid" } as BattleOut)).toBe(0);
    expect(battleCreatedAt({} as BattleOut)).toBe(0);
  });
});

describe("saved challenge links", () => {
  it("stores only deduplicated IDs per user, not a client-authoritative spec", () => {
    const entries = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (key: string) => entries.get(key) ?? null, setItem: (key: string, value: string) => entries.set(key, value) });
    expect(rememberChallenge("u1", "d1")).toBe(true);
    rememberChallenge("u1", "d2");
    rememberChallenge("u1", "d1");
    expect(savedChallengeIds("u1")).toEqual(["d1", "d2"]);
    expect(savedChallengeIds("u2")).toEqual([]);
    expect(entries.get("seekharness_challenges:u1")).toBe('["d1","d2"]');
    forgetChallenge("u1", "d1");
    expect(savedChallengeIds("u1")).toEqual(["d2"]);
  });
  it("handles corrupt or blocked browser storage without pretending a save succeeded", () => {
    vi.stubGlobal("localStorage", { getItem: () => "{bad json", setItem: () => { throw new Error("blocked"); } });
    expect(savedChallengeIds("u1")).toEqual([]);
    expect(rememberChallenge("u1", "d1")).toBe(false);
  });
});
