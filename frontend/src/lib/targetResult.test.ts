import { describe, expect, it } from "vitest";
import {
  isAuthoritativeScoresEvent,
  targetResultPresentation,
  verificationLabel,
} from "./targetResult";

describe("target result truth", () => {
  it("renders trusted verified_fail as verified fail without a winner", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        scores: { "host:modal-kimi": 0 },
        winner: "host:modal-kimi",
        verified_solution: false,
        verification_status: "verified_fail",
        termination_reason: "TURN_BUDGET_EXCEEDED",
      },
    });
    expect(view.statusLabel).toBe("Verified fail");
    expect(view.verificationLabel).toBe("Verified fail");
    expect(view.showCompetitiveWinner).toBe(false);
    expect(view.winnerId).toBeNull();
    expect(view.scores).toEqual({ "host:modal-kimi": 0 });
  });

  it("uses authoritative score 0 instead of an untrusted judge score", () => {
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
    expect(view.statusLabel).toBe("Unverified");
  });

  it("shows a winner only after trusted verification passes", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        scores: { "host:modal-kimi": 1 },
        winner: "host:modal-kimi",
        verified_solution: true,
        verification_status: "verified_pass",
      },
    });
    expect(view.statusLabel).toBe("Verified pass");
    expect(view.showCompetitiveWinner).toBe(true);
  });

  it("labels not_attempted as verification not completed", () => {
    expect(verificationLabel("not_attempted", false)).toBe("Verification not completed");
  });

  it("ignores judge score events that are not authoritative", () => {
    expect(isAuthoritativeScoresEvent({})).toBe(false);
    expect(isAuthoritativeScoresEvent({ authoritative: true })).toBe(true);
    expect(isAuthoritativeScoresEvent({ source: "arena-score-v1" })).toBe(true);
  });

  it("keeps infrastructure failure distinct from unverified and failed", () => {
    const view = targetResultPresentation({
      status: "completed",
      isTargetBattle: true,
      result: {
        verification_status: "infra_failure",
        verified_solution: false,
      },
    });
    expect(view.statusLabel).toBe("Infrastructure failure");
    expect(view.verificationLabel).toBe("Verification infrastructure failure");
    expect(view.showCompetitiveWinner).toBe(false);
  });

  it("does not fabricate a winner for cancelled or failed battles", () => {
    for (const status of ["failed", "cancelled"] as const) {
      const view = targetResultPresentation({
        status,
        isTargetBattle: true,
        result: { winner: "host:modal-kimi", scores: { "host:modal-kimi": 1 } },
      });
      expect(view.showCompetitiveWinner).toBe(false);
      expect(view.winnerId).toBeNull();
    }
  });
});
