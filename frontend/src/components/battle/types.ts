export type BattleStreamItem = {
  phase: string;
  model_id: string;
  artifact: string;
  t: number;
  kind: string;
  payload?: Record<string, unknown>;
};

export type ParsedAction = {
  action: string;
  command: string;
  state: string;
  result: string;
  duration_ms?: number;
  turn_id?: number;
  tool_step?: number;
  tool_call_id?: string;
  event_sequence?: number;
};

export type SkillEventKind =
  | "skill_index_browse"
  | "skill_search"
  | "skill_card_view"
  | "skill_load";

export type SkillActivity = {
  kind: SkillEventKind;
  modelId: string;
  t: number;
  skillId?: string;
  index?: string;
  query?: string;
  success: boolean;
  eventSequence?: number;
};
