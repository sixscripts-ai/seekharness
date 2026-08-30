import { describe, expect, it } from "vitest";
import {
  isAuthoritativeScoresEvent,
  targetResultPresentation,
  verificationLabel,
} from "./targetResult";

describe("target result truth", () => {
  it("does not render a verified winner for TURN_BUDGET_EXCEEDED + verified_solution=false", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        scores: { "host:modal-kimi": 0 },
        winner: "host:modal-kimi",
        verified_solution: false,
        verification_status: "verified_fail",
        termination_reason: "TURN_BUDGET_EXCEEDED",
        outcome: "TURN_BUDGET_EXCEEDED",
      },
    });
    expect(view.statusLabel).toBe("UNVERIFIED TARGET RESULT");
    expect(view.statusLabel.startsWith("VERIFIED")).toBe(false);
    expect(view.showCompetitiveWinner).toBe(false);
    expect(view.winnerId).toBeNull();
    expect(view.scores).toEqual({ "host:modal-kimi": 0 });
    expect(view.terminalOutcome).toBe("TURN_BUDGET_EXCEEDED");
    expect(view.verificationLabel).toMatch(/Unverified|Verification not completed/i);
  });

  it("uses authoritative score 0 instead of a legacy judge 58", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        scores: { "host:modal-kimi": 0 },
        verified_solution: false,
        verification_status: "not_attempted",
        termination_reason: "TURN_BUDGET_EXCEEDED",
      },
    });
    expect(view.scores?.["host:modal-kimi"]).toBe(0);
    expect(view.showCompetitiveWinner).toBe(false);
    expect(view.statusLabel).toBe("UNVERIFIED TARGET RESULT");
  });

  it("shows a verified winner only after trusted verification passed", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        scores: { "host:modal-kimi": 1 },
        winner: "host:modal-kimi",
        verified_solution: true,
        verification_status: "verified_pass",
        termination_reason: "TEST_PASS",
      },
    });
    expect(view.statusLabel).toBe("VERIFIED TARGET RESULT");
    expect(view.showCompetitiveWinner).toBe(true);
    expect(view.winnerId).toBe("host:modal-kimi");
    expect(view.verificationLabel).toBe("Verified");
  });

  it("labels not_attempted as verification not completed", () => {
    expect(verificationLabel("not_attempted", false)).toBe("Verification not completed");
  });

  it("ignores judge score events that are not authoritative", () => {
    expect(isAuthoritativeScoresEvent({ scores: { a: 58 } } as never)).toBe(false);
    expect(isAuthoritativeScoresEvent({ authoritative: true, source: "arena-score-v1" })).toBe(true);
    expect(isAuthoritativeScoresEvent({ source: "arena-score-v1" })).toBe(true);
  });
});
