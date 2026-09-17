import { describe, expect, it } from "vitest";
import type { BattleOut, FormatOut, TargetDetailOut } from "./api";
import type { BattleStreamItem } from "@/components/battle/types";
import { battleShape, verificationEventIndex } from "./battleOverview";

describe("battle contract and evidence", () => {
  it("uses frozen solo Node contract instead of the carrier format", () => {
    const battle = { target_id: "broken-package-recovery", model_ids: ["host:modal-kimi"], battle_config: { format: "solo", runtime: "node22", roles: ["fighter"], battle_plan: { phases: [{ phase_id: "solve" }] } } } as BattleOut;
    const shape = battleShape(battle, { name: "Auth System vs Breaker" } as FormatOut, null);
    expect(shape.label).toBe("Solo run");
    expect(shape.runtime).toBe("node22");
    expect(shape.roles).toEqual(["fighter"]);
    expect(shape.phases).toEqual(["solve"]);
  });

  it("distinguishes Builder vs Breaker and two-model races", () => {
    const target = { format: "builder_breaker", runtime: "python" } as TargetDetailOut;
    const base = { target_id: "authentication-gate", model_ids: ["a", "b"] } as BattleOut;
    expect(battleShape(base, null, target).label).toBe("Builder vs. Breaker");
    expect(battleShape({ ...base, target_id: "tinyshop", battle_config: { format: "solo", runtime: "node22" } }, null, null).label).toBe("Head-to-head race");
  });

  it("only links result rows to authoritative trusted-verifier events", () => {
    const event = (payload: Record<string, unknown>) => ({ kind: "verification", model_id: "a", phase: "solve", payload }) as BattleStreamItem;
    const events = [event({ verification_status: "verified_pass" }), event({ authoritative: true, source: "judge" }), event({ authoritative: true, source: "trusted_verifier" })];
    expect(verificationEventIndex(events, "a", "solve")).toBe(2);
    expect(verificationEventIndex(events, "b", "solve")).toBe(-1);
  });
});
