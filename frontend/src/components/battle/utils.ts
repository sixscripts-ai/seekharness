/* eslint-disable @typescript-eslint/no-explicit-any */
import type { BattleStreamItem, ParsedAction, SkillActivity, SkillEventKind } from "./types";

export const SKILL_EVENTS = new Set<SkillEventKind>([
  "skill_index_browse",
  "skill_search",
  "skill_card_view",
  "skill_load",
]);

export function parseJson(value: unknown): any | null {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function titleCase(value: string): string {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function timeLabel(t: number): string {
  return new Date(t).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortModelName(id: string): string {
  const tail = String(id || "").split(":").pop() || id;
  return titleCase(tail.replace(/^or-/, "").replace(/^host-/, ""));
}

export function displayCommand(raw: any): string {
  if (typeof raw?.command === "string" && raw.command.trim()) return raw.command.trim();
  const action = String(raw?.action || raw?.tool || "event").toLowerCase();
  const target = String(raw?.target || raw?.path || raw?.name || raw?.url || "").trim();
  if (!target) return action;
  if (action === "read") return `cat ${target}`;
  if (action === "write") return `write ${target}`;
  if (action === "run") return `python ${target}`;
  if (action === "test") return target ? `pytest ${target}` : "pytest -q";
  if (action === "ls") return `ls ${target}`;
  if (action === "tree") return `tree ${target}`;
  if (action === "grep") return `grep ${target}`;
  if (action === "fetch") return `fetch ${target}`;
  if (action === "skills") return target ? `skills ${target}` : "skills";
  if (action === "use_skill") return target ? `use_skill ${target}` : "use_skill";
  return `${action} ${target}`.trim();
}

export function parseAction(item: BattleStreamItem): ParsedAction | null {
  if (item.kind !== "action_log") return null;
  const raw = parseJson(item.artifact);
  if (!raw || typeof raw !== "object") return null;
  return {
    action: String(raw.action || raw.tool || "event"),
    command: displayCommand(raw),
    state: String(raw.state || raw.status || "done").toLowerCase(),
    result: String(raw.result || raw.output || raw.stdout || raw.message || ""),
    duration_ms: typeof raw.duration_ms === "number" ? raw.duration_ms : undefined,
    turn_id: typeof raw.turn_id === "number" ? raw.turn_id : undefined,
    tool_step: typeof raw.tool_step === "number" ? raw.tool_step : undefined,
    tool_call_id: typeof raw.tool_call_id === "string" ? raw.tool_call_id : undefined,
    event_sequence: typeof raw.event_sequence === "number" ? raw.event_sequence : undefined,
  };
}

export function actionKey(item: BattleStreamItem): string {
  const action = parseAction(item);
  if (!action) return `${item.kind}:${item.model_id}:${item.t}:${item.artifact.slice(0, 80)}`;
  if (action.tool_call_id) return `call:${action.tool_call_id}`;
  if (action.event_sequence !== undefined) return `seq:${action.event_sequence}`;
  return `${item.model_id}:${item.phase}:${action.action}:${action.command}:${action.tool_step ?? ""}`;
}

export function mergeEvent(previous: BattleStreamItem[], next: BattleStreamItem): BattleStreamItem[] {
  if (next.kind !== "action_log") {
    const nextSequence = typeof next.payload?.event_sequence === "number" ? next.payload.event_sequence : undefined;
    const duplicate = previous.some((item) => {
      if (item.kind !== next.kind || item.model_id !== next.model_id) return false;
      const itemSequence = typeof item.payload?.event_sequence === "number" ? item.payload.event_sequence : undefined;
      if (nextSequence !== undefined && itemSequence !== undefined) return nextSequence === itemSequence;
      return item.t === next.t && item.artifact === next.artifact;
    });
    return duplicate ? previous : [...previous, next];
  }

  const key = actionKey(next);
  const index = previous.findIndex((item) => item.kind === "action_log" && actionKey(item) === key);
  if (index < 0) return [...previous, next];
  const copy = [...previous];
  copy[index] = next;
  return copy;
}

export function artifactFiles(artifact: string): Record<string, string> | null {
  const parsed = parseJson(artifact);
  if (!parsed || typeof parsed !== "object") return null;
  const files = parsed.files;
  if (!files || typeof files !== "object" || Array.isArray(files)) return null;
  const out: Record<string, string> = {};
  for (const [name, content] of Object.entries(files)) {
    if (typeof content === "string") out[name] = content;
  }
  return Object.keys(out).length ? out : null;
}

export function lineDiff(previous: string, current: string) {
  const before = previous.split("\n");
  const after = current.split("\n");
  const max = Math.max(before.length, after.length);
  const rows: { type: "same" | "add" | "remove"; text: string }[] = [];
  for (let i = 0; i < max; i += 1) {
    const a = before[i];
    const b = after[i];
    if (a === b && a !== undefined) rows.push({ type: "same", text: a });
    else {
      if (a !== undefined) rows.push({ type: "remove", text: a });
      if (b !== undefined) rows.push({ type: "add", text: b });
    }
  }
  return rows.slice(0, 700);
}

export function skillActivityFromEvent(item: BattleStreamItem): SkillActivity | null {
  if (!SKILL_EVENTS.has(item.kind as SkillEventKind)) return null;
  // Real D6 fields live in the round artifact JSON. The SSE wrapper only has
  // {phase, model_id, artifact, sequence} and must not be treated as the event body.
  const parsedArtifact = parseJson(item.artifact);
  const wrapper = item.payload && typeof item.payload === "object" ? item.payload : {};
  const payload = {
    ...wrapper,
    ...(parsedArtifact && typeof parsedArtifact === "object" ? parsedArtifact : {}),
  } as Record<string, unknown>;
  return {
    kind: item.kind as SkillEventKind,
    modelId: item.model_id,
    t: item.t,
    skillId: typeof payload.skill_id === "string" ? payload.skill_id : undefined,
    index: typeof payload.index === "string" ? payload.index : undefined,
    query: typeof payload.query === "string" ? payload.query : undefined,
    success: item.kind === "skill_load" ? payload.success === true : payload.success !== false,
    eventSequence: typeof payload.event_sequence === "number" ? payload.event_sequence : undefined,
  };
}

export function humanSkillLabel(skillId: string): string {
  return titleCase(skillId.replace(/\//g, " "));
}
