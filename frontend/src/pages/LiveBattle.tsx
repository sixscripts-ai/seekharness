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

function preview(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 180 ? `${normalized.slice(0, 180)}…` : normalized;
}

function eventLabel(kind?: string): string {
  if (kind === "action_log") return "TOOL";
  if (kind === "transcript") return "OUTPUT";
  if (kind === "artifact") return "ARTIFACT";
  return (kind || "EVENT").toUpperCase();
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

  const activity = useMemo(() => {
    const filtered =
      activityFilter === "all"
        ? arts
        : arts.filter((item) => item.phase === activityFilter);
    return filtered.slice(-14).reverse();
  }, [arts, activityFilter]);

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
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            Stream locked
          </div>
          <p className="text-[14px] text-muted">
            This bout is private. Log in to watch the live stream.
          </p>
          <Link to="/login" className="btn btn-primary mx-auto h-10 px-6">
            Log in
          </Link>
        </div>
      </div>
    );
  }

  const statusClass =
    status === "completed"
      ? "bg-accent text-accent-fg"
      : status === "running"
        ? "bg-accent text-accent-fg"
        : status === "failed" || status === "cancelled"
          ? "bg-danger text-white"
          : "border border-border text-muted";

  const fighters = modelIds.length ? modelIds : ["model_a", "model_b"];

  return (
    <div className="min-h-[calc(100vh-56px)] bg-background text-foreground">
      <section className="border-b border-border">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-4 px-6 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] ${statusClass}`}
              >
                {status === "running" && (
                  <span className="h-1.5 w-1.5 animate-pulse bg-current" />
                )}
                {status === "running" ? "live" : status}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
                {elapsed}
              </span>
            </div>
            <h1 className="mt-2 truncate font-display text-[36px] leading-none tracking-[-0.04em] md:text-[48px]">
              {battle?.custom_title || battle?.format_id || "Battle"}
            </h1>
            {(() => {
              const cfg = battle?.battle_config;
              const mode = cfg?.evaluation_mode || (cfg?.judge_only ? "quick" : "");
              const badge = mode === "verified" ? "Verified" : mode === "quick" || cfg?.custom ? "Judge-only" : "";
              const brief = typeof cfg?.description === "string" ? cfg.description : "";
              return (
                <div className="mt-2 space-y-2">
                  {badge && (
                    <span className="inline-flex border border-border px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                      {badge}
                      {battle?.ranked === false ? " · unranked" : ""}
                    </span>
                  )}
                  {brief && (
                    <p className="max-w-[72ch] text-[13px] leading-5 text-muted">{brief}</p>
                  )}
                  {battle?.spec_hash && (
                    <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                      spec {String(battle.spec_hash).slice(0, 16)}
                    </div>
                  )}
                </div>
              );
            })()}
            <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              <button
                type="button"
                onClick={copyBattleId}
                className="flex items-center gap-1 hover:text-foreground"
                title="Copy battle id"
              >
                {copiedId ? (
                  <Check className="h-3 w-3" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
                {String(id).slice(0, 8)}
              </button>
              <span className="flex items-center gap-1">
                <Eye className="h-3 w-3" />
                {battle?.round_visibility || "isolated"}
              </span>
              <span className="flex items-center gap-1">
                <Clock3 className="h-3 w-3" />
                {battle?.timeout_seconds || 600}s
              </span>
              <span className="flex items-center gap-1">
                <Activity className="h-3 w-3" />
                {arts.length} events / {modelIds.length} agents
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={busy === "save" || !!battle?.saved}
              className="btn btn-ghost h-10 px-4 text-[11px]"
            >
              <Save className="h-3.5 w-3.5" />{" "}
              {battle?.saved ? "Saved" : "Save"}
            </button>
            <button
              type="button"
              onClick={cancel}
              disabled={busy === "cancel" || TERMINAL_STATES.has(status)}
              className="btn btn-danger h-10 px-4 text-[11px]"
            >
              <Square className="h-3.5 w-3.5" /> Stop
            </button>
          </div>
        </div>

        <div className="flex min-h-[48px] items-center gap-0 overflow-x-auto border-t border-border">
          <span className="shrink-0 px-6 font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
            Phase
          </span>
          {phases.map((itemPhase, index) => {
            const active = itemPhase === phase && !TERMINAL_STATES.has(status);
            const phaseIndex = phases.indexOf(phase);
            const done = TERMINAL_STATES.has(status) || index < phaseIndex;
            return (
              <button
                key={`${itemPhase}-${index}`}
                type="button"
                onClick={() => setActivityFilter(itemPhase)}
                className={`flex h-12 shrink-0 items-center gap-2 border-l border-border px-4 font-mono text-[10px] uppercase tracking-[0.12em] ${active ? "bg-accent text-accent-fg" : done ? "text-accent" : "text-muted"}`}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <span>{itemPhase}</span>
                {active ? (
                  <Radio className="h-3 w-3 animate-pulse" />
                ) : done ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : null}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setActivityFilter("all")}
            className={`ml-auto h-12 shrink-0 border-l border-border px-4 font-mono text-[10px] uppercase tracking-[0.12em] ${activityFilter === "all" ? "bg-foreground text-background" : "text-muted"}`}
          >
            all
          </button>
        </div>
      </section>

      {err && (
        <div className="flex items-start gap-3 border-b border-danger px-6 py-3 text-[11px] text-danger">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1 break-words font-mono">{err}</span>
          <button
            type="button"
            onClick={() => setErr(null)}
            className="shrink-0 underline underline-offset-2"
          >
            dismiss
          </button>
        </div>
      )}

      <div className="mx-auto grid max-w-[1360px] grid-cols-12">
        {fighters.map((modelId, index) => {
          const modelHistory = histories.get(modelId) || [];
          const artifactHistory = modelHistory.filter(
            (item) => !item.kind || item.kind === "artifact",
          );
          const latest =
            artifactHistory[artifactHistory.length - 1]?.artifact ||
            modelHistory[modelHistory.length - 1]?.artifact ||
            "";
          const paneColor = "accent";
          return (
            <div
              key={modelId}
              className="col-span-12 border-b border-border lg:col-span-6 lg:border-r lg:last:border-r-0"
            >
              <CodePane
                modelId={modelId}
                label={modelId}
                role={index === 1 ? "breaker" : "builder"}
                code={latest}
                history={artifactHistory}
                events={modelHistory}
                status={status}
                color={paneColor}
                previewUrl={previewUrls[modelId]}
                artifactMeta={`${(latest.length / 1024).toFixed(1)}kb · ${latest ? latest.split("\n").length : 0} lines`}
                win={winner === modelId && status === "completed"}
                winText="winner"
                protectedFiles={index === 1 || battle?.format_id?.includes("auth") ? ["auth.py"] : []}
              />
            </div>
          );
        })}
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12 border-t border-border">
        <section className="col-span-12 min-h-0 overflow-hidden lg:col-span-8 lg:border-r lg:border-border">
          <header className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em]">
                Activity
              </div>
              <div className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                newest first
              </div>
            </div>
            <div className="flex items-center gap-0 overflow-x-auto">
              <button
                type="button"
                onClick={() => setActivityFilter("all")}
                className={`px-2 py-1 font-mono text-[9px] uppercase ${activityFilter === "all" ? "bg-accent text-accent-fg" : "text-muted"}`}
              >
                all
              </button>
              {phases.map((itemPhase) => (
                <button
                  key={itemPhase}
                  type="button"
                  onClick={() => setActivityFilter(itemPhase)}
                  className={`px-2 py-1 font-mono text-[9px] uppercase ${activityFilter === itemPhase ? "bg-accent text-accent-fg" : "text-muted"}`}
                >
                  {itemPhase}
                </button>
              ))}
            </div>
          </header>

          <div className="h-[230px] overflow-auto bg-code p-0">
            {activity.length ? (
              <div>
                {activity.map((item, index) => {
                  const isTool = item.kind === "action_log";
                  const isArtifact = item.kind === "artifact";
                  return (
                    <div
                      key={`${item.t}-${index}`}
                      className="grid grid-cols-[66px_68px_90px_minmax(0,1fr)] items-start gap-2 border-b border-codeBorder px-4 py-2 font-mono text-[9px] leading-4"
                    >
                      <span className="text-lineNo">{timeLabel(item.t)}</span>
                      <span
                        className={
                          isTool || isArtifact ? "text-accent" : "text-muted"
                        }
                      >
                        {eventLabel(item.kind)}
                      </span>
                      <span className="truncate text-lineNo">
                        {item.model_id}
                      </span>
                      <span className="min-w-0 text-codeFg/85">
                        <span className="mr-2 uppercase text-lineNo">
                          {item.phase}
                        </span>
                        {preview(item.artifact)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <Activity className="mx-auto h-5 w-5 text-lineNo" />
                  <div className="mt-2 font-mono text-[9px] uppercase tracking-[0.12em] text-lineNo">
                    Waiting for activity
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="col-span-12 overflow-hidden lg:col-span-4">
          <header className="flex items-center justify-between border-b border-border px-6 py-3">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em]">
                Judge
              </div>
              <div className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                verified scores only
              </div>
            </div>
            <Trophy className="h-4 w-4 text-muted" />
          </header>

          <div className="h-[230px] overflow-auto">
            {scores && Object.keys(scores).length ? (
              <div>
                {Object.entries(scores)
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .map(([model, score], index) => (
                    <div
                      key={model}
                      className={`flex items-center justify-between gap-3 border-b border-border px-6 py-4 ${winner === model ? "bg-accent text-accent-fg" : ""}`}
                    >
                      <div className="min-w-0">
                        <div className="font-mono text-[9px] uppercase tracking-[0.14em] opacity-70">
                          #{index + 1} {winner === model ? "win" : ""}
                        </div>
                        <div className="mt-1 truncate font-mono text-[12px]">
                          {model}
                        </div>
                      </div>
                      <div className="font-display text-[40px] leading-none tracking-[-0.05em]">
                        {Number(score).toFixed(Number(score) % 1 ? 1 : 0)}
                      </div>
                    </div>
                  ))}
              </div>
            ) : (
              <div className="grid h-full place-items-center px-6 text-center">
                <div className="max-w-[240px]">
                  <div className="font-display text-[28px] leading-none text-muted">
                    VS
                  </div>
                  <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em]">
                    Judge pending
                  </div>
                  <p className="mt-2 text-[11px] leading-5 text-muted">
                    Scores appear only when the backend emits a real judge
                    result.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
