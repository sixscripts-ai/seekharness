/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Copy,
  Download,
  MoreHorizontal,
  RotateCcw,
  Save,
  Square,
  Target,
  XCircle,
} from "lucide-react";
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
import { cn } from "@/lib/utils";
import { isAuthoritativeScoresEvent, targetResultPresentation } from "@/lib/targetResult";
import ExecutionSurface from "@/components/battle/ExecutionSurface";
import BattleInspector from "@/components/battle/BattleInspector";
import BattleStatus from "@/components/battle/BattleStatus";
import type { BattleStreamItem, SkillActivity } from "@/components/battle/types";
import {
  mergeEvent,
  parseAction,
  parseJson,
  shortModelName,
  skillActivityFromEvent,
  titleCase,
} from "@/components/battle/utils";

const TERMINAL_STATES = new Set(["completed", "failed", "cancelled"]);
type InspectorTab = "activity" | "expertise" | "evidence" | "result";

function unwrap(ev: StreamEvent): any {
  const wrapped = ev.data as any;
  if (wrapped && typeof wrapped === "object" && wrapped.data && typeof wrapped.data === "object") return wrapped.data;
  return wrapped;
}

function eventTime(data: any): number {
  const raw = data?.created_at ?? data?.ts ?? data?.timestamp;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return Date.now();
  return raw < 1_000_000_000_000 ? raw * 1000 : raw;
}

function normalizeEvent(ev: StreamEvent, fallbackPhase: string): BattleStreamItem | null {
  const data = unwrap(ev) || {};
  const wrapped = ev.data as any;
  const modelId = data?.model_id || data?.fighter_id || wrapped?.model_id || wrapped?.fighter_id || "arena";
  const phase = data?.phase || data?.phase_id || wrapped?.phase || wrapped?.phase_id || fallbackPhase;
  let artifact = data?.artifact ?? wrapped?.artifact ?? data?.message;
  if (artifact === undefined) artifact = typeof data === "string" ? data : JSON.stringify(data);
  if (typeof artifact !== "string") artifact = JSON.stringify(artifact);
  return {
    phase: String(phase || "runtime"),
    model_id: String(modelId),
    artifact,
    t: eventTime(data),
    kind: ev.event,
    payload: data && typeof data === "object" && !Array.isArray(data) ? data : undefined,
  };
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function formatConfig(format: FormatOut | null): any {
  if (!format?.config) return null;
  if (typeof format.config === "object") return format.config;
  return parseJson(format.config);
}

function configuredPhases(format: FormatOut | null): string[] {
  const cfg = formatConfig(format);
  const plan = cfg?.battle_plan;
  const raw = Array.isArray(plan) ? plan : Array.isArray(plan?.phases) ? plan.phases : [];
  const out = raw
    .map((item: any) => typeof item === "string" ? item : item?.id || item?.phase || item?.name)
    .filter((value: unknown): value is string => typeof value === "string" && Boolean(value)) as string[];
  return [...new Set<string>(out)];
}

function rolesForFormat(format: FormatOut | null): string[] {
  if (Array.isArray(format?.roles)) return format.roles;
  const cfg = formatConfig(format);
  return Array.isArray(cfg?.roles) ? cfg.roles.filter((value: unknown): value is string => typeof value === "string") as string[] : [];
}

export default function LiveBattle() {
  const { id } = useParams<{ id: string }>();
  const { user, jwt, refreshJwt } = useAuth();
  const [battle, setBattle] = useState<BattleOut | null>(null);
  const [format, setFormat] = useState<FormatOut | null>(null);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [targetDetail, setTargetDetail] = useState<TargetDetailOut | null>(null);
  const [events, setEvents] = useState<BattleStreamItem[]>([]);
  const [scores, setScores] = useState<Record<string, number> | null>(null);
  const [status, setStatus] = useState("queued");
  const [phase, setPhase] = useState("runtime");
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [selectedModelId, setSelectedModelId] = useState("");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("activity");
  const [showMission, setShowMission] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(Date.now());

  const statusRef = useRef(status);
  const phaseRef = useRef(phase);
  const sessionStartedRef = useRef(Date.now());

  useEffect(() => { statusRef.current = status; }, [status]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

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
          api.formats(token).catch(() => []),
          api.providers(token).catch(() => []),
        ]);
        if (!active) return;
        setBattle(loadedBattle);
        setStatus(loadedBattle.status);
        statusRef.current = loadedBattle.status;
        setFormat(loadedFormats.find((row) => row.id === loadedBattle.format_id) || null);
        setProviders(loadedProviders);
        setScores(loadedBattle.scores && Object.keys(loadedBattle.scores).length ? loadedBattle.scores : null);
        setPreviewUrls(loadedBattle.preview_urls || {});
        if (loadedBattle.model_ids?.length) setSelectedModelId((current) => current || loadedBattle.model_ids[0]);

        if (loadedBattle.target_id) {
          void api.target(loadedBattle.target_id, token).then((detail) => {
            if (active) setTargetDetail(detail);
          }).catch(() => undefined);
        }

        try {
          const persisted = await api.artifacts(token, id);
          if (active && Array.isArray(persisted) && persisted.length) {
            const base = Date.now() - persisted.length;
            setEvents((current) => current.length ? current : persisted.map((item, index) => ({
              phase: item.phase,
              model_id: item.model_id,
              artifact: item.artifact,
              t: base + index,
              kind: "artifact",
            })));
          }
        } catch {
          // A saved artifact snapshot is optional. Durable SSE history is loaded below.
        }
      } catch (error) {
        if (active) setErr(error instanceof Error ? error.message : "Battle failed to load");
      }
    })();
    return () => { active = false; };
  }, [jwt, id, refreshJwt]);

  useEffect(() => {
    if (!jwt || !id || !user) return;
    let cancelled = false;
    const controller = new AbortController();

    const connect = async (attempt = 0): Promise<void> => {
      if (cancelled) return;
      try {
        const token = (await refreshJwt()) || jwt;
        await streamBattle(id, token, (ev) => {
          if (cancelled) return;
          const data = unwrap(ev) || {};

          if (ev.event === "battle_status" || ev.event === "done") {
            const next = data?.status;
            if (next) {
              statusRef.current = String(next);
              setStatus(String(next));
            }
          }

          if (ev.event === "phase_start") {
            const nextPhase = data?.phase || data?.phase_id;
            if (nextPhase) {
              phaseRef.current = String(nextPhase);
              setPhase(String(nextPhase));
            }
          }

          if (["artifact", "transcript", "action_log", "phase_start", "skill_index_browse", "skill_search", "skill_card_view", "skill_load"].includes(ev.event)) {
            const item = normalizeEvent(ev, phaseRef.current);
            if (item) setEvents((previous) => mergeEvent(previous, item));
          }

          if (ev.event === "verification") {
            setBattle((current) => current ? {
              ...current,
              verification_status: data?.verification_status ?? current.verification_status,
              verified_solution: data?.verification_status === "verified_pass" && data?.passed === true,
              termination_reason: data?.executor_outcome || data?.outcome || current.termination_reason,
              outcome: data?.executor_outcome || data?.outcome || current.outcome,
            } : current);
          }

          if (ev.event === "scores") {
            const payload = data as {
              scores?: Record<string, number>;
              authoritative?: boolean;
              source?: string;
              winner?: string | null;
              verified_solution?: boolean;
              verification_status?: string;
              termination_reason?: string | null;
            };
            if (!isAuthoritativeScoresEvent(payload)) return;
            if (payload.scores && typeof payload.scores === "object") setScores(payload.scores);
            setBattle((current) => current ? {
              ...current,
              scores: payload.scores ?? current.scores,
              winner: payload.winner ?? current.winner,
              verified_solution: payload.verified_solution ?? current.verified_solution,
              verification_status: payload.verification_status ?? current.verification_status,
              termination_reason: payload.termination_reason ?? current.termination_reason,
              outcome: payload.termination_reason ?? current.outcome,
            } : current);
          }

          if (ev.event === "preview") {
            const modelId = data?.model_id || data?.fighter_id;
            const url = data?.url;
            if (modelId && url) setPreviewUrls((previous) => ({ ...previous, [String(modelId)]: String(url) }));
          }
        }, controller.signal);
      } catch (error) {
        if (cancelled) return;
        if (!TERMINAL_STATES.has(statusRef.current) && attempt < 5) {
          await new Promise((resolve) => window.setTimeout(resolve, Math.min(1000 * (attempt + 1), 5000)));
          return connect(attempt + 1);
        }
        if (!TERMINAL_STATES.has(statusRef.current)) setErr(error instanceof Error ? error.message : "Battle stream disconnected");
      }
    };

    // Connect once even for completed battles: the stream endpoint emits its durable snapshot first.
    void connect();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jwt, id, user, refreshJwt]);

  const providerNames = useMemo(() => new Map(providers.map((provider) => [provider.id, provider.name || provider.model_name])), [providers]);
  const modelName = (modelId: string) => providerNames.get(modelId) || shortModelName(modelId);

  const modelIds = useMemo(() => {
    const ids = [...(battle?.model_ids || [])];
    for (const event of events) if (event.model_id && event.model_id !== "arena" && !ids.includes(event.model_id)) ids.push(event.model_id);
    return ids;
  }, [battle?.model_ids, events]);

  useEffect(() => {
    if (!selectedModelId && modelIds.length) setSelectedModelId(modelIds[0]);
    if (selectedModelId && !modelIds.includes(selectedModelId) && modelIds.length) setSelectedModelId(modelIds[0]);
  }, [modelIds, selectedModelId]);

  const formatRoles = useMemo(() => rolesForFormat(format), [format]);
  const runtimeRoles = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of events) {
      if (item.kind === "phase_start") {
        const payload = item.payload || parseJson(item.artifact) || {};
        const role = payload.role;
        if (typeof role === "string" && item.model_id !== "arena") map.set(item.model_id, role);
      }
      const action = parseAction(item);
      const payload = parseJson(item.artifact);
      const role = payload?.role || payload?.fighter_role;
      if (action && typeof role === "string") map.set(item.model_id, role);
    }
    return map;
  }, [events]);
  const roleForModel = (modelId: string, index: number) => runtimeRoles.get(modelId) || formatRoles[index] || `Fighter ${index + 1}`;

  const histories = useMemo(() => {
    const map = new Map<string, BattleStreamItem[]>();
    for (const modelId of modelIds) map.set(modelId, []);
    for (const item of events) {
      if (!map.has(item.model_id)) map.set(item.model_id, []);
      map.get(item.model_id)?.push(item);
    }
    return map;
  }, [events, modelIds]);

  const skillActivity = useMemo(() => events.map(skillActivityFromEvent).filter((item): item is SkillActivity => Boolean(item)), [events]);

  const latestActionByModel = useMemo(() => {
    const map = new Map<string, ReturnType<typeof parseAction>>();
    for (const item of events) {
      const parsed = parseAction(item);
      if (parsed) map.set(item.model_id, parsed);
    }
    return map;
  }, [events]);

  function fighterState(modelId: string): "waiting" | "starting" | "running" | "complete" | "failed" {
    const latest = latestActionByModel.get(modelId);
    if (status === "failed" || status === "cancelled") return "failed";
    if (status === "completed") return "complete";
    if (!latest) return status === "running" ? "starting" : "waiting";
    if (latest.state === "failed" || latest.state === "error") return "failed";
    if (latest.state === "running" || latest.state === "starting") return "running";
    return status === "running" ? "running" : "waiting";
  }

  const expectedPhases = useMemo(() => configuredPhases(format), [format]);
  const observedPhases = useMemo(() => {
    const out: string[] = [];
    for (const item of events) if (item.phase && !out.includes(item.phase)) out.push(item.phase);
    if (phase && !out.includes(phase)) out.push(phase);
    return out;
  }, [events, phase]);
  const pipeline = expectedPhases.length ? expectedPhases : observedPhases.length ? observedPhases : [phase];
  const currentPhaseIndex = Math.max(0, pipeline.indexOf(phase));

  const resultView = useMemo(() => targetResultPresentation({
    status,
    isTargetBattle: Boolean(battle?.target_id),
    result: {
      scores: scores || battle?.scores,
      winner: battle?.winner,
      verified_solution: battle?.verified_solution,
      verification_status: battle?.verification_status,
      termination_reason: battle?.termination_reason,
      outcome: battle?.outcome,
    },
  }), [status, battle, scores]);

  const firstEventTime = useMemo(() => events.length ? Math.min(...events.map((item) => item.t)) : sessionStartedRef.current, [events]);
  const elapsed = formatElapsed(now - firstEventTime);

  async function cancelBattle() {
    if (!id) return;
    setBusy("cancel");
    try {
      const token = (await refreshJwt()) || jwt;
      if (!token) return;
      await api.cancelBattle(token, id);
      statusRef.current = "cancelled";
      setStatus("cancelled");
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to cancel battle");
    } finally { setBusy(null); }
  }

  async function saveBattle() {
    if (!id) return;
    setBusy("save");
    try {
      const token = (await refreshJwt()) || jwt;
      if (!token) return;
      await api.saveBattle(token, id);
      setBattle((current) => current ? { ...current, saved: true } : current);
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Failed to save battle");
    } finally { setBusy(null); }
  }

  async function copyBattleId() {
    if (!id) return;
    await navigator.clipboard.writeText(id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1300);
  }

  function downloadReplay() {
    const payload = { battle, status, phase, scores, events };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `seekharness_battle_${id || "replay"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!user) {
    return (
      <div className="grid min-h-[calc(100vh-56px)] place-items-center bg-[#07080a] px-6">
        <div className="max-w-[34ch] text-center">
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-zinc-600">Private execution</div>
          <p className="mt-3 text-[13px] leading-6 text-zinc-400">Log in to inspect this battle and its execution stream.</p>
          <Link to="/login" className="mt-5 inline-flex h-9 items-center rounded-md bg-zinc-100 px-4 text-[11px] font-semibold text-zinc-950">Log in</Link>
        </div>
      </div>
    );
  }

  const isTargetBattle = Boolean(battle?.target_id);
  const title = targetDetail?.name || battle?.custom_title || battle?.title || (battle?.target_id ? titleCase(battle.target_id) : titleCase(battle?.format_id || "Battle"));
  const dualDesktop = modelIds.length === 2;

  return (
    <div className="battle-live bg-[#07080a] text-zinc-100">
      <header className="battle-command-bar">
        <div className="flex min-w-0 items-center gap-3">
          <Link to="/battles" className="battle-icon-button" title="Back to battles"><ArrowLeft className="h-4 w-4" /></Link>
          <div className="min-w-0 border-l border-white/[0.07] pl-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <h1 className="truncate text-[14px] font-semibold tracking-[-0.02em] text-zinc-100">{title}</h1>
              <BattleStatus status={status} verificationStatus={battle?.verification_status} compact />
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-2 font-mono text-[8px] uppercase tracking-[0.1em] text-zinc-700">
              <span className="truncate">{format?.name || titleCase(battle?.format_id || "battle")}</span>
              {!TERMINAL_STATES.has(status) ? <><span>·</span><span>{elapsed}</span></> : null}
              {battle?.target_version ? <><span>·</span><span>v{battle.target_version}</span></> : null}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {isTargetBattle && battle?.target_id ? (
            <Link to={`/targets/${encodeURIComponent(battle.target_id)}`} className="battle-text-button hidden md:inline-flex">
              <Target className="h-3.5 w-3.5" /> Briefing
            </Link>
          ) : null}
          {!TERMINAL_STATES.has(status) ? (
            <button type="button" onClick={cancelBattle} disabled={busy === "cancel"} className="battle-text-button text-rose-300 hover:text-rose-200">
              <Square className="h-3 w-3" /> Stop
            </button>
          ) : null}
          <div className="relative">
            <button type="button" onClick={() => setShowActions((value) => !value)} className="battle-icon-button" title="Battle actions">
              <MoreHorizontal className="h-4 w-4" />
            </button>
            {showActions ? (
              <div className="battle-actions-menu">
                <button type="button" onClick={copyBattleId}>{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy battle ID"}</button>
                <button type="button" onClick={downloadReplay}><Download className="h-3.5 w-3.5" /> Export replay</button>
                <button type="button" onClick={saveBattle} disabled={busy === "save" || Boolean(battle?.saved)}><Save className="h-3.5 w-3.5" /> {battle?.saved ? "Saved" : "Save battle"}</button>
                {isTargetBattle && battle?.target_id ? (
                  <Link to={`/battles/new?target=${encodeURIComponent(battle.target_id)}`}><RotateCcw className="h-3.5 w-3.5" /> Rerun target</Link>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {err ? (
        <div className="flex items-start gap-3 border-b border-rose-400/20 bg-rose-400/[0.05] px-5 py-2.5 text-[10px] text-rose-200">
          <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span className="min-w-0 flex-1 break-words">{err}</span>
          <button type="button" onClick={() => setErr(null)} className="text-zinc-600 hover:text-zinc-300">dismiss</button>
        </div>
      ) : null}

      <div className="battle-context-strip">
        <div className="flex min-w-0 items-center gap-4 overflow-x-auto">
          <span className="shrink-0 font-mono text-[8px] font-semibold uppercase tracking-[0.14em] text-zinc-700">Phase</span>
          {pipeline.map((item, index) => {
            const active = item === phase;
            const done = index < currentPhaseIndex || (TERMINAL_STATES.has(status) && index <= currentPhaseIndex);
            return (
              <div key={`${item}-${index}`} className="flex shrink-0 items-center gap-2">
                <span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-fuchsia-400" : done ? "bg-emerald-400/70" : "bg-zinc-800")} />
                <span className={cn("font-mono text-[9px]", active ? "text-zinc-200" : done ? "text-zinc-500" : "text-zinc-700")}>{titleCase(item)}</span>
                {index < pipeline.length - 1 ? <span className="h-px w-5 bg-white/[0.07]" /> : null}
              </div>
            );
          })}
        </div>

        {targetDetail?.objectives?.length ? (
          <button type="button" onClick={() => setShowMission((value) => !value)} className="ml-auto hidden shrink-0 items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.11em] text-zinc-600 hover:text-zinc-300 md:flex">
            Mission <ChevronDown className={cn("h-3 w-3 transition", showMission && "rotate-180")} />
          </button>
        ) : null}
      </div>

      {showMission && targetDetail?.objectives?.length ? (
        <div className="border-b border-white/[0.06] bg-[#090a0c] px-5 py-3">
          <div className="mx-auto flex max-w-[1500px] flex-wrap gap-x-8 gap-y-2">
            {targetDetail.objectives.map((objective, index) => (
              <div key={`${objective}-${index}`} className="flex max-w-[46ch] items-start gap-2 text-[10px] leading-5 text-zinc-500">
                <span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-zinc-700" /><span>{objective}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {modelIds.length > 1 ? (
        <div className="battle-fighter-switcher xl:hidden">
          {modelIds.map((modelId, index) => (
            <button key={modelId} type="button" onClick={() => setSelectedModelId(modelId)} className={cn("battle-fighter-switch", selectedModelId === modelId && "battle-fighter-switch-active")}>
              <span>{modelName(modelId)}</span><span>{roleForModel(modelId, index)}</span>
            </button>
          ))}
        </div>
      ) : null}

      <main className="battle-stage">
        <div className="battle-stage-arena">
          <div className={cn("battle-stage-grid", dualDesktop && "battle-stage-grid-dual")}>
            {modelIds.map((modelId, index) => {
              const history = histories.get(modelId) || [];
              const artifacts = history.filter((item) => item.kind === "artifact");
              const skills = skillActivity.filter((item) => item.modelId === modelId);
              const hideWhenCompact = modelIds.length > 1 && selectedModelId !== modelId;
              return (
                <div key={modelId} className={cn("battle-stage-slot", hideWhenCompact && "hidden xl:block", modelIds.length > 2 && hideWhenCompact && "xl:hidden")}>
                  <ExecutionSurface
                    modelId={modelId}
                    displayName={modelName(modelId)}
                    role={roleForModel(modelId, index)}
                    state={fighterState(modelId)}
                    phase={history[history.length - 1]?.phase || phase}
                    events={history}
                    artifacts={artifacts}
                    skillActivity={skills}
                    previewUrl={previewUrls[modelId]}
                    focused={selectedModelId === modelId}
                    onFocus={() => setSelectedModelId(modelId)}
                  />
                </div>
              );
            })}

            {!modelIds.length ? (
              <div className="flex min-h-[520px] items-center justify-center bg-[#08090b] text-center">
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-zinc-700">Waiting for fighters</div>
                  <p className="mt-2 text-[11px] text-zinc-700">No execution slot has been reported yet.</p>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {battle ? (
          <BattleInspector
            tab={inspectorTab}
            onTabChange={setInspectorTab}
            battle={battle}
            status={status}
            modelIds={modelIds}
            modelName={modelName}
            events={events}
            skillActivity={skillActivity}
            selectedModelId={selectedModelId || modelIds[0] || ""}
            resultView={resultView}
          />
        ) : (
          <div className="battle-inspector" />
        )}
      </main>

      {resultView.statusTone === "verified" && resultView.winnerId ? (
        <div className="battle-result-toast">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span className="text-zinc-500">Verified winner</span>
          <span className="font-medium text-zinc-100">{modelName(resultView.winnerId)}</span>
        </div>
      ) : null}
    </div>
  );
}
