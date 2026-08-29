/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  Eye,
  Radio,
  Save,
  Square,
  Trophy,
  XCircle,
} from "lucide-react";
import { api, streamBattle, type BattleOut, type StreamEvent } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import CodePane, { type PaneArtifact } from "@/components/CodePane";

type CodeArtifact = PaneArtifact & { model_id: string };

type ActivityFilter = "all" | string;

const TERMINAL_STATES = new Set(["completed", "failed", "cancelled"]);

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

function formatFighterName(id: string): string {
  if (!id) return "Agent";
  if (id.includes("claude")) return "Claude 3.7 Sonnet";
  if (id.includes("deepseek") || id.includes("6a85")) return "DeepSeek R1";
  if (id.includes("o3") || id.includes("gpt")) return "OpenAI o3-mini";
  if (id.includes("kimi")) return "Moonshot Kimi-K3";
  if (id.includes("gemini")) return "Gemini 2.5 Pro";
  if (id.startsWith("host:")) {
    const clean = id.replace("host:", "").replace(/-/g, " ");
    return clean
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }
  if (id.length > 12) return `Agent ${id.slice(0, 8)}`;
  return id;
}

export default function LiveBattle() {
  const { id } = useParams<{ id: string }>();
  const { user, jwt, refreshJwt } = useAuth();
  const [battle, setBattle] = useState<BattleOut | null>(null);
  const [arts, setArts] = useState<CodeArtifact[]>([]);
  const [scores, setScores] = useState<Record<string, number> | null>(null);
  const [status, setStatus] = useState("queued");
  const [phase, setPhase] = useState("build");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>("all");
  const [now, setNow] = useState(Date.now());
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});

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
    (async () => {
      try {
        const token = (await refreshJwt()) || jwt;
        const b = await api.getBattle(token, id);
        if (!active) return;
        setBattle(b);
        setStatus(b.status);
        if (b.preview_urls && Object.keys(b.preview_urls).length) {
          setPreviewUrls(b.preview_urls);
        }

        try {
          const persisted = await api.artifacts(token, id);
          if (!active || !Array.isArray(persisted) || persisted.length === 0)
            return;
          const base = Date.now() - persisted.length;
          setArts((current) => {
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
          // A live stream can still work when persisted artifacts are unavailable.
        }
      } catch (e) {
        if (active)
          setErr(e instanceof Error ? e.message : "Battle failed to load");
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
            const wrapped = ev.data as any;
            const data = wrapped?.data ?? wrapped;
            const d = data as any;

            if (ev.event === "battle_status" || ev.event === "done") {
              const nextStatus = d?.status || wrapped?.status;
              if (nextStatus) {
                statusRef.current = nextStatus;
                setStatus(nextStatus);
              }
            }

            if (ev.event === "phase_start") {
              const nextPhase = d?.phase || wrapped?.phase;
              if (nextPhase) {
                phaseRef.current = nextPhase;
                setPhase(nextPhase);
              }
            }

            if (["artifact", "transcript", "action_log"].includes(ev.event)) {
              const artifact =
                d?.artifact ??
                wrapped?.artifact ??
                d?.message ??
                JSON.stringify(data);
              const modelId = d?.model_id || wrapped?.model_id || "system";
              const eventPhase = d?.phase || wrapped?.phase || phaseRef.current;
              setArts((previous) =>
                [
                  ...previous,
                  {
                    phase: eventPhase,
                    model_id: modelId,
                    artifact:
                      typeof artifact === "string"
                        ? artifact
                        : JSON.stringify(artifact),
                    t: Date.now(),
                    kind: ev.event,
                  },
                ].slice(-300),
              );
            }

            if (ev.event === "scores") {
              const directScores = d?.scores || wrapped?.scores;
              if (directScores) {
                setScores(directScores);
                return;
              }
              try {
                const raw = d?.artifact || wrapped?.artifact;
                const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
                if (parsed?.scores) setScores(parsed.scores);
                else if (parsed?.data?.scores) setScores(parsed.data.scores);
              } catch {}
            }

            if (ev.event === "preview") {
              const modelId = d?.model_id || wrapped?.model_id;
              const url = d?.url || wrapped?.url;
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
      } catch (e) {
        if (cancelled) return;
        if (attempt < 4) {
          await new Promise((resolve) =>
            window.setTimeout(resolve, 1000 * 2 ** attempt),
          );
          await connect(attempt + 1);
        } else if (!TERMINAL_STATES.has(statusRef.current)) {
          setErr(
            e instanceof Error
              ? `Live stream disconnected: ${e.message}`
              : "Live stream disconnected",
          );
        }
      }
    };

    void connect();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [jwt, id, user, refreshJwt]);

  const modelIds = useMemo(() => battle?.model_ids || [], [battle?.model_ids]);

  const histories = useMemo(() => {
    const map = new Map<string, CodeArtifact[]>();
    for (const item of arts) {
      if (!map.has(item.model_id)) map.set(item.model_id, []);
      map.get(item.model_id)!.push(item);
    }
    return map;
  }, [arts]);

  const phases = useMemo(() => {
    const ordered: string[] = [];
    for (const item of arts) {
      if (item.phase && !ordered.includes(item.phase)) ordered.push(item.phase);
    }
    if (phase && !ordered.includes(phase)) ordered.push(phase);
    return ordered.length ? ordered : ["build"];
  }, [arts, phase]);

  const latestEvent = useMemo(() => {
    return arts[arts.length - 1] || null;
  }, [arts]);

  const winner = useMemo(() => {
    if (!scores || !modelIds.length) return null;
    return modelIds.reduce(
      (best, model) =>
        Number(scores[model] ?? -Infinity) > Number(scores[best] ?? -Infinity)
          ? model
          : best,
      modelIds[0],
    );
  }, [scores, modelIds]);

  const startAt = arts[0]?.t || sessionStartedRef.current;
  const elapsed = formatElapsed(now - startAt);

  async function cancel() {
    if (!jwt || !id) return;
    setBusy("cancel");
    try {
      const token = (await refreshJwt()) || jwt;
      await api.cancelBattle(token, id);
      setStatus("cancelled");
      statusRef.current = "cancelled";
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Cancel failed");
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
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
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
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-pink-400">
            Stream locked
          </div>
          <p className="text-[14px] text-zinc-400">
            This bout is private. Log in to watch the live stream.
          </p>
          <Link to="/login" className="btn btn-primary mx-auto h-10 px-6">
            Log in
          </Link>
        </div>
      </div>
    );
  }

  const fighters = modelIds.length ? modelIds : ["model_a", "model_b"];

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#020104] text-white">
      {/* ===================================================================== */}
      {/* ARENA MATCH CONTROL BAR */}
      {/* ===================================================================== */}
      <section className="border-b border-pink-500/20 bg-[#07050C]">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              {/* Phase Badge */}
              <span className="rounded-md border border-pink-500 bg-pink-500/15 px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-pink-400">
                PHASE 01 // {phase}
              </span>

              {/* Status */}
              <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                {status === "running" ? "SSE Live Streaming" : status}
              </span>

              {/* Elapsed Timer */}
              <span className="flex items-center gap-1 rounded bg-[#040306] px-2.5 py-1 font-mono text-[10px] text-zinc-400 border border-white/5">
                <Clock3 className="h-3 w-3 text-zinc-500" />
                {elapsed} ELAPSED
              </span>

              {/* Battle ID Copy */}
              <button
                type="button"
                onClick={copyBattleId}
                className="flex items-center gap-1 font-mono text-[10px] text-zinc-500 hover:text-white transition-colors"
                title="Copy battle ID"
              >
                {copiedId ? <Check className="h-3 w-3 text-pink-400" /> : <Copy className="h-3 w-3" />}
                ID: #{String(id).slice(0, 8)}
              </button>
            </div>

            <h1 className="mt-2 truncate font-display text-[26px] font-black tracking-tight text-white md:text-[32px]">
              {battle?.custom_title || battle?.format_id?.replace(/_/g, " ").replace(/-/g, " ") || "Live Battle Duel"}
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={busy === "save" || !!battle?.saved}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-4 font-mono text-[11px] font-semibold text-zinc-300 transition-colors hover:border-pink-500 hover:text-pink-400 disabled:opacity-40"
            >
              <Save className="h-3.5 w-3.5" />
              {battle?.saved ? "Saved" : "Save Replay"}
            </button>
            <button
              type="button"
              onClick={cancel}
              disabled={busy === "cancel" || TERMINAL_STATES.has(status)}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/10 px-4 font-mono text-[11px] font-semibold text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-40"
            >
              <Square className="h-3.5 w-3.5" /> Halt
            </button>
          </div>
        </div>
      </section>

      {err && (
        <div className="flex items-start gap-3 border-b border-red-500 bg-red-950/40 px-6 py-3 font-mono text-[11px] text-red-400">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1 break-words">{err}</span>
          <button
            type="button"
            onClick={() => setErr(null)}
            className="shrink-0 underline underline-offset-2"
          >
            dismiss
          </button>
        </div>
      )}

      {/* ===================================================================== */}
      {/* DUAL FULL TERMINAL COCKPIT STAGE */}
      {/* ===================================================================== */}
      <main className="mx-auto max-w-[1440px] px-6 py-6">
        <div className="grid grid-cols-12 gap-6">
          {fighters.map((modelId, index) => {
            const modelHistory = histories.get(modelId) || [];
            const artifactHistory = modelHistory.filter(
              (item) => !item.kind || item.kind === "artifact",
            );
            const latest =
              artifactHistory[artifactHistory.length - 1]?.artifact ||
              modelHistory[modelHistory.length - 1]?.artifact ||
              "";

            return (
              <div key={modelId} className="col-span-12 lg:col-span-6">
                <CodePane
                  modelId={modelId}
                  label={modelId}
                  role={index === 1 ? "breaker" : "builder"}
                  code={latest}
                  history={artifactHistory}
                  events={modelHistory}
                  status={status}
                  previewUrl={previewUrls[modelId]}
                  artifactMeta={`${(latest.length / 1024).toFixed(1)}kb · ${latest ? latest.split("\n").length : 0} lines`}
                  win={winner === modelId && status === "completed"}
                  winText="winner"
                  protectedFiles={
                    index === 1 || battle?.format_id?.includes("auth")
                      ? ["auth.py"]
                      : []
                  }
                />
              </div>
            );
          })}
        </div>

        {/* ===================================================================== */}
        {/* MULTIPLEXED LIVE EVENT TICKER & ARBITER DOCK */}
        {/* ===================================================================== */}
        <section className="mt-6 rounded-xl border border-pink-500/25 bg-[#080510] p-4 shadow-xl">
          <div className="grid grid-cols-12 items-center gap-4">
            {/* Live Multiplexed SSE Event */}
            <div className="col-span-12 lg:col-span-8 font-mono text-[11px]">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-extrabold uppercase tracking-wider text-pink-400 text-[10px]">
                  LATEST MULTIPLEXED EVENT
                </span>
                <span className="text-[9px] text-zinc-500">
                  (Auto-parsed from SSE)
                </span>
              </div>
              {latestEvent ? (
                <div className="flex flex-wrap items-center gap-2 text-zinc-300">
                  <span className="text-zinc-500">{timeLabel(latestEvent.t)}</span>
                  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400 border border-emerald-500/30">
                    {latestEvent.kind ? latestEvent.kind.toUpperCase() : "EVENT"}
                  </span>
                  <span className="font-bold text-white">
                    {formatFighterName(latestEvent.model_id)}
                  </span>
                  <span className="text-zinc-400 truncate max-w-[500px]">
                    {latestEvent.artifact.slice(0, 120)}
                  </span>
                </div>
              ) : (
                <div className="text-zinc-500">
                  Listening for agent execution stream…
                </div>
              )}
            </div>

            {/* Judge Arbiter Verdict Summary */}
            <div className="col-span-12 lg:col-span-4 flex justify-start lg:justify-end items-center">
              <div className="font-mono text-left lg:text-right">
                <div className="text-[9px] uppercase tracking-widest text-zinc-500">
                  JUDGE ARBITER (KIMI-K3)
                </div>
                {scores && Object.keys(scores).length > 0 ? (
                  <div className="mt-0.5 text-[14px] font-extrabold text-pink-400">
                    {winner ? formatFighterName(winner) : "Tied"} [{scores[winner || ""] ?? 1.0}]
                    <span className="mx-1 text-zinc-500 font-normal">def.</span>
                    {formatFighterName(fighters.find((f) => f !== winner) || "")} [{scores[fighters.find((f) => f !== winner) || ""] ?? 0.0}]
                  </div>
                ) : (
                  <div className="mt-0.5 text-[12px] text-zinc-400">
                    Awaiting battle completion…
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
