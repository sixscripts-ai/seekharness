export type BattleSetupDraft = {
  selected: string[];
  runMode: "solo" | "race";
  judgeId: string;
  timeoutSec: number;
  save: boolean;
  visibility: "isolated" | "open";
  difficulty: string;
  contextMode: "strict" | "adaptive";
};

export function setupDraftKey(userId: string, challengeId: string): string {
  return `seekharness_battle_setup:${userId}:${challengeId}`;
}

export function readSetupDraft(key: string): BattleSetupDraft | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) || "null");
    if (!value || typeof value !== "object") return null;
    const draft = value as Partial<BattleSetupDraft>;
    if (!Array.isArray(draft.selected) || !draft.selected.every(id => typeof id === "string")) return null;
    if (draft.runMode !== "solo" && draft.runMode !== "race") return null;
    if (typeof draft.judgeId !== "string" || !Number.isInteger(draft.timeoutSec)) return null;
    if (typeof draft.save !== "boolean" || !["isolated", "open"].includes(draft.visibility || "")) return null;
    if (typeof draft.difficulty !== "string" || !["strict", "adaptive"].includes(draft.contextMode || "")) return null;
    return draft as BattleSetupDraft;
  } catch { return null; }
}

export function writeSetupDraft(key: string, draft: BattleSetupDraft): void {
  try { sessionStorage.setItem(key, JSON.stringify(draft)); } catch { /* Private-mode storage may be unavailable. */ }
}

export function clearSetupDraft(key: string): void {
  try { sessionStorage.removeItem(key); } catch { /* No saved state to clear. */ }
}
