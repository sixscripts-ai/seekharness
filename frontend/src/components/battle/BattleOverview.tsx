import { ArrowUpRight, CircleAlert, ShieldCheck, TerminalSquare } from "lucide-react";
import type { BattleOut, FormatOut, TargetDetailOut } from "@/lib/api";
import { battleShape, verificationEventIndex } from "@/lib/battleOverview";
import { verificationLabel } from "@/lib/targetResult";
import type { BattleStreamItem } from "./types";
import { parseAction, timeLabel, titleCase } from "./utils";

type Props = {
  battle: BattleOut;
  officialBattle: BattleOut | null;
  format: FormatOut | null;
  target: TargetDetailOut | null;
  status: string;
  events: BattleStreamItem[];
  modelName: (id: string) => string;
  onDeepDive: () => void;
};

export default function BattleOverview({ battle, officialBattle, format, target, status, events, modelName, onDeepDive }: Props) {
  const shape = battleShape(battle, format, target);
  const record = officialBattle;
  const recordStatus = record?.status || status;
  const results = record?.results || [];
  const reason = record?.failure_reason || record?.termination_reason || null;
  const infraFailure = recordStatus === "failed" && (record?.verification_status === "infra_failure" || Boolean(reason && /(?:SANDBOX|INFRA|PROVIDER|BOOT|RUNTIME)/i.test(reason)));
  const observedPhases = events.filter(item => item.kind === "phase_start").map(item => item.phase);
  const phaseNames = shape.phases.length ? shape.phases : [...new Set(observedPhases)];
  const verificationEvents = events.map((event, index) => ({ event, index })).filter(({ event }) => event.kind === "verification" && event.payload?.source === "trusted_verifier" && event.payload.authoritative === true);
  const activity = events.filter(item => ["phase_start", "action_log", "error"].includes(item.kind) || (item.kind === "battle_status" && item.payload?.authoritative === true)).slice(-8).reverse();
  const hasExecution = events.some(item => ["phase_start", "action_log", "transcript", "artifact"].includes(item.kind));

  return <div className="space-y-5">
    <section className="rounded-2xl border border-white/10 bg-[#10141d] p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan-300">Battle contract</p><h2 className="mt-2 font-display text-2xl text-white sm:text-3xl">{shape.label}</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">{target?.description || battle.battle_config?.description || "Live execution and recorded results for this battle."}</p></div>
        <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full border border-cyan-400/25 bg-cyan-400/5 px-3 py-1.5 text-cyan-200">{shape.scoring}</span>{shape.runtime && <span className="rounded-full border border-white/10 px-3 py-1.5 text-slate-300">{shape.runtime}</span>}</div>
      </div>
      <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {(battle.model_ids || []).map((id, index) => <div key={`${id}-${index}`} className="rounded-xl border border-white/10 bg-black/20 p-4"><p className="text-[11px] uppercase tracking-widest text-slate-500">{titleCase(shape.roles[index] || `Model ${index + 1}`)}</p><p className="mt-2 break-words text-base font-medium text-white">{modelName(id)}</p><p className="mt-1 break-all font-mono text-[10px] text-slate-500">{id}</p></div>)}
      </div>
      {phaseNames.length > 0 && <div className="mt-7"><h3 className="text-xs uppercase tracking-widest text-slate-500">Phase plan</h3><ol className="mt-3 flex flex-wrap gap-2">{phaseNames.map((phase, index) => <li key={`${phase}-${index}`} className="rounded-md border border-white/10 px-3 py-2 text-xs text-slate-300"><span className="mr-2 text-cyan-300">{index + 1}.</span>{titleCase(phase)}{observedPhases.includes(phase) && <span className="ml-2 text-emerald-300">Observed</span>}</li>)}</ol></div>}
    </section>

    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(310px,0.8fr)]">
      <section aria-labelledby="official-result-heading" className="rounded-2xl border border-white/10 bg-[#10141d] p-5 sm:p-6">
        <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-cyan-300" /><h2 id="official-result-heading" className="font-display text-xl text-white">Official record</h2></div>
        <p className="mt-2 text-xs leading-5 text-slate-500">Battle state and result rows come from the persisted server record. Model claims and judge commentary do not establish target correctness.</p>
        <div className="mt-5 rounded-xl border border-white/10 bg-black/20 p-4"><p className="text-[11px] uppercase tracking-widest text-slate-500">Lifecycle</p><p className={`mt-2 text-lg font-medium ${recordStatus === "failed" ? "text-rose-200" : recordStatus === "completed" ? "text-emerald-200" : "text-white"}`}>{infraFailure ? "Infrastructure failure" : titleCase(recordStatus)}</p>{reason && <p role="status" className="mt-2 flex items-start gap-2 break-words text-sm text-rose-200"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{titleCase(reason.toLowerCase())}</p>}</div>
        {record?.winner && (!battle.target_id || record.verified_solution === true) && <p className="mt-4 text-sm text-emerald-200">{battle.target_id ? "Verified winner" : "Recorded winner"}: <span className="font-medium">{modelName(record.winner)}</span></p>}
        {recordStatus === "failed" && !hasExecution && <p className="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-100">{infraFailure ? "The run failed before any fighter execution was recorded. This is infrastructure failure, not a fighter loss." : "No fighter execution was recorded. The public record does not establish a fighter loss."}</p>}
        {results.length ? <div className="mt-4 space-y-3">{results.map((result, index) => {
          const evidenceIndex = verificationEventIndex(events, result.model_id, result.phase);
          const verified = result.verification_status === "verified_pass";
          return <article key={`${result.model_id}-${result.phase}-${index}`} className="rounded-xl border border-white/10 p-4"><div className="flex flex-wrap justify-between gap-2"><div><p className="text-sm font-medium text-white">{modelName(result.model_id)}</p><p className="mt-1 text-xs text-slate-500">{titleCase(result.role || result.phase || "Fighter")}</p></div><span className={`text-sm ${verified ? "text-emerald-300" : result.verification_status === "infra_failure" ? "text-rose-300" : "text-slate-300"}`}>{verificationLabel(result.verification_status)}</span></div>{result.termination_reason && <p className="mt-2 text-xs text-slate-400">Termination: {titleCase(result.termination_reason)}</p>}{evidenceIndex >= 0 ? <a href={`#evidence-event-${evidenceIndex}`} className="mt-3 inline-flex items-center gap-1 text-xs text-cyan-300 underline-offset-4 hover:underline">View recorded verification event <ArrowUpRight className="h-3 w-3" /></a> : <p className="mt-3 text-xs text-slate-500">No replayable public verification event is available for this result.</p>}</article>;
        })}</div> : <p className="mt-5 text-sm text-slate-400">{recordStatus === "completed" || recordStatus === "failed" ? "No official model result rows were recorded." : "Awaiting authoritative result rows."}</p>}
        {record?.scores && Object.keys(record.scores).length > 0 && <div className="mt-5 border-t border-white/10 pt-4"><h3 className="text-xs uppercase tracking-widest text-slate-500">Recorded scores</h3><div className="mt-2 space-y-2">{Object.entries(record.scores).map(([id, score]) => <div key={id} className="flex justify-between gap-3 text-sm"><span className="text-slate-300">{modelName(id)}</span><span className="font-mono text-white">{score}</span></div>)}</div><p className="mt-3 text-xs text-slate-500">Scores are recorded outcomes; a target pass still requires trusted verification.</p></div>}
      </section>

      <section aria-labelledby="activity-heading" className="rounded-2xl border border-white/10 bg-[#10141d] p-5 sm:p-6"><div className="flex items-center gap-2"><TerminalSquare className="h-4 w-4 text-cyan-300" /><h2 id="activity-heading" className="font-display text-xl text-white">Recorded activity</h2></div><p className="mt-2 text-xs text-slate-500">Replayable public events, newest first.</p>{activity.length ? <ol className="mt-5 space-y-3">{activity.map((item, index) => {
        const action = parseAction(item);
        const label = item.kind === "action_log" ? action?.command || "Tool activity" : item.kind === "phase_start" ? `Phase: ${titleCase(item.phase)}` : item.kind === "error" ? "Runtime error" : `Battle ${String(item.payload?.status || "status update")}`;
        return <li key={`${item.kind}-${item.t}-${index}`} className="border-l border-cyan-300/30 pl-3"><p className="break-words text-sm text-slate-200">{label}</p><p className="mt-1 text-[11px] text-slate-500">{item.model_id !== "arena" ? modelName(item.model_id) + " · " : ""}{timeLabel(item.t)}</p></li>;
      })}</ol> : <p className="mt-5 text-sm text-slate-400">No fighter or phase activity has been recorded.</p>}<button type="button" onClick={onDeepDive} className="mt-6 inline-flex min-h-11 items-center gap-2 text-sm text-cyan-300 hover:text-cyan-100">Open Deep Dive <ArrowUpRight className="h-4 w-4" /></button></section>
    </div>

    <section aria-labelledby="evidence-heading" className="rounded-2xl border border-white/10 bg-[#10141d] p-5 sm:p-6"><h2 id="evidence-heading" className="font-display text-xl text-white">Verification trail</h2><p className="mt-2 text-xs leading-5 text-slate-500">Only public, trusted-verifier event summaries are shown. Hidden tests and evaluator output remain private.</p>{verificationEvents.length ? <ol className="mt-4 space-y-2">{verificationEvents.map(({ event, index }) => <li id={`evidence-event-${index}`} key={`${event.kind}-${event.t}-${index}`} className="scroll-mt-24 rounded-lg border border-white/10 p-4"><div className="flex flex-wrap justify-between gap-2"><span className="text-sm text-white">{modelName(event.model_id)} · {titleCase(event.phase)}</span><span className="text-sm text-cyan-200">{verificationLabel(String(event.payload?.verification_status || "unverified"))}</span></div><p className="mt-2 font-mono text-[11px] text-slate-500">{typeof event.payload?.event_id === "string" ? `Event ${event.payload.event_id}` : `Recorded ${timeLabel(event.t)}`}</p></li>)}</ol> : <p className="mt-5 text-sm text-slate-400">No trusted-verifier summary event is available in the replay.</p>}</section>
  </div>;
}
