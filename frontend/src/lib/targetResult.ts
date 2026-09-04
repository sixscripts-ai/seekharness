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
  statusTone: "live" | "verified" | "failed" | "unverified" | "other";
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
  if (verifiedSolution === true || status === "verified_pass") return "Verified pass";
  if (status === "verified_fail") return "Verified fail";
  if (status === "infra_failure") return "Verification infrastructure failure";
  if (status === "policy_invalid") return "Policy invalid";
  if (status === "not_attempted") return "Verification not completed";
  if (status === "unverified") return "Unverified";
  return status ? status.replace(/[_-]+/g, " ") : "Unverified";
}

export function isAuthoritativeScoresEvent(data: {
  authoritative?: boolean;
  source?: string;
} | null | undefined): boolean {
  if (!data) return false;
  return data.authoritative === true || data.source === "arena-score-v1";
}

const BATTLE_STATUSES = new Set(["queued", "running", "completed", "failed", "cancelled"]);
const TERMINAL_BATTLE_STATUSES = new Set(["completed", "failed", "cancelled"]);

export function isBattleStatus(value: unknown): value is string {
  return typeof value === "string" && BATTLE_STATUSES.has(value);
}

export function isAuthoritativeStatusEvent(
  eventName: string,
  data: { authoritative?: boolean; status?: string; artifact?: string } | string | null | undefined,
): boolean {
  if (eventName === "done") return true;
  if (!data || typeof data !== "object") return false;
  return data.authoritative === true;
}

export function streamBattleStatus(data: unknown): string | null {
  if (isBattleStatus(data)) return data;
  if (!data || typeof data !== "object") return null;
  const rec = data as { status?: unknown; artifact?: unknown };
  if (isBattleStatus(rec.status)) return rec.status;
  if (isBattleStatus(rec.artifact)) return rec.artifact;
  return null;
}

export function isTerminalBattleStatus(status: string | null | undefined): boolean {
  return Boolean(status && TERMINAL_BATTLE_STATUSES.has(status));
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
  const terminal = input.result.termination_reason || input.result.outcome || null;
  const verification = input.result.verification_status || null;

  if (input.status === "running" || input.status === "queued") {
    return {
      statusLabel: input.status === "running" ? "Live execution" : "Queued",
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
      statusLabel: input.status.replace(/[_-]+/g, " "),
      statusTone: input.status === "failed" ? "failed" : "other",
      showCompetitiveWinner: false,
      winnerId: null,
      scores,
      verificationLabel: "",
      terminalOutcome: terminal,
    };
  }

  if (!input.isTargetBattle) {
    return {
      statusLabel: "Completed",
      statusTone: "other",
      showCompetitiveWinner: Boolean(input.result.winner),
      winnerId: input.result.winner || null,
      scores,
      verificationLabel: "",
      terminalOutcome: terminal,
    };
  }

  if (verified) {
    return {
      statusLabel: "Verified pass",
      statusTone: "verified",
      showCompetitiveWinner: Boolean(input.result.winner),
      winnerId: input.result.winner || null,
      scores,
      verificationLabel: "Verified pass",
      terminalOutcome: terminal,
    };
  }

  if (verification === "verified_fail") {
    return {
      statusLabel: "Verified fail",
      statusTone: "failed",
      showCompetitiveWinner: false,
      winnerId: null,
      scores,
      verificationLabel: "Verified fail",
      terminalOutcome: terminal,
    };
  }

  if (verification === "infra_failure") {
    return {
      statusLabel: "Infrastructure failure",
      statusTone: "failed",
      showCompetitiveWinner: false,
      winnerId: null,
      scores,
      verificationLabel: "Verification infrastructure failure",
      terminalOutcome: terminal,
    };
  }

  return {
    statusLabel: "Unverified",
    statusTone: "unverified",
    showCompetitiveWinner: false,
    winnerId: null,
    scores,
    verificationLabel: verificationLabel(verification, input.result.verified_solution),
    terminalOutcome: terminal,
  };
}
