export type VerificationStatus =
  | "verified_pass"
  | "verified_fail"
  | "not_attempted"
  | "infra_failure"
  | "unverified"
  | "policy_invalid"
  | string;

export type AuthoritativeBattleResult = {
  scores?: Record<string, number> | null;
  winner?: string | null;
  verified_solution?: boolean | null;
  verification_status?: VerificationStatus | null;
  termination_reason?: string | null;
  outcome?: string | null;
};

export type TargetResultView = {
  statusLabel: string;
  statusTone: "live" | "verified" | "unverified" | "other";
  showCompetitiveWinner: boolean;
  winnerId: string | null;
  scores: Record<string, number> | null;
  verificationLabel: string;
  terminalOutcome: string | null;
};

function isVerifiedPass(result: AuthoritativeBattleResult): boolean {
  return result.verified_solution === true || result.verification_status === "verified_pass";
}

export function verificationLabel(status?: VerificationStatus | null, verifiedSolution?: boolean | null): string {
  if (verifiedSolution === true || status === "verified_pass") return "Verified";
  if (status === "verified_fail") return "Unverified";
  if (status === "infra_failure") return "Verification infrastructure failure";
  if (status === "not_attempted") return "Verification not completed";
  return "Unverified";
}

export function isAuthoritativeScoresEvent(data: {
  authoritative?: boolean;
  source?: string;
} | null | undefined): boolean {
  if (!data) return false;
  return data.authoritative === true || data.source === "arena-score-v1";
}

export function targetResultPresentation(input: {
  status: string;
  isTargetBattle: boolean;
  result: AuthoritativeBattleResult;
}): TargetResultView {
  const verified = isVerifiedPass(input.result);
  const scores = input.result.scores && Object.keys(input.result.scores).length
    ? input.result.scores
    : null;
  const terminal =
    input.result.termination_reason || input.result.outcome || null;

  if (input.status === "running") {
    return {
      statusLabel: "● Live Execution",
      statusTone: "live",
      showCompetitiveWinner: false,
      winnerId: null,
      scores,
      verificationLabel: "",
      terminalOutcome: null,
    };
  }

  if (input.status !== "completed") {
    return {
      statusLabel: input.status,
      statusTone: "other",
      showCompetitiveWinner: false,
      winnerId: null,
      scores,
      verificationLabel: "",
      terminalOutcome: terminal,
    };
  }

  if (!input.isTargetBattle) {
    return {
      statusLabel: "REPLAY · VERIFIED RESULT",
      statusTone: "verified",
      showCompetitiveWinner: Boolean(input.result.winner),
      winnerId: input.result.winner || null,
      scores,
      verificationLabel: "",
      terminalOutcome: terminal,
    };
  }

  if (verified) {
    return {
      statusLabel: "VERIFIED TARGET RESULT",
      statusTone: "verified",
      showCompetitiveWinner: Boolean(input.result.winner),
      winnerId: input.result.winner || null,
      scores,
      verificationLabel: "Verified",
      terminalOutcome: terminal,
    };
  }

  return {
    statusLabel: "UNVERIFIED TARGET RESULT",
    statusTone: "unverified",
    showCompetitiveWinner: false,
    winnerId: null,
    scores,
    verificationLabel: verificationLabel(input.result.verification_status, input.result.verified_solution),
    terminalOutcome: terminal,
  };
}
