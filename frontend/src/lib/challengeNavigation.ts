import { formatConfig, type FormatOut, type BattleOut, type TargetDetailOut, type ProviderOut } from "./api";

export function formatScoring(format: FormatOut): string {
  const config = formatConfig(format);
  if (config.evaluation_mode === "judge_only" || config.judge_only === true) return "Judge-scored";
  if (config.test_code || config.verification?.visible_command) return "Test-scored";
  return "Scoring defined by template";
}

export function challengeRoles(target: TargetDetailOut | null, format: FormatOut | undefined, runMode: "solo" | "race"): string[] {
  if (target?.format === "builder_breaker") return ["Builder", "Breaker"];
  if (target) return runMode === "solo" ? ["Model"] : ["Model A", "Model B"];
  const roles = format?.roles || (format ? formatConfig(format).roles : []);
  return Array.isArray(roles) ? roles.filter((role: string) => role !== "judge") : [];
}

export function modelSlots(previous: string[], providers: ProviderOut[], count: number): string[] {
  const allowed = new Set(providers.map(provider => provider.id));
  const next = previous.slice(0, count).map(id => allowed.has(id) ? id : "");
  while (next.length < count) next.push("");
  return next.map((id, index) => {
    if (id) return id;
    const candidate = providers.find(provider => !next.includes(provider.id));
    next[index] = candidate?.id || "";
    return next[index];
  });
}

export function validModelSlots(selected: string[], providers: ProviderOut[], count: number): boolean {
  return count > 0 && selected.length === count && new Set(selected).size === count &&
    selected.every(id => providers.some(provider => provider.id === id));
}

export function legacyCustomUrl(search: string): string {
  const params = new URLSearchParams(search);
  params.delete("source");
  params.set("custom", "1");
  return "/battles/new?" + params;
}

export function legacyTargetUrl(pathname: string, search = "", hash = ""): string {
  return pathname.replace(/^\/targets(?=\/|$)/, "/challenges") + search + hash;
}

export function battleCreatedAt(battle: BattleOut): number {
  const value = battle.created_at;
  if (typeof value === "number") return value * 1000;
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp : 0;
}

// This index stores identifiers only. The server remains the source of the
// draft, its revision, and its readiness to launch.
export function savedChallengeIds(userId: string): string[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem("seekharness_challenges:" + userId) || "[]");
    return Array.isArray(values) ? values.filter((v): v is string => typeof v === "string").slice(0, 50) : [];
  } catch { return []; }
}

export function rememberChallenge(userId: string, draftId: string): boolean {
  try {
    localStorage.setItem("seekharness_challenges:" + userId,
      JSON.stringify([draftId, ...savedChallengeIds(userId).filter(id => id !== draftId)].slice(0, 50)));
    return true;
  } catch { return false; }
}

export function forgetChallenge(userId: string, draftId: string): void {
  try {
    localStorage.setItem("seekharness_challenges:" + userId,
      JSON.stringify(savedChallengeIds(userId).filter(id => id !== draftId)));
  } catch { /* Migration is best effort; the account record is authoritative. */ }
}
