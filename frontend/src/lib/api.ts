declare const __DEFAULT_MODAL_URL__: string;

const BASE = (
  import.meta.env.VITE_MODAL_URL ||
  __DEFAULT_MODAL_URL__
).replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string) {
    super(body || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  const res = await fetch(`${BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  stats: () => request<StatsOut>("/stats"),
  formats: (token?: string | null) =>
    request<FormatOut[]>("/formats", { token }),
  providers: (token: string) => request<ProviderOut[]>("/providers", { token }),
  createProvider: (token: string, body: ProviderCreate) =>
    request<ProviderOut>("/providers", { method: "POST", body, token }),
  deleteProvider: (token: string, id: string) =>
    request<{ ok: boolean; id: string; name?: string }>(`/providers/${id}`, {
      method: "DELETE",
      token,
    }),
  testProviderHealth: (token: string, providerId: string) =>
    request<{
      ok: boolean;
      status: "HEALTHY" | "ERROR";
      status_code?: number;
      latency_ms: number;
      detail?: string | null;
    }>(`/providers/${providerId}/health`, {
      method: "POST",
      token,
    }),
  providerHealth: (
    token: string,
    body: {
      base_url: string;
      api_key: string;
      auth_style: string;
      model?: string;
    },
  ) =>
    request<{ ok: boolean; status_code: number }>("/providers/health", {
      method: "POST",
      body,
      token,
    }),
  createBattle: (token: string, body: BattleCreate) =>
    request<{ id: string; status: string }>("/battles", {
      method: "POST",
      body,
      token,
    }),
  getBattle: (token: string, id: string) =>
    request<BattleOut>(`/battles/${id}`, { token }),
  listBattles: (token: string, saved?: boolean) => {
    const q = saved ? "?saved=true" : "";
    return request<BattleOut[]>(`/battles${q}`, { token });
  },
  cancelBattle: (token: string, id: string) =>
    request<{ id: string; status: string }>(`/battles/${id}/cancel`, {
      method: "POST",
      token,
    }),
  saveBattle: (token: string, id: string) =>
    request<{ id: string; saved: boolean }>(`/battles/${id}/save`, {
      method: "POST",
      token,
    }),
  artifacts: (token: string, id: string) =>
    request<ArtifactOut[]>(`/battles/${id}/artifacts`, { token }),
  createBattleDraft: (token: string, body: BattleDraftCreate) =>
    request<BattleDraftOut>("/battle-drafts", { method: "POST", body, token }),
  getBattleDraft: (token: string, id: string) =>
    request<BattleDraftOut>(`/battle-drafts/${id}`, { token }),
  postDraftMessage: (token: string, id: string, body: { content: string; architect_provider_id?: string | null }) =>
    request<BattleDraftOut>(`/battle-drafts/${id}/messages`, { method: "POST", body, token }),
  patchDraftSpec: (token: string, id: string, body: Partial<BattleSpec>) =>
    request<BattleDraftOut>(`/battle-drafts/${id}/spec`, { method: "PATCH", body, token }),
  launchDraft: (token: string, id: string, body: BattleDraftLaunch) =>
    request<{ id: string; status: string; draft_id: string; spec_hash: string }>(
      `/battle-drafts/${id}/launch`,
      { method: "POST", body, token },
    ),
  targets: (filters: TargetFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.category) params.set("category", filters.category);
    if (filters.difficulty) params.set("difficulty", filters.difficulty);
    if (filters.format) params.set("format", filters.format);
    if (filters.tag) params.set("tag", filters.tag);
    const suffix = params.toString() ? `?${params}` : "";
    return request<TargetSummaryOut[]>(`/targets${suffix}`);
  },
  target: (id: string, token?: string | null) =>
    request<TargetDetailOut>(`/targets/${encodeURIComponent(id)}`, { token }),
  leaderboard: (token: string | null, format = "overall") => {
    const params = new URLSearchParams({ format });
    return request<LeaderboardRow[]>(`/leaderboard?${params}`, { token });
  },
};

export type FormatOut = {
  id: string;
  name: string;
  engine: string;
  description?: string;
  slug?: string;
  roles?: string[];
  config?: any;
};

export type ProviderOut = {
  id: string;
  name: string;
  base_url: string;
  masked_key: string;
  auth_style: string;
  model_name: string;
};

export function isHostProviderId(id: string): boolean {
  return id.startsWith("host:");
}

export function splitProviders(providers: ProviderOut[]) {
  return {
    host: providers.filter((p) => isHostProviderId(p.id)),
    yours: providers.filter((p) => !isHostProviderId(p.id)),
  };
}

export type ProviderCreate = {
  name: string;
  base_url: string;
  api_key: string;
  auth_style: string;
  model_name: string;
};

export type BattleCreate = {
  format_id: string;
  model_ids: string[];
  arena_size?: number;
  timeout_seconds?: number;
  round_visibility?: "isolated" | "open";
  save?: boolean;
  judge_provider_id?: string | null;
  difficulty?: "novice" | "general" | "advanced" | "expert" | null;
  target_id?: string | null;
  target_version?: string | null;
};

export type BattleOut = {
  $id?: string;
  id: string;
  user_id: string;
  format_id: string;
  model_ids: string[];
  arena_size: number;
  status: string;
  timeout_seconds: number;
  round_visibility: string;
  saved: boolean;
  difficulty?: string | null;
  sandbox_id?: string;
  preview_urls?: Record<string, string>;
  draft_id?: string | null;
  battle_config?: {
    custom?: boolean;
    evaluation_mode?: string;
    judge_only?: boolean;
    description?: string;
    spec_hash?: string;
  } | null;
  spec_hash?: string | null;
  title?: string | null;
  custom_title?: string | null;
  ranked?: boolean | null;
  target_id?: string | null;
  target_version?: string | null;
  scores?: Record<string, number> | null;
  winner?: string | null;
  verified_solution?: boolean | null;
  verification_status?: string | null;
  termination_reason?: string | null;
  outcome?: string | null;
  results?: Array<{
    model_id: string;
    phase?: string;
    role?: string;
    passed?: boolean;
    score?: number;
    verification_status?: string;
    termination_reason?: string | null;
  }>;
};

export type BattleSpec = {
  title?: string;
  brief?: string;
  deliverables?: string[];
  constraints?: string[];
  required_artifacts?: string[];
  judge_rubric?: string;
  starter_files?: Record<string, string>;
  test_code?: string | null;
  languages?: string[];
  mode?: "quick" | "verified";
};

export type BattleDraftCreate = {
  mode: "quick" | "verified";
  architect_provider_id?: string | null;
};

export type BattleDraftOut = {
  id: string;
  user_id: string;
  mode: "quick" | "verified";
  transcript: { role: string; content: string; ts?: number }[];
  spec: BattleSpec;
  revision: number;
  status: string;
  launched_battle_id?: string | null;
  architect_error?: string | null;
  spec_hash?: string | null;
  created_at?: number;
  updated_at?: number;
};

export type BattleDraftLaunch = {
  revision: number;
  model_ids: string[];
  timeout_seconds: number;
  save: boolean;
  judge_provider_id?: string | null;
};

export type TargetFilters = {
  category?: string;
  difficulty?: string;
  format?: string;
  tag?: string;
};

export type TargetSummaryOut = {
  id: string;
  name: string;
  description: string;
  category: string;
  difficulty: string;
  format: string;
  runtime: string;
  tags: string[];
  version: string;
  visible_test_count: number;
  hidden_test_count: number;
  handoff_required: boolean;
  verification_type: "visible+hidden" | "hidden_only" | "visible_only" | string;
  network: boolean;
  manifest_hash: string;
};

// The backend gates evaluator-internal detail fields behind optional auth:
// anonymous callers receive null for these; authenticated callers receive the
// full safe public representation.
export type TargetDetailOut = TargetSummaryOut & {
  objectives: string[];
  role_objectives?: Record<string, string[]> | null;
  starter_files: string[] | null;
  visible_tests: string[] | null;
  protected_paths: string[] | null;
  handoff_allowlist: string[] | null;
  limits: {
    max_tool_steps: number;
    exec_timeout_seconds: number;
  } | null;
  safety: {
    scope?: string;
    real_targets?: boolean;
    network_required?: boolean;
    [key: string]: unknown;
  } | null;
};

export type ArtifactOut = { phase: string; model_id: string; artifact: string };
export type LeaderboardRow = {
  model_id: string;
  format_id?: string;
  elo: number;
  games_played: number;
  rank?: number;
  top_skills?: string[];
};
export type StreamEvent = { event: string; data: any };
export type StatsOut = {
  battles_running: number;
  battles_total: number;
  median_duration_s: number | null;
  top_models: { model_id: string; elo: number; games_played: number }[];
};

export async function streamBattle(
  battleId: string,
  token: string,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const seenEventIds = new Set<string>();
  let attempt = 0;
  const maxAttempts = 8;
  let isDone = false;

  while (!isDone && !signal?.aborted && attempt < maxAttempts) {
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
      };

      const res = await fetch(`${BASE}/battles/${battleId}/stream`, {
        headers,
        signal,
      });

      if (res.status === 404 || res.status === 401 || res.status === 403) {
        throw new ApiError(res.status, await res.text());
      }

      if (!res.ok || !res.body) {
        throw new ApiError(res.status, await res.text());
      }

      // Reset backoff on successful HTTP stream open
      attempt = 0;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventName = "message";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop() || "";
        for (const line of parts) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const raw = line.slice(5).trim();
            let data: any = raw;
            try {
              data = JSON.parse(raw);
            } catch {}

            // Deduplicate events to prevent replaying upon reconnect
            const eid =
              data?.event_id ||
              data?.data?.event_id ||
              (data && typeof data === "object"
                ? `${eventName}_${data.created_at || data.ts || data.step || ""}_${data.action || data.tool_name || ""}`
                : null);

            if (eid) {
              if (seenEventIds.has(eid)) continue;
              seenEventIds.add(eid);
            }

            onEvent({ event: eventName, data });

            if (eventName === "done") {
              isDone = true;
              return;
            }
            eventName = "message";
          } else if (line === "") {
            eventName = "message";
          }
        }
      }
    } catch (err: any) {
      if (signal?.aborted) return;
      if (
        err instanceof ApiError &&
        (err.status === 401 || err.status === 403 || err.status === 404)
      ) {
        throw err;
      }

      attempt++;
      if (attempt >= maxAttempts) {
        throw err;
      }

      // Exponential backoff: 800ms, 1500ms, 2700ms, max 5000ms
      const delay = Math.min(5000, 800 * Math.pow(1.8, attempt - 1)) + Math.random() * 200;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
}

function formatConfig(format: FormatOut): any {
  if (format.config && typeof format.config === "object") return format.config;
  if (typeof format.config === "string") {
    try {
      return JSON.parse(format.config);
    } catch {
      return {};
    }
  }
  return {};
}

export function playableRoleCount(format: FormatOut): number {
  if (Array.isArray(format.roles) && format.roles.length)
    return format.roles.filter((r) => r !== "judge").length;
  const cfg = formatConfig(format);
  const roles = (cfg.roles as string[]) || ["a", "b", "judge"];
  return roles.filter((r) => r !== "judge").length;
}

/**
 * A format runs the real in-sandbox toolbelt (AdvancedExecutor) when its engine
 * is `agent_tool_race`, or its config opts in with `universal` / `battle_plan`.
 * These formats stream tool activity (action_log) to the Tools tab.
 */
export function isToolUsingFormat(format: FormatOut): boolean {
  if (format.engine === "agent_tool_race") return true;
  const cfg = formatConfig(format);
  return Boolean(cfg.universal || cfg.battle_plan || cfg.custom);
}

export function isCustomFormat(format: FormatOut): boolean {
  const cfg = formatConfig(format);
  return Boolean(cfg.custom || cfg.require_draft || format.name === "Custom prompt battle");
}
