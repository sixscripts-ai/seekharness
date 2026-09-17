import type { BattleOut, FormatOut, TargetDetailOut } from "./api";
import type { BattleStreamItem } from "@/components/battle/types";

export type BattleShape = {
  label: string;
  runtime: string | null;
  roles: string[];
  phases: string[];
  scoring: string;
};

export function battleShape(battle: BattleOut, format: FormatOut | null, target: TargetDetailOut | null): BattleShape {
  const cfg = battle.battle_config;
  const targetFormat = cfg?.format || target?.format;
  const count = battle.model_ids?.length || 0;
  const phases = (cfg?.battle_plan?.phases || [])
    .map(item => item.phase_id || item.phase_type || "")
    .filter(Boolean);
  const roles = Array.isArray(cfg?.roles) ? cfg.roles.filter(role => role !== "judge") : [];
  if (battle.target_id) {
    const builderBreaker = targetFormat === "builder_breaker";
    return {
      label: builderBreaker ? "Builder vs. Breaker" : count > 1 ? "Head-to-head race" : "Solo run",
      runtime: cfg?.runtime || target?.runtime || null,
      roles: roles.length === count ? roles : builderBreaker ? ["Builder", "Breaker"] : count > 1 ? ["Model A", "Model B"] : ["Fighter"],
      phases,
      scoring: "Trusted target verification",
    };
  }
  return {
    label: battle.custom_title || format?.name || "Battle",
    runtime: null,
    roles: roles.length === count ? roles : Array.from({ length: count }, (_, index) => `Model ${String.fromCharCode(65 + index)}`),
    phases,
    scoring: cfg?.judge_only || cfg?.evaluation_mode === "quick" ? "Judge-scored; no correctness claim" : "Battle scoring",
  };
}

export function verificationEventIndex(events: BattleStreamItem[], modelId: string, phase?: string): number {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const item = events[index];
    if (item.kind !== "verification") continue;
    if (item.model_id !== modelId) continue;
    if (phase && item.phase && item.phase !== phase) continue;
    if (item.payload?.source !== "trusted_verifier" || item.payload.authoritative !== true) continue;
    return index;
  }
  return -1;
}
