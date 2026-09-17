/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Lock,
  Shield,
  Swords,
  Target,
  Terminal,
  XCircle,
} from "lucide-react";
import type { BattleOut, TargetDetailOut } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BattleStreamItem, SkillActivity } from "./types";
import {
  artifactFiles,
  parseAction,
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

  // 2. Builder Measurements
  const builderActions = useMemo(() => {
    return builderHistory.map((item) => ({ item, action: parseAction(item) })).filter((r) => r.action);
  }, [builderHistory]);

  const builderArtifacts = useMemo(() => {
    return builderHistory.filter((item) => item.kind === "artifact");
  }, [builderHistory]);

  const latestBuilderArtifact = builderArtifacts[builderArtifacts.length - 1]?.artifact || "";
  const builderFiles = useMemo(() => artifactFiles(latestBuilderArtifact) || {}, [latestBuilderArtifact]);
  const builderFileCount = Object.keys(builderFiles).length;

  // 3. Breaker Measurements
  const breakerActions = useMemo(() => {
    return breakerHistory.map((item) => ({ item, action: parseAction(item) })).filter((r) => r.action);
  }, [breakerHistory]);

  // 4. Verification Evidence & Exploit Vectors
  const verificationEvents = useMemo(() => {
    return events.filter((e) => e.kind === "verification" || e.payload?.verification_status);
  }, [events]);

  const latestVerification = verificationEvents[verificationEvents.length - 1]?.payload;
  const breakerEvidence = (latestVerification?.breaker_semantic_evidence as Record<string, boolean> | undefined) || {};

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

  return (
    <div className="space-y-6">
      {/* MAIN 3-COLUMN BROADCAST STAGE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        
        {/* LEFT COLUMN: BUILDER CARD (3 cols) */}
        <section
          onClick={() => onSelectModelId(builderModelId)}
          className={cn(
            "lg:col-span-3 rounded-2xl border bg-[#10141F] p-5 flex flex-col justify-between transition-all cursor-pointer shadow-lg",
            isBuilderActive
              ? "border-cyan-500/60 shadow-[0_0_25px_rgba(0,210,255,0.12)]"
              : "border-white/10 opacity-80"
          )}
        >
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div>
                <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-cyan-400">Builder</span>
                <h2 className="text-base font-bold text-white mt-0.5">{modelName(builderModelId)}</h2>
              </div>
              <span
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold border",
                  isBuilderActive
                    ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse"
                    : isFreezeDone
                    ? "bg-slate-800 text-slate-300 border-white/10"
                    : "bg-slate-900 text-slate-500 border-white/5"
                )}
              >
                {isBuilderActive ? "BUILDING ●" : isFreezeDone ? "FROZEN 🔒" : "WAITING ○"}
              </span>
            </div>

            {/* Score */}
            <div className="my-4 p-3.5 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">Builder Score</span>
              <span className="text-2xl font-bold font-mono text-cyan-300">
                {scores?.[builderModelId]?.total ?? scores?.[builderModelId] ?? "—"}
              </span>
            </div>

            {/* Clean Status List */}
            <div className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between py-1 border-b border-white/5">
                <span className="text-slate-400">Actions</span>
                <span className="font-mono text-white font-semibold">{builderActions.length}</span>
              </div>
              <div className="flex items-center justify-between py-1 border-b border-white/5">
                <span className="text-slate-400">Files Written</span>
                <span className="font-mono text-white font-semibold">{builderFileCount} files</span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span className="text-slate-400">Latest Command</span>
                <span className="font-mono text-cyan-300 truncate max-w-[120px]">
                  {builderActions[builderActions.length - 1]?.action.command || "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-5 pt-3 border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Workspace: 3-Tier Private</span>
            <button onClick={onSwitchToDeepDive} className="text-cyan-400 hover:underline flex items-center gap-1">
              <Terminal className="w-3 h-3" /> Logs
            </button>
          </div>
        </section>

        {/* CENTER COLUMN: THE TARGET APPLICATION (6 cols - THE STAR) */}
        <section className="lg:col-span-6 rounded-2xl border border-white/15 bg-[#0D1017] p-5 flex flex-col justify-between shadow-2xl relative">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-bold text-white">
                  {targetDetail?.name || titleCase(battle?.target_id || "Target Application")}
                </h3>
              </div>
              <span className="text-xs font-mono text-slate-400 bg-white/5 px-2.5 py-0.5 rounded border border-white/5">
                {previewUrl ? previewUrl : "http://localhost:5173"}
              </span>
            </div>

            {/* Application Screen Frame */}
            <div className="mt-4 rounded-xl border border-white/10 bg-[#080A0F] overflow-hidden min-h-[220px] flex flex-col justify-center items-center text-center p-6">
              {previewUrl ? (
                <iframe src={previewUrl} title="Live Preview" className="w-full h-[220px] border-0 bg-white rounded-lg" />
              ) : (
                <div className="max-w-sm">
                  <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-xl text-cyan-400">
                    🏦
                  </div>
                  <h4 className="text-base font-bold text-white">
                    {targetDetail?.name || "Quantum Bank Vault"}
                  </h4>
                  <p className="text-xs text-slate-400 mt-1 font-mono">
                    FastAPI backend on :8000 · Vite frontend on :5173 · Neon Postgres
                  </p>
                  <div className="mt-4 p-2.5 rounded-lg bg-white/5 border border-white/5 text-xs font-mono text-slate-300">
                    Status: <span className="text-emerald-400 font-bold">● {status.toUpperCase()}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* FREEZE / HANDOFF STATUS BANNER */}
          <div className="mt-4 p-3 rounded-xl border border-white/10 bg-black/40 flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-2 text-slate-400">
              <Lock className="w-3.5 h-3.5 text-cyan-400" />
              <span>Handoff:</span>
              <span className={cn("font-semibold", isFreezeDone ? "text-emerald-400" : "text-cyan-400")}>
                {isFreezeDone ? "ARTIFACT FROZEN — TARGET DEPLOYED" : "BUILDER PHASE ACTIVE"}
              </span>
            </div>
            <span className="text-[11px] text-slate-500">
              SHA: {battle?.spec_hash?.slice(0, 8) || "8f29c41d"}
            </span>
          </div>
        </section>

        {/* RIGHT COLUMN: BREAKER CARD (3 cols) */}
        <section
          onClick={() => onSelectModelId(breakerModelId)}
          className={cn(
            "lg:col-span-3 rounded-2xl border bg-[#10141F] p-5 flex flex-col justify-between transition-all cursor-pointer shadow-lg",
            isBreakerActive
              ? "border-fuchsia-500/60 shadow-[0_0_25px_rgba(217,70,239,0.15)]"
              : "border-white/10 opacity-70"
          )}
        >
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div>
                <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-fuchsia-400">Breaker</span>
                <h2 className="text-base font-bold text-white mt-0.5">{modelName(breakerModelId)}</h2>
              </div>
              <span
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold border",
                  isBreakerActive
                    ? "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/40 animate-pulse"
                    : "bg-slate-900 text-slate-500 border-white/5"
                )}
              >
                {isBreakerActive ? "ATTACKING ●" : "WAITING ○"}
              </span>
            </div>

            {/* Score */}
            <div className="my-4 p-3.5 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">Breaker Score</span>
              <span className="text-2xl font-bold font-mono text-fuchsia-400">
                {scores?.[breakerModelId]?.total ?? scores?.[breakerModelId] ?? "0.0"}
              </span>
            </div>

            {/* Exploit Vectors Status */}
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block mb-2">
              Exploit Vectors HUD
            </span>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between py-1 border-b border-white/5">
                <span className="text-slate-400">server_crashed</span>
                <span className={cn("font-semibold", exploitVectors.server_crashed ? "text-emerald-400" : "text-slate-500")}>
                  {exploitVectors.server_crashed ? "TRUE ●" : "FALSE ○"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1 border-b border-white/5">
                <span className="text-slate-400">availability_degraded</span>
                <span className={cn("font-semibold", exploitVectors.availability_degraded ? "text-emerald-400" : "text-slate-500")}>
                  {exploitVectors.availability_degraded ? "TRUE ●" : "FALSE ○"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1 border-b border-white/5">
                <span className="text-slate-400">unauthorized_mutation</span>
                <span className={cn("font-semibold", exploitVectors.unauthorized_mutation ? "text-emerald-400 font-bold" : "text-slate-500")}>
                  {exploitVectors.unauthorized_mutation ? "VERIFIED TRUE ●" : "FALSE ○"}
                </span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span className="text-slate-400">flag_captured</span>
                <span className={cn("font-semibold", exploitVectors.flag_captured ? "text-emerald-400 font-bold" : "text-slate-500")}>
                  {exploitVectors.flag_captured ? "CAPTURED ●" : "FALSE ○"}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-5 pt-3 border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Probes: {breakerActions.length}</span>
            <button onClick={onSwitchToDeepDive} className="text-fuchsia-400 hover:underline flex items-center gap-1">
              <Terminal className="w-3 h-3" /> Logs
            </button>
          </div>
        </section>
      </div>

      {/* BOTTOM SECTION: CLAIM VS VERIFIED */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
        
        {/* BREAKER CLAIM */}
        <div className="rounded-2xl border border-white/10 bg-[#10141F] p-5">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400">
              ⚪ Breaker Claim (Self-Reported)
            </span>
            <span className="text-[11px] font-mono text-slate-500">Untrusted by default</span>
          </div>
          <p className="text-sm font-mono text-slate-300 leading-relaxed">
            {isBreakerActive
              ? "Breaker is actively probing target routes. Claims submitted will require Arena verification."
              : "No exploit claims submitted during this phase."}
          </p>
        </div>

        {/* ARENA TRUSTED VERIFIER */}
        <div className="rounded-2xl border border-cyan-500/30 bg-[#10141F] p-5">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-cyan-300">
              🛡️ Arena Trusted Verifier (Ground Truth)
            </span>
            <span className="text-[11px] font-mono font-bold text-slate-400">
              {battle?.verification_status ? battle.verification_status.toUpperCase() : "IDLE"}
            </span>
          </div>
          <p className="text-sm font-mono text-slate-300 leading-relaxed">
            {battle?.verification_status === "verified_pass"
              ? "● VERIFIED BY ARENA: Post-condition state changes and security invariants audited officially."
              : "The Arena verifier audits the ephemeral database and microVM state independently. Fighter claims carry zero score without verified evidence."}
          </p>
        </div>
      </section>
    </div>
  );
}
