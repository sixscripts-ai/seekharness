import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { BattleOut, FormatOut } from "@/lib/api";
import type { BattleStreamItem } from "./types";
import BattleOverview from "./BattleOverview";

describe("battle overview", () => {
  it("shows a solo sandbox boot failure without a fabricated duel or fighter loss", () => {
    const battle = {
      id: "b1", target_id: "broken-package-recovery", model_ids: ["host:modal-kimi"], status: "failed",
      failure_reason: "SANDBOX_BOOT_FAILURE", verification_status: "infra_failure",
      winner: "host:modal-kimi", verified_solution: false,
      battle_config: { format: "solo", runtime: "node22", roles: ["fighter"], battle_plan: { phases: [{ phase_id: "solve" }] } },
    } as BattleOut;
    const html = renderToStaticMarkup(<BattleOverview battle={battle} officialBattle={battle} format={{ name: "Auth System vs Breaker" } as FormatOut} target={null} status="failed" events={[]} modelName={id => id} onDeepDive={() => undefined} />);
    expect(html).toContain("Solo run");
    expect(html).toContain("node22");
    expect(html).toContain("Infrastructure failure");
    expect(html).toContain("Sandbox Boot Failure");
    expect(html).toContain("not a fighter loss");
    expect(html).not.toContain("Auth System vs Breaker");
    expect(html).not.toContain("Quantum Bank Vault");
    expect(html).not.toContain("Verified winner");
  });

  it("links verified result to recorded public verifier summary only", () => {
    const battle = {
      id: "b2", target_id: "tinyshop", model_ids: ["model-a"], status: "completed",
      winner: "model-a", verified_solution: true,
      battle_config: { format: "solo", runtime: "node22" },
      results: [{ model_id: "model-a", phase: "solve", role: "fighter", passed: true, score: 1, verification_status: "verified_pass" }],
    } as BattleOut;
    const events = [{ kind: "verification", phase: "solve", model_id: "model-a", t: 1000, artifact: "", payload: { authoritative: true, source: "trusted_verifier", verification_status: "verified_pass", event_id: "ev-1" } }] as BattleStreamItem[];
    const html = renderToStaticMarkup(<BattleOverview battle={battle} officialBattle={battle} format={null} target={null} status="completed" events={events} modelName={id => id} onDeepDive={() => undefined} />);
    expect(html).toContain("Verified pass");
    expect(html).toContain("Verified winner");
    expect(html).toContain('href="#evidence-event-0"');
    expect(html).toContain("Event ev-1");
    expect(html).not.toContain("hidden_output");
  });
});
