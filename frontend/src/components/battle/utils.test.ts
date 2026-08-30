import { describe, expect, it } from "vitest";
import type { BattleStreamItem } from "./types";
import { skillActivityFromEvent } from "./utils";

function event(kind: BattleStreamItem["kind"], artifact: Record<string, unknown>, extra?: Partial<BattleStreamItem>): BattleStreamItem {
  return {
    kind,
    phase: "race",
    model_id: "model-a",
    artifact: JSON.stringify(artifact),
    t: 1,
    payload: {
      phase: "race",
      model_id: "model-a",
      artifact: JSON.stringify(artifact),
      sequence: 12,
    },
    ...extra,
  };
}

describe("D6 skill activity from real SSE payloads", () => {
  it("reads skill fields from the artifact JSON, not the SSE wrapper", () => {
    const activity = skillActivityFromEvent(event("skill_search", {
      type: "skill_search",
      fighter_id: "model-a",
      query: "session replay",
      event_sequence: 12,
      success: true,
    }));
    expect(activity).toEqual({
      kind: "skill_search",
      modelId: "model-a",
      t: 1,
      skillId: undefined,
      index: undefined,
      query: "session replay",
      success: true,
      eventSequence: 12,
    });
  });

  it("does not infer expertise from terminal/tool text", () => {
    expect(skillActivityFromEvent(event("action_log", {
      action: "use_skill",
      result: "unstructured tool text",
    }))).toBeNull();
  });

  it("does not count a failed skill_load as loaded expertise", () => {
    const failed = skillActivityFromEvent(event("skill_load", {
      type: "skill_load",
      skill_id: "failed-skill",
      success: false,
    }));
    const loaded = skillActivityFromEvent(event("skill_load", {
      type: "skill_load",
      skill_id: "python-kata-fixer",
      success: true,
    }));
    expect(failed?.success).toBe(false);
    expect(failed?.skillId).toBe("failed-skill");
    expect(loaded?.success).toBe(true);
    expect(loaded?.skillId).toBe("python-kata-fixer");
  });

  it("treats a skill_load without an explicit success flag as not loaded", () => {
    const activity = skillActivityFromEvent(event("skill_load", {
      type: "skill_load",
      skill_id: "ambiguous-skill",
    }));
    expect(activity?.success).toBe(false);
  });
});
