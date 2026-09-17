import { afterEach, describe, expect, it, vi } from "vitest";
import { clearSetupDraft, readSetupDraft, setupDraftKey, writeSetupDraft } from "./battleSetupDraft";

afterEach(() => vi.unstubAllGlobals());

describe("battle setup restoration", () => {
  it("retains model choices and settings per account and challenge", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("sessionStorage", { getItem: (key: string) => values.get(key) || null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
    const key = setupDraftKey("owner", "target:tinyshop");
    const draft = { selected: ["a", "b"], runMode: "race" as const, judgeId: "", timeoutSec: 600, save: true, visibility: "isolated" as const, difficulty: "general", contextMode: "strict" as const };
    writeSetupDraft(key, draft);
    expect(readSetupDraft(key)).toEqual(draft);
    expect(readSetupDraft(setupDraftKey("other", "target:tinyshop"))).toBeNull();
    clearSetupDraft(key);
    expect(readSetupDraft(key)).toBeNull();
  });

  it("rejects malformed or unavailable session storage", () => {
    vi.stubGlobal("sessionStorage", { getItem: () => '{bad', setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } });
    expect(readSetupDraft("x")).toBeNull();
    expect(() => writeSetupDraft("x", { selected: [], runMode: "solo", judgeId: "", timeoutSec: 600, save: false, visibility: "isolated", difficulty: "general", contextMode: "strict" })).not.toThrow();
    expect(() => clearSetupDraft("x")).not.toThrow();
  });
});
