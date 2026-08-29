/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Boxes,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  ExternalLink,
  RotateCcw,
  Save,
  ShieldCheck,
  Square,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  streamBattle,
  type BattleOut,
  type FormatOut,
  type ProviderOut,
  type StreamEvent,
  type TargetDetailOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import LiveExecutionPane, {
  type BattleStreamItem,
} from "@/components/LiveExecutionPane";
import { cn } from "@/lib/utils";

const TERMINAL_STATES = new Set(["completed", "failed", "cancelled"]);
type DockTab = "activity" | "handoffs" | "evidence" | "judge";

type ParsedAction = {
  battle_id?: string;
  fighter_id?: string;
  role?: string;
  phase_id?: string;
  event_sequence?: number;
  turn_id?: number;
  tool_step?: number;
  tool_call_id?: string;
  exec_id?: string | null;
  action?: string;
  command?: string;
  target?: string;
  state?: string;
  duration_ms?: number;
  result?: string;
  workspace?: string;
};

function parseJson(value: unknown): any | null {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function unwrap(ev: StreamEvent) {
  const wrapped = ev.data as any;
  return wrapped?.data ?? wrapped;
}

function normalizeArtifact(ev: StreamEvent, fallbackPhase: string): BattleStreamItem | null {
  const data = unwrap(ev) as any;
  const wrapped = ev.data as any;
  const raw = data?.artifact ?? wrapped?.artifact ?? data?.message ?? data;
  const modelId = data?.model_id || data?.fighter_id || wrapped?.model_id || wrapped?.fighter_id;
  if (!modelId) return null;
  const phase = data?.phase || data?.phase_id || wrapped?.phase || wrapped?.phase_id || fallbackPhase;
  return {
    phase: phase || "runtime",
    model_id: modelId,
    artifact: typeof raw === "string" ? raw : JSON.stringify(raw ?? ""),
    t: Date.now(),
    kind: ev.event,
  };
}

function parseActionItem(item: BattleStreamItem): ParsedAction | null {
  if (item.kind !== "action_log") return null;
  const parsed = parseJson(item.artifact);
  if (!parsed || typeof parsed !== "object") return null;
  return parsed as ParsedAction;
}

function phaseStartRole(item: BattleStreamItem): string | null {
  if (item.kind !== "phase_start") return null;
  const parsed = parseJson(item.artifact);
  if (parsed && typeof parsed.role === "string") return parsed.role;
  const match = item.artifact.match(/phase_start:([^\s]+)/i);
  return match?.[1] || null;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function timeLabel(t: number): string {
  return new Date(t).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function titleCase(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function providerName(id: string, providers: ProviderOut[]) {
  const found = providers.find((provider) => provider.id === id);
  if (found) return found.model_name || found.name || id;
  if (id.startsWith("host:")) return titleCase(id.replace("host:", ""));
  return id.length > 24 ? `${id.slice(0, 18)}…` : id;
}

function formatConfig(format: FormatOut | null): any {
  if (!format?.config) return {};
  if (typeof format.config === "object") return format.config;
  try {
    return JSON.parse(format.config);
  } catch {
    return {};
  }
}

function configuredPhases(format: FormatOut | null): string[] {
  const cfg = formatConfig(format);
  const plan = cfg?.battle_plan;
  const raw = Array.isArray(plan) ? plan : Array.isArray(plan?.phases) ? plan.phases : [];
  const out = raw
    .map((entry: any) =>
      typeof entry === "string"
        ? entry
        : entry?.phase_id || entry?.id || entry?.name || entry?.phase || "",
    )
    .filter(Boolean)
    .map(String);
  return Array.from(new Set<string>(out as string[]));
}

function displayCommand(action: ParsedAction) {
  if (action.command?.trim()) return action.command.trim();
  const tool = String(action.action || "event").toLowerCase();
  const target = String(action.target || "").trim();
  if (tool === "read") return `cat ${target}`.trim();
  if (tool === "write") return `write ${target}`.trim();
  if (tool === "run") return `python ${target}`.trim();
  if (tool === "test") return target ? `pytest ${target}` : "pytest -q";
  if (tool === "ls") return `ls ${target || "."}`;
  if (tool === "tree") return `tree ${target || "."}`;
  if (tool === "fetch") return `fetch ${target}`.trim();
  return `${tool} ${target}`.trim();
}

function actionKey(item: BattleStreamItem) {
  const action = parseActionItem(item);
  if (!action) return `${item.kind}:${item.model_id}:${item.t}`;
  if (action.tool_call_id) return `tool:${item.model_id}:${action.tool_call_id}`;
  if (action.event_sequence !== undefined) return `seq:${action.event_sequence}`;
  return `${item.model_id}:${item.phase}:${action.turn_id || 0}:${action.tool_step || 0}:${action.action || ""}`;
}

function mergeEvent(previous: BattleStreamItem[], next: BattleStreamItem) {
  if (next.kind !== "action_log") return [...previous, next].slice(-600);
  const key = actionKey(next);
  const index = previous.findIndex((item) => item.kind === "action_log" && actionKey(item) === key);
  if (index === -1) return [...previous, next].slice(-600);
  const copy = [...previous];
  copy[index] = next;
  return copy.slice(-600);
}

export default function LiveBattle() {
  const { id } = useParams<{ id: string }>();
  const { user, jwt, refreshJwt } = useAuth();

  const [battle, setBattle] = useState<BattleOut | null>(null);
  const [format, setFormat] = useState<FormatOut | null>(null);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [events, setEvents] = useState<BattleStreamItem[]>([]);
  const [scores, setScores] = useState<Record<string, number> | null>(null);
  const [status, setStatus] = useState("queued");
  const [phase, setPhase] = useState("runtime");
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [dockTab, setDockTab] = useState<DockTab>("activity");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [targetDetail, setTargetDetail] = useState<TargetDetailOut | null>(null);
  const [showMissionDrawer, setShowMissionDrawer] = useState(false);

  const sessionStartedRef = useRef(Date.now());
  const statusRef = useRef(status);
  const phaseRef = useRef(phase);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    if (TERMINAL_STATES.has(status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => {
    if (!jwt || !id) return;
    let active = true;

    void (async () => {
      try {
        const token = (await refreshJwt()) || jwt;
        const [loadedBattle, loadedFormats, loadedProviders] = await Promise.all([
          api.getBattle(token, id),
          api.formats(token),
          api.providers(token),
        ]);
        if (!active) return;

        setBattle(loadedBattle);
        setStatus(loadedBattle.status);
        setFormat(loadedFormats.find((row) => row.id === loadedBattle.format_id) || null);
        setProviders(loadedProviders);
        if (loadedBattle.preview_urls) setPreviewUrls(loadedBattle.preview_urls);

        if (loadedBattle.target_id) {
          api.target(loadedBattle.target_id, token).then((t) => {
            if (active) setTargetDetail(t);
          }).catch(() => {});
        }

        try {
          const persisted = await api.artifacts(token, id);
          if (!active || !Array.isArray(persisted) || !persisted.length) return;
          const base = Date.now() - persisted.length;
          setEvents((current) => {
            if (current.length) return current;
            return persisted.map((item, index) => ({
              phase: item.phase,
              model_id: item.model_id,
              artifact: item.artifact,
              t: base + index,
              kind: "artifact",
            }));
          });
        } catch {
          // Live SSE remains authoritative when persisted artifacts are unavailable.
        }
      } catch (error) {
        if (active) setErr(error instanceof Error ? error.message : "Battle failed to load");
      }
    })();

    return () => {
      active = false;
    };
  }, [jwt, id, refreshJwt]);

  useEffect(() => {
    if (!jwt || !id || !user) return;
    let cancelled = false;
    const controller = new AbortController();

    const connect = async (attempt = 0): Promise<void> => {
      if (cancelled || TERMINAL_STATES.has(statusRef.current)) return;
      try {
        const token = (await refreshJwt()) || jwt;
        await streamBattle(
          id,
          token,
          (ev: StreamEvent) => {
            if (cancelled) return;
            const data = unwrap(ev) as any;
            const wrapped = ev.data as any;

            if (ev.event === "battle_status" || ev.event === "done") {
              const nextStatus = data?.status || wrapped?.status;
              if (nextStatus) {
                statusRef.current = nextStatus;
                setStatus(nextStatus);
              }
            }

            if (ev.event === "phase_start") {
              const nextPhase = data?.phase || data?.phase_id || wrapped?.phase || wrapped?.phase_id;
              if (nextPhase) {
                phaseRef.current = nextPhase;
                setPhase(nextPhase);
              }
            }

            if (["artifact", "transcript", "action_log", "phase_start"].includes(ev.event)) {
              const item = normalizeArtifact(ev, phaseRef.current);
              if (item) setEvents((previous) => mergeEvent(previous, item));
            }

            if (ev.event === "scores") {
              const direct = data?.scores || wrapped?.scores;
              if (direct) {
                setScores(direct);
              } else {
                const raw = data?.artifact || wrapped?.artifact;
                const parsed = parseJson(raw);
                if (parsed?.scores) setScores(parsed.scores);
                else if (parsed?.data?.scores) setScores(parsed.data.scores);
              }
            }

            if (ev.event === "preview") {
              const modelId = data?.model_id || data?.fighter_id || wrapped?.model_id;
              const url = data?.url || wrapped?.url;
              if (modelId && url) {
                setPreviewUrls((previous) => ({ ...previous, [modelId]: url }));
              }
            }
          },
          controller.signal,
        );

        if (!cancelled && !TERMINAL_STATES.has(statusRef.current)) {
          await new Promise((resolve) =>
            window.setTimeout(resolve, Math.min(1000 * 2 ** attempt, 8000)),
          );
          await connect(Math.min(attempt + 1, 4));
        }
      } catch (error) {
        if (cancelled) return;
        if (attempt < 4) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000 * 2 ** attempt));
          await connect(attempt + 1);
        } else if (!TERMINAL_STATES.has(statusRef.current)) {
          setErr(error instanceof Error ? `Live stream disconnected: ${error.message}` : "Live stream disconnected");
        }
      }
    };

    void connect();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jwt, id, user, refreshJwt]);

  const modelIds = useMemo(() => {
    if (battle?.model_ids && battle.model_ids.length > 0) {
      return battle.model_ids;
    }
    const fromEvents: string[] = [];
    for (const item of events) {
      if (item.model_id && !fromEvents.includes(item.model_id)) {
        fromEvents.push(item.model_id);
      }
    }
    return fromEvents;
  }, [battle?.model_ids, events]);
  const formatRoles = useMemo(
    () => (format?.roles || []).filter((role) => role !== "judge"),
    [format?.roles],
  );

  const runtimeRoles = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of events) {
      const role = phaseStartRole(item);
      if (role) map.set(item.model_id, role);
      const action = parseActionItem(item);
      if (action?.role) map.set(item.model_id, action.role);
    }
    return map;
  }, [events]);

  const roleForModel = (modelId: string, index: number) =>
    runtimeRoles.get(modelId) || formatRoles[index] || `fighter ${index + 1}`;

  const histories = useMemo(() => {
    const map = new Map<string, BattleStreamItem[]>();
    for (const item of events) {
      if (!map.has(item.model_id)) map.set(item.model_id, []);
      map.get(item.model_id)!.push(item);
    }
    return map;
  }, [events]);

  const actionEvents = useMemo(
    () => events.filter((item) => item.kind === "action_log"),
    [events],
  );

  const expectedPhases = useMemo(() => configuredPhases(format), [format]);
  const observedPhases = useMemo(() => {
    const out: string[] = [];
    for (const item of events) if (item.phase && !out.includes(item.phase)) out.push(item.phase);
    if (phase && !out.includes(phase)) out.push(phase);
    return out;
  }, [events, phase]);

  const pipeline = expectedPhases.length ? expectedPhases : observedPhases.length ? observedPhases : [phase];
  const currentPhaseIndex = Math.max(0, pipeline.indexOf(phase));

  const latestActionByModel = useMemo(() => {
    const map = new Map<string, ParsedAction>();
    for (const item of actionEvents) {
      const parsed = parseActionItem(item);
      if (parsed) map.set(item.model_id, parsed);
    }
    return map;
  }, [actionEvents]);

  const latestModelWithAction = actionEvents[actionEvents.length - 1]?.model_id || null;

  function fighterStatus(modelId: string): "waiting" | "starting" | "running" | "complete" | "failed" {
    const latest = latestActionByModel.get(modelId);
    if (status === "failed" && latestModelWithAction === modelId) return "failed";
    if (status === "completed") return "complete";
    if (latest?.state === "failed" || latest?.state === "error") return "failed";
    if (latest?.state === "running" || latest?.state === "starting") return "running";
    const modelEvents = histories.get(modelId) || [];
    if (!modelEvents.length) return "waiting";
    if (latestModelWithAction === modelId && !TERMINAL_STATES.has(status)) return "running";
    return latestModelWithAction && latestModelWithAction !== modelId ? "complete" : "starting";
  }

  const scoreWinner = useMemo(() => {
    if (!scores || !modelIds.length) return null;
    return modelIds.reduce(
      (best, model) => Number(scores[model] ?? -Infinity) > Number(scores[best] ?? -Infinity) ? model : best,
      modelIds[0],
    );
  }, [scores, modelIds]);

  const startAt = events[0]?.t || sessionStartedRef.current;
  const elapsed = formatElapsed(now - startAt);

  const handoffEvents = useMemo(
    () =>
      actionEvents.filter((item) => {
        const parsed = parseActionItem(item);
        const action = String(parsed?.action || "").toLowerCase();
        return action.includes("handoff") || action.includes("snapshot") || action.includes("workspace_destroy");
      }),
    [actionEvents],
  );

  async function cancel() {
    if (!jwt || !id) return;
    setBusy("cancel");
    try {
      const token = (await refreshJwt()) || jwt;
      await api.cancelBattle(token, id);
      statusRef.current = "cancelled";
      setStatus("cancelled");
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Cancel failed");
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!jwt || !id) return;
    setBusy("save");
    try {
      const token = (await refreshJwt()) || jwt;
      await api.saveBattle(token, id);
      setBattle((current) => (current ? { ...current, saved: true } : current));
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  async function copyBattleId() {
    if (!id) return;
    await navigator.clipboard.writeText(id);
    setCopiedId(true);
    window.setTimeout(() => setCopiedId(false), 1200);
  }

  function downloadBattleReplay() {
    const payload = {
      battle_id: id,
      title,
      format_id: battle?.format_id,
      status,
      difficulty: battle?.difficulty,
      round_visibility: battle?.round_visibility,
      spec_hash: battle?.spec_hash || battle?.battle_config?.spec_hash,
      models: modelIds.map((m, idx) => ({
        model_id: m,
        role: roleForModel(m, idx),
        display_name: providerName(m, providers),
      })),
      scores,
      events,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `seekharness_battle_${id || "replay"}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[36ch] space-y-3 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-pink-400">Stream locked</div>
          <p className="text-[14px] text-zinc-400">This battle is private. Log in to watch the live execution stream.</p>
          <Link to="/login" className="btn btn-primary mx-auto h-10 px-6">Log in</Link>
        </div>
      </div>
    );
  }

  const isTargetBattle = Boolean(battle?.target_id);
  const title = isTargetBattle
    ? (targetDetail?.name ? `Target: ${targetDetail.name}` : `Target: ${battle?.target_id}`)
    : (battle?.custom_title || titleCase(battle?.format_id || "Live battle"));

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#040207] text-white">
      {/* Top Banner */}
      <section className="border-b border-pink-500/20 bg-[#08050E]/90 backdrop-blur-md">
        <div className="mx-auto max-w-[1760px] px-6 py-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="truncate text-[22px] font-bold tracking-[-0.03em] md:text-[26px] text-white font-sans">{title}</h1>

                {isTargetBattle && (
                  <Link
                    to={`/targets/${encodeURIComponent(battle?.target_id || "")}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/15 px-3 py-1 font-mono text-[9.5px] font-bold uppercase tracking-wider text-accent shadow-[0_0_10px_rgba(255,0,160,0.25)] hover:bg-accent hover:text-white transition-all"
                  >
                    <Boxes className="h-3 w-3" />
                    <span>Target Briefing</span>
                    <ExternalLink className="h-2.5 w-2.5" />
                  </Link>
                )}

                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.14em]",
                    status === "running"
                      ? "border-pink-500/40 bg-pink-500/10 text-pink-400 shadow-[0_0_12px_rgba(255,0,160,0.3)]"
                      : status === "completed"
                      ? "border-emerald-500/40 bg-emerald-950/40 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.25)]"
                      : "border-white/10 bg-white/5 text-zinc-400",
                  )}
                >
                  {status === "running" ? (
                    <span className="h-1.5 w-1.5 rounded-full bg-pink-400 animate-ping" />
                  ) : null}
                  {status === "completed" ? (
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  ) : null}
                  {status === "running"
                    ? "● Live Execution"
                    : status === "completed"
                    ? (isTargetBattle ? "VERIFIED TARGET RESULT" : "REPLAY · VERIFIED RESULT")
                    : status}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] text-zinc-500">
                <button type="button" onClick={copyBattleId} className="inline-flex items-center gap-1.5 hover:text-pink-400 transition-colors">
                  {copiedId ? <Check className="h-3 w-3 text-pink-400" /> : <Copy className="h-3 w-3" />}
                  <span>{id}</span>
                </button>
                <span>mode://{battle?.round_visibility || "isolated"}</span>
                <span>{elapsed} elapsed</span>
                {battle?.target_version ? (
                  <span className="text-accent">v{battle.target_version}</span>
                ) : battle?.difficulty ? (
                  <span className="text-pink-400/80">{battle.difficulty}</span>
                ) : null}
              </div>
            </div>

            {/* Action Bar */}
            <div className="flex flex-wrap items-center gap-2.5">
              {isTargetBattle && (
                <Link
                  to={`/battles/new?target=${encodeURIComponent(battle?.target_id || "")}`}
                  className="btn h-9 border border-accent/50 bg-accent/15 px-4 font-mono text-[9.5px] font-bold uppercase tracking-[0.12em] text-accent hover:bg-accent hover:text-white transition-all shadow-sm flex items-center gap-1.5"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Rerun Target</span>
                </Link>
              )}
              <button
                type="button"
                onClick={downloadBattleReplay}
                className="btn h-9 border border-pink-500/30 bg-[#0E0918] px-4 font-mono text-[9.5px] font-bold uppercase tracking-[0.12em] text-zinc-200 hover:border-pink-500 hover:bg-pink-500/10 hover:text-pink-400 transition-all shadow-sm"
                title="Download complete telemetry and event replay as JSON"
              >
                <Download className="mr-2 inline h-3.5 w-3.5" />
                Export JSON
              </button>
              <button
                type="button"
                onClick={save}
                disabled={busy === "save" || !!battle?.saved}
                className="btn h-9 border border-white/10 bg-[#0E0918] px-4 font-mono text-[9.5px] font-bold uppercase tracking-[0.12em] text-zinc-300 hover:border-pink-500 hover:text-pink-400 disabled:opacity-40 transition-all"
              >
                <Save className="mr-2 inline h-3.5 w-3.5" />
                {battle?.saved ? "Saved" : "Save replay"}
              </button>
              <button
                type="button"
                onClick={cancel}
                disabled={busy === "cancel" || TERMINAL_STATES.has(status)}
                className="btn h-9 border border-red-500/40 bg-red-500/10 px-4 font-mono text-[9.5px] font-bold uppercase tracking-[0.12em] text-red-400 hover:bg-red-500/20 disabled:opacity-40 transition-all"
              >
                <Square className="mr-2 inline h-3 w-3" /> Halt
              </button>
            </div>
          </div>

          {/* Phase Pipeline */}
          <div className="mt-5 flex items-center gap-0 overflow-x-auto border-t border-white/[0.08] pt-4 font-mono">
            {pipeline.map((item, index) => {
              const active = item === phase;
              const done = index < currentPhaseIndex || (TERMINAL_STATES.has(status) && index <= currentPhaseIndex);
              return (
                <div key={`${item}-${index}`} className="flex min-w-[140px] flex-1 items-center last:flex-none">
                  <div className="min-w-[100px]">
                    <div className={cn(
                      "text-[9px] font-bold uppercase tracking-[0.14em] transition-colors",
                      active ? "text-pink-400 drop-shadow-[0_0_8px_rgba(255,0,160,0.5)]" : done ? "text-emerald-400" : "text-zinc-600",
                    )}>
                      {done ? "✓ " : active ? "● " : ""}{titleCase(item)}
                    </div>
                  </div>
                  {index < pipeline.length - 1 ? (
                    <div className={cn("mx-3 h-0.5 min-w-8 flex-1 rounded-full", done ? "bg-emerald-500/40" : active ? "bg-pink-500" : "bg-white/10")} />
                  ) : null}
                </div>
              );
            })}
          </div>

          {/* Target Mission Drawer */}
          {isTargetBattle && targetDetail && (
            <div className="mt-4 rounded-xl border border-white/[0.08] bg-[#050508] p-3 text-xs mono">
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setShowMissionDrawer(!showMissionDrawer)}
                  className="flex items-center gap-2 font-bold text-accent hover:text-white transition-colors"
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  <span>CHALLENGE OBJECTIVES ({targetDetail.objectives.length})</span>
                  {showMissionDrawer ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                </button>
                <span className="text-[10px] text-zinc-500">
                  {targetDetail.category} · {targetDetail.runtime} · {targetDetail.difficulty}
                </span>
              </div>
              {showMissionDrawer && (
                <div className="mt-3 grid gap-2 border-t border-white/[0.08] pt-3 text-zinc-300 sm:grid-cols-2">
                  {targetDetail.objectives.map((obj, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      <span className="text-accent font-bold">✓</span>
                      <span className="leading-snug">{obj}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Official Completed Verdict Banner */}
      {status === "completed" && (
        <div className="mx-auto max-w-[1760px] px-6 pt-6">
          <div className="rounded-xl border border-emerald-500/40 bg-[#09090E] p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                <span className="mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  {isTargetBattle
                    ? `TARGET BENCHMARK VERDICT · ${targetDetail?.name || battle?.target_id} (v${battle?.target_version || "1.0.0"})`
                    : "OFFICIAL MATCH VERDICT · VERIFIED REPLAY"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {isTargetBattle && (
                  <Link
                    to={`/battles/new?target=${encodeURIComponent(battle?.target_id || "")}`}
                    className="mono inline-flex items-center gap-1.5 rounded-lg border border-accent bg-accent px-3 py-1 text-xs font-bold text-white shadow-[0_0_10px_rgba(255,0,160,0.3)] hover:bg-accent-hover transition-all"
                  >
                    <RotateCcw className="h-3 w-3" />
                    <span>Rerun Target</span>
                  </Link>
                )}
                <span className="mono text-[10px] text-zinc-500 hidden sm:inline">
                  ISOLATED MODAL MICROVM HARNESS
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              {modelIds.slice(0, 2).map((mId, idx) => {
                const isWinner = scoreWinner === mId;
                const hasScore = scores && mId in scores;
                const rawScore = hasScore ? scores[mId] : null;
                const role = roleForModel(mId, idx);

                return (
                  <div
                    key={mId}
                    className={`rounded-lg border p-4 space-y-2 mono ${
                      isWinner
                        ? "border-emerald-500/40 bg-emerald-950/20"
                        : "border-[#1F1F22] bg-[#050508]"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-[10px] font-bold text-accent uppercase">
                          {role}
                        </div>
                        <h4 className="text-base font-extrabold text-white">
                          {providerName(mId, providers)}
                        </h4>
                      </div>
                      <div className="text-right">
                        {hasScore ? (
                          <div className="text-2xl font-black text-emerald-400">
                            {rawScore}
                          </div>
                        ) : (
                          <div className="text-xs font-semibold text-zinc-500 uppercase">
                            Completed
                          </div>
                        )}
                        {isWinner && (
                          <span className="text-[10px] font-bold text-accent">
                            ★ WINNER
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="border-t border-[#1F1F22] pt-2 text-[11px] text-zinc-400 space-y-1">
                      <div className="flex items-center justify-between text-[10.5px]">
                        <span className="text-zinc-500">Status:</span>
                        <span className="text-zinc-300 font-semibold uppercase">{status}</span>
                      </div>
                      <div className="flex items-center justify-between text-[10.5px]">
                        <span className="text-zinc-500">Execution:</span>
                        <span className="text-zinc-300">Isolated MicroVM</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {err && (
        <div className="border-b border-red-500/40 bg-red-950/30">
          <div className="mx-auto flex max-w-[1760px] items-start gap-3 px-6 py-3 font-mono text-[11px] text-red-300">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{err}</span>
            <button type="button" onClick={() => setErr(null)} className="text-zinc-500 hover:text-white">dismiss</button>
          </div>
        </div>
      )}

      {/* Main Expansive Grid */}
      <main className="mx-auto max-w-[1760px] p-4 md:p-6">
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {modelIds.map((modelId, index) => {
            const history = histories.get(modelId) || [];
            const artifacts = history.filter((item) => item.kind === "artifact");
            const role = roleForModel(modelId, index);
            return (
              <LiveExecutionPane
                key={modelId}
                modelId={modelId}
                displayName={providerName(modelId, providers)}
                role={role}
                status={fighterStatus(modelId)}
                phase={history[history.length - 1]?.phase || phase}
                events={history}
                artifacts={artifacts}
                previewUrl={previewUrls[modelId]}
                win={status === "completed" && scoreWinner === modelId}
              />
            );
          })}
        </div>

        {/* Bottom Dock Drawer */}
        <section className="mt-5 overflow-hidden rounded-lg border border-pink-500/20 bg-[#08050E] shadow-2xl">
          <div className="flex overflow-x-auto border-b border-white/[0.08] bg-[#0A0612] font-mono">
            {([
              ["activity", `Activity Stream (${actionEvents.length})`],
              ["handoffs", `Handoffs (${handoffEvents.length})`],
              ["evidence", "Evidence & Telemetry"],
              ["judge", "Judge Scorecard"],
            ] as const).map(([tabKey, label]) => (
              <button
                key={tabKey}
                type="button"
                onClick={() => setDockTab(tabKey as DockTab)}
                className={cn(
                  "flex h-11 items-center border-r border-white/[0.08] px-6 text-[10px] font-bold uppercase tracking-[0.14em] transition-all",
                  dockTab === tabKey
                    ? "bg-pink-500/10 text-pink-400 shadow-[inset_0_-2px_0_#ff00a0]"
                    : "text-zinc-500 hover:bg-white/[0.02] hover:text-white",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {dockTab === "activity" && (
            <div className="max-h-[300px] overflow-y-auto font-mono text-[10px]">
              {actionEvents.length ? (
                [...actionEvents].reverse().map((item, index) => {
                  const action = parseActionItem(item);
                  if (!action) return null;
                  const failed = action.state === "failed" || action.state === "error";
                  const running = action.state === "running" || action.state === "starting";
                  return (
                    <div
                      key={`${actionKey(item)}-${index}`}
                      className="grid grid-cols-[80px_130px_100px_minmax(0,1fr)_90px] items-center gap-4 border-b border-white/[0.04] px-6 py-3 hover:bg-white/[0.02] transition-colors"
                    >
                      <span className="text-zinc-500">{timeLabel(item.t)}</span>
                      <span className="truncate font-semibold text-pink-400">
                        {titleCase(runtimeRoles.get(item.model_id) || providerName(item.model_id, providers))}
                      </span>
                      <span className="font-bold text-zinc-300">{String(action.action || "event").toUpperCase()}</span>
                      <span className="truncate text-zinc-300 font-mono">{displayCommand(action)}</span>
                      <span className={cn("text-right font-bold", failed ? "text-red-400" : running ? "text-pink-400 animate-pulse" : "text-emerald-400")}>
                        {running ? "● running" : failed ? "× failed" : action.duration_ms ? `${action.duration_ms}ms` : "✓ done"}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="px-6 py-10 text-zinc-500 text-center font-mono text-[11px]">
                  Waiting for authoritative runtime tool activity…
                </div>
              )}
            </div>
          )}

          {dockTab === "handoffs" && (
            <div className="p-6 font-mono text-[11px]">
              {handoffEvents.length ? (
                <div className="space-y-3">
                  {handoffEvents.map((item, index) => {
                    const action = parseActionItem(item);
                    return (
                      <div key={`${actionKey(item)}-${index}`} className="flex flex-wrap items-center gap-4 rounded border border-white/10 bg-[#0A0612] px-5 py-3.5">
                        <span className="text-zinc-500">{timeLabel(item.t)}</span>
                        <span className="font-bold text-pink-400">{String(action?.action || "handoff").toUpperCase()}</span>
                        <span className="text-zinc-200">{action?.target || action?.result || "Runtime handoff event"}</span>
                        <span className="ml-auto font-bold text-emerald-400">{action?.state || "done"}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-zinc-500 text-center py-6">
                  No structured handoff event has been emitted yet. This panel stays empty rather than reconstructing one from assumptions.
                </div>
              )}
            </div>
          )}

          {dockTab === "evidence" && (
            <div className="grid gap-px bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
              <EvidenceCell label="Tool events" value={String(actionEvents.length)} />
              <EvidenceCell label="Artifact snapshots" value={String(events.filter((item) => item.kind === "artifact").length)} />
              <EvidenceCell label="Failed tools" value={String(actionEvents.filter((item) => {
                const a = parseActionItem(item);
                return a?.state === "failed" || a?.state === "error";
              }).length)} />
              <EvidenceCell label="Spec hash" value={battle?.spec_hash || battle?.battle_config?.spec_hash || "not emitted"} mono />
            </div>
          )}

          {dockTab === "judge" && (
            <div className="p-6 font-mono">
              {scores && Object.keys(scores).length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {modelIds.map((modelId) => (
                    <div key={modelId} className="rounded border border-white/10 bg-[#0A0612] p-6">
                      <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">{providerName(modelId, providers)}</div>
                      <div className="mt-2 text-[36px] font-bold tracking-[-0.05em] text-pink-400">{scores[modelId] ?? "—"}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[11px] text-zinc-500 text-center py-6">
                  Judge pending. Scores appear only after the backend emits an authoritative score event.
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function EvidenceCell({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-[#08050E] p-6">
      <div className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-zinc-500">{label}</div>
      <div className={cn("mt-2 truncate text-[17px] font-semibold text-zinc-100", mono && "font-mono text-[12px] text-pink-400")}>{value}</div>
    </div>
  );
}
