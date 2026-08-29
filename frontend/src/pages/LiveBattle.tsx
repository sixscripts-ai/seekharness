/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, Save, Square, XCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  streamBattle,
  type BattleOut,
  type FormatOut,
  type ProviderOut,
  type StreamEvent,
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

function phaseStartWorkspace(item: BattleStreamItem): string | null {
  if (item.kind !== "phase_start") return null;
  const parsed = parseJson(item.artifact);
  if (parsed && typeof parsed.workspace === "string") return parsed.workspace;
  const match = item.artifact.match(/workdir\s+([^\s]+)/i);
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

  const modelIds = battle?.model_ids || [];
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

  const title = battle?.custom_title || titleCase(battle?.format_id || "Live battle");

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#020203] text-white">
      <section className="border-b border-white/10 bg-[#070708]">
        <div className="mx-auto max-w-[1600px] px-4 py-4 md:px-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="truncate text-[20px] font-semibold tracking-[-0.03em] md:text-[24px]">{title}</h1>
                <span className={cn(
                  "font-mono text-[9px] font-bold uppercase tracking-[0.13em]",
                  status === "running" ? "text-emerald-400" : "text-zinc-500",
                )}>
                  {status === "running" ? "● live" : status}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-[9px] text-zinc-600">
                <button type="button" onClick={copyBattleId} className="inline-flex items-center gap-1 hover:text-zinc-300">
                  {copiedId ? <Check className="h-3 w-3 text-pink-400" /> : <Copy className="h-3 w-3" />}
                  {id}
                </button>
                <span>{battle?.round_visibility || "—"}</span>
                <span>{elapsed} elapsed</span>
                {battle?.difficulty ? <span>{battle.difficulty}</span> : null}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={save}
                disabled={busy === "save" || !!battle?.saved}
                className="btn h-9 border border-white/10 bg-[#0B0B0C] px-4 font-mono text-[9px] uppercase tracking-[0.1em] text-zinc-300 hover:border-pink-500 hover:text-pink-400 disabled:opacity-40"
              >
                <Save className="mr-2 inline h-3 w-3" />
                {battle?.saved ? "Saved" : "Save replay"}
              </button>
              <button
                type="button"
                onClick={cancel}
                disabled={busy === "cancel" || TERMINAL_STATES.has(status)}
                className="btn h-9 border border-red-500/30 bg-red-500/5 px-4 font-mono text-[9px] uppercase tracking-[0.1em] text-red-400 hover:bg-red-500/10 disabled:opacity-40"
              >
                <Square className="mr-2 inline h-3 w-3" /> Halt
              </button>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-0 overflow-x-auto border-t border-white/10 pt-3 font-mono">
            {pipeline.map((item, index) => {
              const active = item === phase;
              const done = index < currentPhaseIndex || (TERMINAL_STATES.has(status) && index <= currentPhaseIndex);
              return (
                <div key={`${item}-${index}`} className="flex min-w-[120px] flex-1 items-center last:flex-none">
                  <div className="min-w-[88px]">
                    <div className={cn(
                      "text-[8px] uppercase tracking-[0.12em]",
                      active ? "text-pink-400" : done ? "text-emerald-400" : "text-zinc-700",
                    )}>
                      {done ? "✓ " : active ? "● " : ""}{titleCase(item)}
                    </div>
                  </div>
                  {index < pipeline.length - 1 ? (
                    <div className={cn("mx-2 h-px min-w-8 flex-1", done ? "bg-emerald-500/40" : active ? "bg-pink-500/60" : "bg-white/10")} />
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {err && (
        <div className="border-b border-red-500/40 bg-red-950/30">
          <div className="mx-auto flex max-w-[1600px] items-start gap-3 px-6 py-3 font-mono text-[10px] text-red-300">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{err}</span>
            <button type="button" onClick={() => setErr(null)} className="text-zinc-500 hover:text-white">dismiss</button>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-[1600px] p-3 md:p-4">
        <div className="grid grid-cols-1 gap-px bg-white/10 xl:grid-cols-2">
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

        <section className="mt-px border border-white/10 bg-[#060607]">
          <div className="flex overflow-x-auto border-b border-white/10 font-mono">
            {(["activity", "handoffs", "evidence", "judge"] as DockTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setDockTab(tab)}
                className={cn(
                  "h-10 border-r border-white/10 px-5 text-[9px] font-bold uppercase tracking-[0.12em]",
                  dockTab === tab
                    ? "bg-pink-500/10 text-pink-400 shadow-[inset_0_-1px_0_#ff00a0]"
                    : "text-zinc-500 hover:text-white",
                )}
              >
                {tab}
              </button>
            ))}
          </div>

          {dockTab === "activity" && (
            <div className="max-h-[270px] overflow-y-auto font-mono text-[9px]">
              {actionEvents.length ? (
                [...actionEvents].reverse().map((item, index) => {
                  const action = parseActionItem(item);
                  if (!action) return null;
                  const failed = action.state === "failed" || action.state === "error";
                  const running = action.state === "running" || action.state === "starting";
                  return (
                    <div
                      key={`${actionKey(item)}-${index}`}
                      className="grid grid-cols-[76px_110px_90px_minmax(0,1fr)_80px] gap-3 border-b border-white/[0.06] px-4 py-2.5"
                    >
                      <span className="text-zinc-700">{timeLabel(item.t)}</span>
                      <span className="truncate text-zinc-400">{titleCase(runtimeRoles.get(item.model_id) || providerName(item.model_id, providers))}</span>
                      <span className="text-pink-400">{String(action.action || "event").toUpperCase()}</span>
                      <span className="truncate text-zinc-300">{displayCommand(action)}</span>
                      <span className={failed ? "text-red-400" : running ? "text-amber-300" : "text-emerald-400"}>
                        {running ? "running" : failed ? "failed" : action.duration_ms ? `${action.duration_ms}ms` : "done"}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="px-5 py-8 text-zinc-600">Waiting for authoritative tool activity…</div>
              )}
            </div>
          )}

          {dockTab === "handoffs" && (
            <div className="p-5 font-mono text-[10px]">
              {handoffEvents.length ? (
                <div className="space-y-2">
                  {handoffEvents.map((item, index) => {
                    const action = parseActionItem(item);
                    return (
                      <div key={`${actionKey(item)}-${index}`} className="flex flex-wrap items-center gap-3 border border-white/10 bg-[#09090A] px-4 py-3">
                        <span className="text-zinc-700">{timeLabel(item.t)}</span>
                        <span className="text-pink-400">{String(action?.action || "handoff").toUpperCase()}</span>
                        <span className="text-zinc-300">{action?.target || action?.result || "Runtime handoff event"}</span>
                        <span className="ml-auto text-emerald-400">{action?.state || "done"}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-zinc-600">
                  No structured handoff event has been emitted yet. This panel stays empty rather than reconstructing one from UI assumptions.
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
            <div className="p-5 font-mono">
              {scores && Object.keys(scores).length ? (
                <div className="grid gap-px bg-white/10 md:grid-cols-2">
                  {modelIds.map((modelId) => (
                    <div key={modelId} className="bg-[#09090A] p-5">
                      <div className="text-[9px] uppercase tracking-[0.12em] text-zinc-600">{providerName(modelId, providers)}</div>
                      <div className="mt-2 text-[32px] font-semibold tracking-[-0.05em] text-pink-400">{scores[modelId] ?? "—"}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-zinc-600">
                  Judge pending. Scores appear only after the backend emits a real score event.
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
    <div className="bg-[#080809] p-5">
      <div className="font-mono text-[8px] uppercase tracking-[0.13em] text-zinc-600">{label}</div>
      <div className={cn("mt-2 truncate text-[16px] text-zinc-200", mono && "font-mono text-[11px]")}>{value}</div>
    </div>
  );
}
