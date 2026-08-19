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

export function isHostProviderId(id: string): boolean {
  return id.startsWith("host:");
}

export type ProviderOut = {
  id: string;
  name: string;
  base_url: string;
  masked_key: string;
  auth_style: string;
  model_name: string;
};

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
  arena_size: number;
  timeout_seconds: number;
  round_visibility: "isolated" | "open";
  save: boolean;
  judge_provider_id?: string | null;
};

export type BattleOut = {
  $id?: string;
  id?: string;
  user_id: string;
  format_id: string;
  model_ids: string[];
  arena_size: number;
  status: string;
  timeout_seconds: number;
  round_visibility: string;
  saved: boolean;
  sandbox_id?: string;
  preview_urls?: Record<string, string>;
};

export type ArtifactOut = { phase: string; model_id: string; artifact: string };
export type LeaderboardRow = {
  model_id: string;
  format_id?: string;
  elo: number;
  games_played: number;
  rank?: number;
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
  const res = await fetch(`${BASE}/battles/${battleId}/stream`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());
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
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        let data: any = raw;
        try {
          data = JSON.parse(raw);
        } catch {}
        onEvent({ event: eventName, data });
        eventName = "message";
      } else if (line === "") eventName = "message";
    }
  }
}

export function playableRoleCount(format: FormatOut): number {
  if (Array.isArray(format.roles) && format.roles.length)
    return format.roles.filter((r) => r !== "judge").length;
  let cfg: any = {};
  if (typeof format.config === "string") {
    try {
      cfg = JSON.parse(format.config);
    } catch {
      cfg = {};
    }
  } else if (format.config && typeof format.config === "object")
    cfg = format.config;
  const roles = (cfg.roles as string[]) || ["a", "b", "judge"];
  return roles.filter((r) => r !== "judge").length;
}
