/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  ChevronDown,
  Code2,
  Copy,
  ExternalLink,
  Eye,
  FileCode2,
  Hammer,
  Layers,
  Lock,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Swords,
  Target,
  Terminal,
  TerminalSquare,
  X,
  XCircle,
} from "lucide-react";
import type { BattleOut, TargetDetailOut } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BattleStreamItem, SkillActivity } from "./types";
import {
  artifactFiles,
  parseAction,
  shortModelName,
  timeLabel,
  titleCase,
} from "./utils";

type Props = {
  battle: BattleOut | null;
  status: string;
  phase: string;
  pipeline: string[];
  modelIds: string[];
  modelName: (id: string) => string;
  roleForModel: (id: string, index: number) => string;
  targetDetail: TargetDetailOut | null;
  events: BattleStreamItem[];
  histories: Map<string, BattleStreamItem[]>;
  skillActivity: SkillActivity[];
  scores: Record<string, any> | null;
  previewUrls: Record<string, string>;
  selectedModelId: string | null;
  onSelectModelId: (id: string) => void;
  onSwitchToDeepDive: () => void;
};

type SpectatorTab = "split" | "target" | "hud";

export default function SpectatorArenaView({
  battle,
  status,
  phase,
  pipeline,
  modelIds,
  modelName,
  roleForModel,
  targetDetail,
  events,
  histories,
  scores,
  previewUrls,
  onSelectModelId,
  onSwitchToDeepDive,
}: Props) {
  const [activeTab, setActiveTab] = useState<SpectatorTab>("split");
  const [inspectFile, setInspectFile] = useState<{ name: string; content: string; author: string } | null>(null);

  // 1. Identify Builder and Breaker
  const builderModelId = useMemo(() => {
    const found = modelIds.find((id, idx) =>
      roleForModel(id, idx).toLowerCase().includes("builder")
    );
    return found || modelIds[0] || "";
  }, [modelIds, roleForModel]);

  const breakerModelId = useMemo(() => {
    const found = modelIds.find((id, idx) =>
      roleForModel(id, idx).toLowerCase().includes("breaker")
    );
    return found || (modelIds.length > 1 ? modelIds[1] : "");
  }, [modelIds, roleForModel]);

  const builderHistory = useMemo(() => histories.get(builderModelId) || [], [histories, builderModelId]);
  const breakerHistory = useMemo(() => histories.get(breakerModelId) || [], [histories, breakerModelId]);

  // 2. Builder Measurements & Artifacts
  const builderActions = useMemo(() => {
    return builderHistory.map((item) => ({ item, action: parseAction(item) })).filter((r) => r.action);
  }, [builderHistory]);

  const builderArtifacts = useMemo(() => {
    return builderHistory.filter((item) => item.kind === "artifact");
  }, [builderHistory]);

  const latestBuilderArtifact = builderArtifacts[builderArtifacts.length - 1]?.artifact || "";
  const builderFiles = useMemo(() => artifactFiles(latestBuilderArtifact) || {}, [latestBuilderArtifact]);
  const builderFileNames = useMemo(() => Object.keys(builderFiles).sort(), [builderFiles]);

  // 3. Breaker Measurements & Artifacts
  const breakerActions = useMemo(() => {
    return breakerHistory.map((item) => ({ item, action: parseAction(item) })).filter((r) => r.action);
  }, [breakerHistory]);

  const breakerArtifacts = useMemo(() => {
    return breakerHistory.filter((item) => item.kind === "artifact");
  }, [breakerHistory]);

  const latestBreakerArtifact = breakerArtifacts[breakerArtifacts.length - 1]?.artifact || "";
  const breakerFiles = useMemo(() => artifactFiles(latestBreakerArtifact) || {}, [latestBreakerArtifact]);
  const breakerFileNames = useMemo(() => Object.keys(breakerFiles).sort(), [breakerFiles]);

  // 4. Verification Evidence & Exploit Vectors
  const verificationEvents = useMemo(() => {
    return events.filter((e) => e.kind === "verification" || e.payload?.verification_status);
  }, [events]);

  const latestVerification = verificationEvents[verificationEvents.length - 1]?.payload;
  const breakerEvidence = (latestVerification?.breaker_semantic_evidence as Record<string, any> | undefined) || {};

  const exploitVectors = useMemo(() => ({
    server_crashed: Boolean(breakerEvidence.server_crashed),
    availability_degraded: Boolean(breakerEvidence.availability_degraded),
    unauthorized_mutation: Boolean(breakerEvidence.unauthorized_mutation),
    flag_captured: Boolean(breakerEvidence.flag_captured),
  }), [breakerEvidence]);

  const isBreakerActive = phase.toLowerCase().includes("break") || phase.toLowerCase().includes("attack");
  const isBuilderActive = phase.toLowerCase().includes("build") || phase.toLowerCase().includes("harden");
  const isFreezeDone = isBreakerActive || status === "completed";

  const previewUrl = previewUrls[builderModelId] || previewUrls[breakerModelId] || Object.values(previewUrls)[0] || "";

  // Terminal Auto-Scroll Refs
  const builderTermRef = useRef<HTMLDivElement | null>(null);
  const breakerTermRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (builderTermRef.current) {
      builderTermRef.current.scrollTop = builderTermRef.current.scrollHeight;
    }
  }, [builderActions.length]);

  useEffect(() => {
    if (breakerTermRef.current) {
      breakerTermRef.current.scrollTop = breakerTermRef.current.scrollHeight;
    }
  }, [breakerActions.length]);

  return (
    <div className="space-y-5">
      {/* 1. BROADCAST MATCHUP HEADER & HANDOFF PIPELINE */}
      <section className="rounded-2xl border border-white/10 bg-[#0D1017] p-4 lg:p-5 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-0 left-0 w-96 h-96 bg-fuchsia-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
          {/* Builder Head */}
          <div
            onClick={() => onSelectModelId(builderModelId)}
            className="lg:col-span-4 flex items-center gap-3.5 p-3 rounded-xl bg-[#121622]/80 border border-cyan-500/20 hover:border-cyan-500/40 transition cursor-pointer"
          >
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0">
              <Hammer className="w-5 h-5 text-cyan-400" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">BUILDER</span>
                <span className={cn(
                  "px-1.5 py-0.2 text-[9px] font-mono font-semibold rounded border",
                  isBuilderActive
                    ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse"
                    : isFreezeDone
                    ? "bg-slate-800 text-slate-300 border-white/10"
                    : "bg-slate-900 text-slate-500 border-white/5"
                )}>
                  {isBuilderActive ? "BUILDING" : isFreezeDone ? "FROZEN" : "WAITING"}
                </span>
              </div>
              <h3 className="text-sm font-bold text-white truncate mt-0.5">{modelName(builderModelId)}</h3>
              <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 mt-0.5">
                <span>{builderActions.length} actions</span>
                <span>·</span>
                <span>{builderFileNames.length} files</span>
              </div>
            </div>
            <div className="text-right pl-2 border-l border-white/10 shrink-0">
              <span className="text-[10px] font-mono text-slate-400 block">SCORE</span>
              <span className="text-xl font-bold font-mono text-cyan-300">
                {scores?.[builderModelId]?.total ?? scores?.[builderModelId] ?? "—"}
              </span>
            </div>
          </div>

          {/* Central Handoff & Pipeline Flow */}
          <div className="lg:col-span-4 flex flex-col items-center justify-center px-2 py-1 text-center">
            <div className="flex items-center gap-1 sm:gap-2 mb-2 w-full justify-center">
              <div className={cn(
                "px-2.5 py-1 rounded-md text-[10px] font-mono font-bold border transition-all flex items-center gap-1.5",
                isBuilderActive
                  ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-[0_0_12px_rgba(0,210,255,0.3)]"
                  : "bg-black/30 text-slate-500 border-white/5"
              )}>
                <Hammer className="w-3 h-3" />
                <span>BUILD</span>
              </div>

              <span className="text-slate-600 font-mono text-xs">→</span>

              <div className={cn(
                "px-2.5 py-1 rounded-md text-[10px] font-mono font-bold border transition-all flex items-center gap-1.5",
                isFreezeDone
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : "bg-black/30 text-slate-500 border-white/5"
              )}>
                <Lock className="w-3 h-3" />
                <span>FREEZE</span>
              </div>

              <span className="text-slate-600 font-mono text-xs">→</span>

              <div className={cn(
                "px-2.5 py-1 rounded-md text-[10px] font-mono font-bold border transition-all flex items-center gap-1.5",
                isBreakerActive
                  ? "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/50 shadow-[0_0_12px_rgba(217,70,239,0.3)] animate-pulse"
                  : "bg-black/30 text-slate-500 border-white/5"
              )}>
                <Bug className="w-3 h-3" />
                <span>ATTACK</span>
              </div>

              <span className="text-slate-600 font-mono text-xs">→</span>

              <div className={cn(
                "px-2.5 py-1 rounded-md text-[10px] font-mono font-bold border transition-all flex items-center gap-1.5",
                battle?.verification_status === "verified_pass"
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : battle?.verification_status === "verified_fail"
                  ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                  : "bg-black/30 text-slate-500 border-white/5"
              )}>
                <Shield className="w-3 h-3" />
                <span>VERIFY</span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-[10px] font-mono text-slate-400">
              <span className="flex items-center gap-1">
                <Target className="w-3 h-3 text-cyan-400" />
                <span className="text-white font-medium truncate max-w-[140px]">{targetDetail?.name || battle?.target_id || "Target App"}</span>
              </span>
              <span>·</span>
              <span className="text-slate-500">SHA: {battle?.spec_hash?.slice(0, 8) || "8f29c41d"}</span>
            </div>
          </div>

          {/* Breaker Head */}
          <div
            onClick={() => onSelectModelId(breakerModelId)}
            className="lg:col-span-4 flex items-center gap-3.5 p-3 rounded-xl bg-[#121622]/80 border border-fuchsia-500/20 hover:border-fuchsia-500/40 transition cursor-pointer"
          >
            <div className="text-left pr-2 border-r border-white/10 shrink-0">
              <span className="text-[10px] font-mono text-slate-400 block">SCORE</span>
              <span className="text-xl font-bold font-mono text-fuchsia-400">
                {scores?.[breakerModelId]?.total ?? scores?.[breakerModelId] ?? "0.0"}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-fuchsia-400">BREAKER</span>
                <span className={cn(
                  "px-1.5 py-0.2 text-[9px] font-mono font-semibold rounded border",
                  isBreakerActive
                    ? "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40 animate-pulse"
                    : "bg-slate-900 text-slate-500 border-white/5"
                )}>
                  {isBreakerActive ? "ATTACKING" : "WAITING"}
                </span>
              </div>
              <h3 className="text-sm font-bold text-white truncate mt-0.5">{modelName(breakerModelId)}</h3>
              <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 mt-0.5">
                <span>{breakerActions.length} probes</span>
                <span>·</span>
                <span>{breakerFileNames.length ? `${breakerFileNames.length} artifacts` : "exploit ready"}</span>
              </div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-fuchsia-500/10 border border-fuchsia-500/30 flex items-center justify-center shrink-0">
              <Swords className="w-5 h-5 text-fuchsia-400" />
            </div>
          </div>
        </div>

        {/* Sub-navigation bar */}
        <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-1.5 bg-black/40 p-1 rounded-xl border border-white/5">
            <button
              type="button"
              onClick={() => setActiveTab("split")}
              className={cn(
                "px-3 py-1 text-xs font-mono font-medium rounded-lg transition flex items-center gap-1.5",
                activeTab === "split"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold"
                  : "text-slate-400 hover:text-white"
              )}
            >
              <TerminalSquare className="w-3.5 h-3.5" /> Split Terminals
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("target")}
              className={cn(
                "px-3 py-1 text-xs font-mono font-medium rounded-lg transition flex items-center gap-1.5",
                activeTab === "target"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold"
                  : "text-slate-400 hover:text-white"
              )}
            >
              <Target className="w-3.5 h-3.5" /> Target App Screen
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("hud")}
              className={cn(
                "px-3 py-1 text-xs font-mono font-medium rounded-lg transition flex items-center gap-1.5",
                activeTab === "hud"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold"
                  : "text-slate-400 hover:text-white"
              )}
            >
              <ShieldAlert className="w-3.5 h-3.5" /> Exploit Vectors HUD
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onSwitchToDeepDive}
              className="text-xs font-mono text-slate-400 hover:text-cyan-300 flex items-center gap-1 transition"
            >
              <Terminal className="w-3.5 h-3.5" /> Deep Dive Workspace
            </button>
          </div>
        </div>
      </section>

      {/* 2. DUAL SPLIT-SCREEN TERMINAL VIEW (DEFAULT FOR SPECTATORS) */}
      {activeTab === "split" ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* LEFT: BUILDER CONSOLE */}
          <section className="rounded-2xl border border-cyan-500/30 bg-[#090B10] flex flex-col overflow-hidden shadow-xl">
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#0D1017] border-b border-white/10">
              <div className="flex items-center gap-2.5">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                </div>
                <span className="font-mono text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <Hammer className="w-3.5 h-3.5 text-cyan-400" />
                  BUILDER CONSOLE
                </span>
                <span className="font-mono text-[10px] text-slate-500">
                  [{modelName(builderModelId)}]
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-slate-400">
                  {builderActions.length} commands
                </span>
                <span className={cn(
                  "w-2 h-2 rounded-full",
                  isBuilderActive ? "bg-cyan-400 animate-ping" : isFreezeDone ? "bg-slate-600" : "bg-zinc-700"
                )} />
              </div>
            </div>

            {/* Terminal Output Body */}
            <div
              ref={builderTermRef}
              className="h-[380px] overflow-y-auto p-4 font-mono text-[11.5px] leading-relaxed space-y-3 bg-[#08090D]"
            >
              {builderActions.length ? (
                builderActions.map(({ item, action }, idx) => {
                  if (!action) return null;
                  const isFail = action.state === "failed" || action.state === "error";
                  const isRun = action.state === "running" || action.state === "starting";
                  return (
                    <div key={`bld-${action.tool_call_id || idx}`} className="space-y-1">
                      <div className="flex items-start gap-2">
                        <span className="text-zinc-600 select-none text-[10px] pt-0.5">{timeLabel(item.t)}</span>
                        <span className={cn("select-none font-bold", isFail ? "text-rose-400" : isRun ? "text-cyan-400 animate-pulse" : "text-cyan-400")}>
                          ›
                        </span>
                        <span className="text-zinc-100 font-semibold break-words flex-1">{action.command}</span>
                      </div>
                      {action.result ? (
                        <pre className={cn(
                          "ml-7 p-2 rounded-lg text-[10.5px] whitespace-pre-wrap break-words border",
                          isFail ? "bg-rose-950/30 text-rose-300 border-rose-500/20" : "bg-black/50 text-slate-300 border-white/5"
                        )}>
                          {action.result}
                        </pre>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center text-slate-500">
                  <TerminalSquare className="w-8 h-8 opacity-40 mb-2 text-cyan-400" />
                  <p className="text-xs">Awaiting builder action stream...</p>
                  <p className="text-[10px] text-slate-600 mt-1">Commands, test executions, and files will appear live here.</p>
                </div>
              )}
            </div>

            {/* Terminal Footer / Files Drawer */}
            <div className="px-4 py-2 bg-[#0D1017] border-t border-white/10 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 overflow-x-auto py-0.5">
                <span className="text-[10px] text-slate-500 uppercase">Files:</span>
                {builderFileNames.length ? (
                  builderFileNames.map((file) => (
                    <button
                      key={file}
                      type="button"
                      onClick={() => setInspectFile({ name: file, content: builderFiles[file] || "", author: "Builder" })}
                      className="px-2 py-0.5 rounded bg-white/5 hover:bg-cyan-500/20 hover:text-cyan-300 text-slate-300 text-[10px] transition flex items-center gap-1 shrink-0"
                    >
                      <FileCode2 className="w-3 h-3 text-cyan-400" />
                      {file}
                    </button>
                  ))
                ) : (
                  <span className="text-slate-600 text-[10px]">No files written yet</span>
                )}
              </div>
              <span className="text-[10px] text-slate-500 shrink-0 pl-2">
                Workspace: Private
              </span>
            </div>
          </section>

          {/* RIGHT: BREAKER CONSOLE */}
          <section className="rounded-2xl border border-fuchsia-500/30 bg-[#090B10] flex flex-col overflow-hidden shadow-xl">
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#0D1017] border-b border-white/10">
              <div className="flex items-center gap-2.5">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                </div>
                <span className="font-mono text-xs font-bold text-fuchsia-300 flex items-center gap-1.5">
                  <Bug className="w-3.5 h-3.5 text-fuchsia-400" />
                  BREAKER CONSOLE
                </span>
                <span className="font-mono text-[10px] text-slate-500">
                  [{modelName(breakerModelId)}]
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-slate-400">
                  {breakerActions.length} probes
                </span>
                <span className={cn(
                  "w-2 h-2 rounded-full",
                  isBreakerActive ? "bg-fuchsia-400 animate-ping" : "bg-zinc-700"
                )} />
              </div>
            </div>

            {/* Terminal Output Body */}
            <div
              ref={breakerTermRef}
              className="h-[380px] overflow-y-auto p-4 font-mono text-[11.5px] leading-relaxed space-y-3 bg-[#08090D]"
            >
              {breakerActions.length ? (
                breakerActions.map(({ item, action }, idx) => {
                  if (!action) return null;
                  const isFail = action.state === "failed" || action.state === "error";
                  const isRun = action.state === "running" || action.state === "starting";
                  return (
                    <div key={`brk-${action.tool_call_id || idx}`} className="space-y-1">
                      <div className="flex items-start gap-2">
                        <span className="text-zinc-600 select-none text-[10px] pt-0.5">{timeLabel(item.t)}</span>
                        <span className={cn("select-none font-bold", isFail ? "text-rose-400" : isRun ? "text-fuchsia-400 animate-pulse" : "text-fuchsia-400")}>
                          ›
                        </span>
                        <span className="text-zinc-100 font-semibold break-words flex-1">{action.command}</span>
                      </div>
                      {action.result ? (
                        <pre className={cn(
                          "ml-7 p-2 rounded-lg text-[10.5px] whitespace-pre-wrap break-words border",
                          isFail ? "bg-rose-950/30 text-rose-300 border-rose-500/20" : "bg-black/50 text-slate-300 border-white/5"
                        )}>
                          {action.result}
                        </pre>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center text-slate-500">
                  <Swords className="w-8 h-8 opacity-40 mb-2 text-fuchsia-400" />
                  <p className="text-xs">
                    {isBuilderActive
                      ? "Awaiting Builder completion & handoff freeze..."
                      : "Awaiting breaker exploit probing..."}
                  </p>
                  <p className="text-[10px] text-slate-600 mt-1">Autonomous exploit payloads and curl responses will appear live here.</p>
                </div>
              )}
            </div>

            {/* Terminal Footer / Exploit Artifacts */}
            <div className="px-4 py-2 bg-[#0D1017] border-t border-white/10 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 overflow-x-auto py-0.5">
                <span className="text-[10px] text-slate-500 uppercase">Exploits:</span>
                {breakerFileNames.length ? (
                  breakerFileNames.map((file) => (
                    <button
                      key={file}
                      type="button"
                      onClick={() => setInspectFile({ name: file, content: breakerFiles[file] || "", author: "Breaker" })}
                      className="px-2 py-0.5 rounded bg-white/5 hover:bg-fuchsia-500/20 hover:text-fuchsia-300 text-slate-300 text-[10px] transition flex items-center gap-1 shrink-0"
                    >
                      <Bug className="w-3 h-3 text-fuchsia-400" />
                      {file}
                    </button>
                  ))
                ) : (
                  <span className="text-slate-600 text-[10px]">exploit.py active in memory</span>
                )}
              </div>
              <span className="text-[10px] text-slate-500 shrink-0 pl-2">
                Sandbox: Isolated
              </span>
            </div>
          </section>
        </div>
      ) : null}

      {/* 3. TARGET APP SCREEN TAB */}
      {activeTab === "target" ? (
        <section className="rounded-2xl border border-white/15 bg-[#0D1017] p-6 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-4">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-cyan-400" />
              <div>
                <h3 className="text-base font-bold text-white">
                  {targetDetail?.name || titleCase(battle?.target_id || "Target Application")}
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  Container Endpoint: {previewUrl ? previewUrl : "http://localhost:5173 / :8000"}
                </span>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold">
              ● {status.toUpperCase()}
            </span>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#080A0F] overflow-hidden min-h-[340px] flex flex-col justify-center items-center text-center p-6">
            {previewUrl ? (
              <iframe src={previewUrl} title="Live Preview" className="w-full h-[340px] border-0 bg-white rounded-lg shadow-inner" />
            ) : (
              <div className="max-w-md">
                <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-2xl text-cyan-400">
                  🏦
                </div>
                <h4 className="text-lg font-bold text-white">
                  {targetDetail?.name || "Quantum Bank Vault"}
                </h4>
                <p className="text-xs text-slate-400 mt-2 font-mono leading-relaxed">
                  FastAPI backend on :8000 · Vite frontend on :5173 · Ephemeral Neon Postgres DB
                </p>
                {targetDetail?.objectives?.length ? (
                  <div className="mt-4 p-3 rounded-xl bg-black/40 border border-white/5 text-left text-xs font-mono text-slate-300 space-y-1.5">
                    <span className="text-[10px] text-cyan-400 uppercase tracking-wider block font-bold">Target Objectives:</span>
                    {targetDetail.objectives.map((obj, i) => (
                      <div key={i} className="flex items-start gap-2 text-slate-400">
                        <span className="text-cyan-400 mt-0.5">•</span>
                        <span>{obj}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </section>
      ) : null}

      {/* 4. ASYMMETRIC VERIFICATION & EXPLOIT VECTORS HUD */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-fuchsia-400" />
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300">
              Asymmetric Exploit Vectors HUD
            </h3>
          </div>
          <span className="text-[11px] font-mono text-slate-500">
            Isolated Host Verifier Audited
          </span>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
          {/* Vector 1 */}
          <div className={cn(
            "p-3.5 rounded-xl border transition flex flex-col justify-between",
            exploitVectors.server_crashed
              ? "bg-rose-950/30 border-rose-500/40 text-rose-200"
              : "bg-[#10141F] border-white/5 text-slate-400"
          )}>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider block text-slate-500">Vector 1</span>
              <h4 className="text-xs font-bold font-mono text-white mt-1">server_crashed</h4>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug">500 error / unhandled process crash</p>
            </div>
            <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between font-mono text-[11px]">
              <span>Status:</span>
              <span className={cn("font-bold", exploitVectors.server_crashed ? "text-rose-400" : "text-emerald-400")}>
                {exploitVectors.server_crashed ? "CRASHED ●" : "RESILIENT ○"}
              </span>
            </div>
          </div>

          {/* Vector 2 */}
          <div className={cn(
            "p-3.5 rounded-xl border transition flex flex-col justify-between",
            exploitVectors.availability_degraded
              ? "bg-amber-950/30 border-amber-500/40 text-amber-200"
              : "bg-[#10141F] border-white/5 text-slate-400"
          )}>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider block text-slate-500">Vector 2</span>
              <h4 className="text-xs font-bold font-mono text-white mt-1">availability_degraded</h4>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug">Latency spike / resource exhaustion</p>
            </div>
            <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between font-mono text-[11px]">
              <span>Status:</span>
              <span className={cn("font-bold", exploitVectors.availability_degraded ? "text-amber-400" : "text-emerald-400")}>
                {exploitVectors.availability_degraded ? "DEGRADED ●" : "HEALTHY ○"}
              </span>
            </div>
          </div>

          {/* Vector 3 */}
          <div className={cn(
            "p-3.5 rounded-xl border transition flex flex-col justify-between",
            exploitVectors.unauthorized_mutation
              ? "bg-fuchsia-950/30 border-fuchsia-500/40 text-fuchsia-200"
              : "bg-[#10141F] border-white/5 text-slate-400"
          )}>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider block text-slate-500">Vector 3</span>
              <h4 className="text-xs font-bold font-mono text-white mt-1">unauthorized_mutation</h4>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug">Auth bypass / unauthorized state change</p>
            </div>
            <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between font-mono text-[11px]">
              <span>Status:</span>
              <span className={cn("font-bold", exploitVectors.unauthorized_mutation ? "text-fuchsia-400" : "text-emerald-400")}>
                {exploitVectors.unauthorized_mutation ? "MUTATED ●" : "GUARDED ○"}
              </span>
            </div>
          </div>

          {/* Vector 4 */}
          <div className={cn(
            "p-3.5 rounded-xl border transition flex flex-col justify-between",
            exploitVectors.flag_captured
              ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-200"
              : "bg-[#10141F] border-white/5 text-slate-400"
          )}>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider block text-slate-500">Vector 4</span>
              <h4 className="text-xs font-bold font-mono text-white mt-1">flag_captured</h4>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug">Confidential flag / credential exfiltration</p>
            </div>
            <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between font-mono text-[11px]">
              <span>Status:</span>
              <span className={cn("font-bold", exploitVectors.flag_captured ? "text-emerald-400" : "text-slate-500")}>
                {exploitVectors.flag_captured ? "EXFILTRATED ●" : "SECURED ○"}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 5. CLAIM VS VERIFIED GROUND TRUTH MATRIX */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Breaker Claim */}
        <div className="rounded-2xl border border-white/10 bg-[#10141F] p-5">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Bug className="w-3.5 h-3.5 text-fuchsia-400" />
              Breaker Claim (Self-Reported)
            </span>
            <span className="text-[11px] font-mono text-slate-500">Untrusted by default</span>
          </div>
          <p className="text-sm font-mono text-slate-300 leading-relaxed">
            {isBreakerActive
              ? "Breaker is actively probing target routes. Autonomous claims submitted will require Arena host verification."
              : breakerActions.length
              ? `Breaker recorded ${breakerActions.length} attack probes against the target.`
              : "No exploit claims submitted during this phase."}
          </p>
        </div>

        {/* Arena Trusted Verifier */}
        <div className="rounded-2xl border border-cyan-500/30 bg-[#10141F] p-5">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-cyan-300 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              Arena Trusted Verifier (Ground Truth)
            </span>
            <span className={cn(
              "text-[11px] font-mono font-bold px-2 py-0.5 rounded border",
              battle?.verification_status === "verified_pass"
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                : battle?.verification_status === "verified_fail"
                ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                : "bg-slate-900 text-slate-400 border-white/10"
            )}>
              {battle?.verification_status ? battle.verification_status.toUpperCase() : "AUDITING IDLE"}
            </span>
          </div>
          <p className="text-sm font-mono text-slate-300 leading-relaxed">
            {battle?.verification_status === "verified_pass"
              ? "● VERIFIED BY ARENA: Ground-truth postconditions and security invariants audited officially in isolated microVM."
              : battle?.verification_status === "verified_fail"
              ? "× VERIFICATION FAILED: Invariants breached or exploit confirmed by host verifier."
              : "The Arena verifier audits the ephemeral database and microVM state independently. Fighter claims carry zero score without verified evidence."}
          </p>
        </div>
      </section>

      {/* 6. MODAL INSPECT FILE DRAWER */}
      {inspectFile ? (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-3xl max-h-[85vh] rounded-2xl border border-white/15 bg-[#0D1017] shadow-2xl flex flex-col overflow-hidden">
            <div className="px-5 py-3.5 border-b border-white/10 flex items-center justify-between bg-[#121622]">
              <div className="flex items-center gap-2">
                <FileCode2 className="w-4 h-4 text-cyan-400" />
                <span className="font-mono text-xs font-bold text-white">{inspectFile.name}</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/5">
                  Author: {inspectFile.author}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setInspectFile(null)}
                className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <pre className="p-5 font-mono text-xs text-slate-200 overflow-auto flex-1 bg-[#08090D] leading-relaxed whitespace-pre-wrap">
              {inspectFile.content}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}
