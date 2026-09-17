import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, isCustomFormat, isToolUsingFormat, splitProviders, type FormatOut, type ProviderOut, type TargetDetailOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { challengeRoles, formatScoring, modelSlots, validModelSlots } from "@/lib/challengeNavigation";
import { clearSetupDraft, readSetupDraft, setupDraftKey, writeSetupDraft } from "@/lib/battleSetupDraft";
import BattleSetupHeader from "@/components/BattleSetupHeader";
import BattleModelFields from "@/components/BattleModelFields";
import BattleSetupActions from "@/components/BattleSetupActions";
import ProviderSelect from "@/components/ProviderSelect";
import { ChallengeLibrary } from "./Targets";
import CustomBattle from "./CustomBattle";

export default function NewBattle() {
  const [params] = useSearchParams();
  if (params.get("custom") === "1" || params.get("source") === "custom") return <CustomBattle key={params.get("draft") || params.get("template") || "custom"} />;
  if (params.get("target") || params.get("format")) return <ConfiguredBattle key={params.toString()} />;
  return <div className="battle-workspace min-h-[calc(100vh-64px)] bg-[#08090D]/95"><div className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8 sm:py-12">
    <BattleSetupHeader step={1} /><h2 className="mb-2 text-xl text-white">What should your models solve?</h2><p className="mb-7 text-sm text-slate-400">Choose a challenge. Its rules determine the models and setup you need.</p><ChallengeLibrary picker />
  </div></div>;
}

function ConfiguredBattle() {
  const { user, loading: authLoading, jwt, refreshJwt } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const requestedTarget = params.get("target") || "";
  const requestedFormat = params.get("format") || "";
  const userId = user?.$id;
  const draftKey = userId ? setupDraftKey(userId, requestedTarget ? `target:${requestedTarget}` : `format:${requestedFormat}`) : "";
  const hasToken = Boolean(jwt);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [target, setTarget] = useState<TargetDetailOut | null>(null);
  const [selected, setSelected] = useState<string[]>([params.get("modelA") || "", params.get("modelB") || ""]);
  const [runMode, setRunMode] = useState<"solo" | "race">("solo");
  const [step, setStep] = useState<2 | 3>(2);
  const [judgeId, setJudgeId] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [save, setSave] = useState(false);
  const [visibility, setVisibility] = useState<"isolated" | "open">("isolated");
  const [difficulty, setDifficulty] = useState("general");
  const [contextMode, setContextMode] = useState<"strict" | "adaptive">("strict");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!userId || !hasToken) return;
    setLoading(true);
    setLoadError("");
    const token = useAuth.getState().jwt;
    void Promise.all([api.formats(token), api.providers(token), requestedTarget ? api.target(requestedTarget, token) : Promise.resolve(null)]).then(([formatRows, providerRows, targetRow]) => {
      if (cancelled) return;
      const available = formatRows.filter(format => !isCustomFormat(format));
      if (!targetRow && !available.some(format => format.id === requestedFormat)) throw new Error("This challenge is no longer available. Choose another from the library.");
      setFormats(available);
      setProviders(providerRows);
      setTarget(targetRow);
      const savedDraft = draftKey ? readSetupDraft(draftKey) : null;
      if (savedDraft) {
        const restoredMode = targetRow && targetRow.format !== "builder_breaker" ? savedDraft.runMode : "solo";
        const restoredRoles = challengeRoles(targetRow, available.find(row => row.id === requestedFormat), restoredMode);
        setRunMode(restoredMode);
        setSelected(modelSlots(savedDraft.selected, providerRows, restoredRoles.length));
        setJudgeId(providerRows.some(row => row.id === savedDraft.judgeId) ? savedDraft.judgeId : "");
        setTimeoutSec(savedDraft.timeoutSec);
        setSave(savedDraft.save);
        setVisibility(savedDraft.visibility);
        setDifficulty(targetRow?.difficulty || savedDraft.difficulty);
        setContextMode(savedDraft.contextMode);
      } else if (targetRow) setDifficulty(targetRow.difficulty);
    }).catch(err => { if (!cancelled) setLoadError(err instanceof Error ? err.message : "Could not load this challenge."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [userId, hasToken, requestedTarget, requestedFormat, draftKey, reload]);

  useEffect(() => {
    if (!draftKey || loading || loadError) return;
    writeSetupDraft(draftKey, { selected, runMode, judgeId, timeoutSec, save, visibility, difficulty, contextMode });
  }, [draftKey, loading, loadError, selected, runMode, judgeId, timeoutSec, save, visibility, difficulty, contextMode]);

  const format = formats.find(row => row.id === requestedFormat);
  // The existing API requires a playable format record before replacing its
  // config with the target contract. Never use this carrier as the target label.
  const carrier = formats.find(row => isToolUsingFormat(row));
  const roles = challengeRoles(target, format, runMode);
  const count = roles.length;
  useEffect(() => {
    if (!loading) setSelected(previous => modelSlots(previous, providers, count));
  }, [providers, count, loading]);
  const { host, yours } = splitProviders(providers);
  const challenge = target?.name || format?.name || "Selected challenge";
  const scoring = target ? "Trusted target verification" : format ? formatScoring(format) : "Unavailable";
  const modelReady = validModelSlots(selected, providers, count);
  const judgeReady = !judgeId || providers.some(provider => provider.id === judgeId);
  const optionsReady = Number.isInteger(timeoutSec) && timeoutSec >= 30 && timeoutSec <= 3600;
  const ready = !loading && !loadError && Boolean(target ? carrier : format) && modelReady && judgeReady && optionsReady && !busy;

  async function launch() {
    if (!ready || step !== 3) return;
    setBusy(true);
    setError("");
    try {
      const token = await refreshJwt();
      if (!token) throw new Error("Your session ended. Log in again to start the battle.");
      const battle = await api.createBattle(token, {
        format_id: target ? carrier!.id : format!.id,
        model_ids: selected, arena_size: selected.length, timeout_seconds: timeoutSec,
        round_visibility: target ? "isolated" : visibility, save,
        difficulty: difficulty as "novice" | "general" | "advanced" | "expert",
        target_id: target?.id, target_version: target?.version, context_mode: contextMode,
        judge_provider_id: judgeId || null,
      });
      if (draftKey) clearSetupDraft(draftKey);
      navigate("/battles/" + battle.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not start battle."); }
    finally { setBusy(false); }
  }

  return <div className="battle-workspace min-h-[calc(100vh-64px)] bg-[#08090D]/95"><div className="mx-auto max-w-[1000px] px-4 py-8 sm:px-8 sm:py-12">
    <BattleSetupHeader step={step} onStep={value => { if (busy) return; if (value === 1) navigate("/battles/new"); else setStep(2); }} />
    {authLoading ? <p role="status">Checking your session…</p> : !user ? <div className="py-12 text-center"><h2 className="text-xl text-white">Log in to choose your models</h2><p className="mt-2 text-sm text-slate-400">Your challenge selection will be kept.</p><Link className="btn btn-primary mt-6" to={"/login?next=" + encodeURIComponent("/battles/new?" + params)}>Log in</Link></div> : loading ? <p role="status" className="py-10 text-slate-400">Loading challenge and models…</p> : loadError ? <div role="alert" className="py-8"><p className="break-words text-rose-300">{loadError}</p><button className="btn btn-ghost mt-5" onClick={() => setReload(value => value + 1)}>Try again</button><Link className="ml-5 text-sm text-cyan-300" to="/battles/new">Choose another challenge</Link></div> : <form onSubmit={event => event.preventDefault()}>
      <section className="mb-8 flex flex-col justify-between gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-start">
        <div><p className="mb-2 text-xs text-slate-500">Selected challenge</p><h2 className="font-display text-2xl text-white">{challenge}</h2><p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">{target?.description || format?.description}</p><p className="mt-3 text-xs text-slate-500">{target ? target.runtime + " / " + target.difficulty + " / v" + target.version : scoring}</p></div><Link to="/battles/new" className="shrink-0 text-sm text-cyan-300">Change challenge</Link>
      </section>
      {step === 2 ? <>
        {target && target.format !== "builder_breaker" && <fieldset className="mb-8"><legend className="mb-3 text-sm text-white">How do you want to run it?</legend><div className="grid gap-3 sm:grid-cols-2">{(["solo", "race"] as const).map(mode => <label key={mode} className={"flex cursor-pointer gap-3 rounded-lg border p-4 " + (runMode === mode ? "border-cyan-300/60 bg-cyan-300/5" : "border-white/10")}><input type="radio" name="run-mode" value={mode} checked={runMode === mode} onChange={() => setRunMode(mode)} className="mt-1 accent-cyan-300" /><span><span className="block text-sm font-medium text-white">{mode === "solo" ? "Solo Run" : "Head-to-Head Race"}</span><span className="mt-1 block text-xs text-slate-400">{mode === "solo" ? "Test one model against the challenge." : "Compare Model A and Model B side-by-side."}</span></span></label>)}</div></fieldset>}
        <BattleModelFields roles={roles} selected={selected} onChange={setSelected} providers={providers} />
        <details className="mt-7 rounded-lg border border-white/10"><summary className="cursor-pointer p-4 text-sm text-slate-300">Run settings <span className="ml-2 text-slate-500">Time limit, judging, and visibility</span></summary><div className="grid gap-5 border-t border-white/10 p-5 sm:grid-cols-2">
          <label className="text-sm text-slate-400">Time limit (seconds)<input className="input mt-2" type="number" min={30} max={3600} step={1} value={timeoutSec} onChange={event => setTimeoutSec(Number(event.target.value))} /></label>
          <label className="text-sm text-slate-400">Context handling<select className="select mt-2" value={contextMode} onChange={event => setContextMode(event.target.value as "strict" | "adaptive")}><option value="strict">Strict</option><option value="adaptive">Adaptive</option></select></label>
          {!target && <><label className="text-sm text-slate-400">Difficulty<select className="select mt-2" value={difficulty} onChange={event => setDifficulty(event.target.value)}>{["novice", "general", "advanced", "expert"].map(value => <option key={value}>{value}</option>)}</select></label><label className="text-sm text-slate-400">Round visibility<select className="select mt-2" value={visibility} onChange={event => setVisibility(event.target.value as "isolated" | "open")}><option value="isolated">Isolated</option><option value="open">Open</option></select></label></>}
          <div className="sm:col-span-2"><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={Boolean(judgeId)} onChange={event => setJudgeId(event.target.checked ? providers[0]?.id || "" : "")} />Choose a judge model (optional)</label>{judgeId && <label className="mt-3 block text-sm text-slate-400">Judge model<ProviderSelect value={judgeId} onChange={setJudgeId} host={host} yours={yours} /></label>}<p className="mt-2 text-xs text-slate-500">Otherwise use the platform default. For target challenges, judge commentary does not replace trusted verification.</p></div>
          <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={save} onChange={event => setSave(event.target.checked)} />Save battle in history</label>
        </div></details>
        {target && !carrier && <p role="alert" className="mt-4 text-sm text-amber-200">No compatible execution preset is available. Refresh the challenge library or contact the operator.</p>}
      </> : <section className="rounded-xl border border-white/10 bg-[#11141E] p-6"><h2 className="mb-6 text-xl text-white">Ready to start?</h2><dl className="space-y-4 text-sm">{roles.map((role, index) => <div key={index} className="flex flex-wrap justify-between gap-2 border-b border-white/5 pb-3"><dt className="capitalize text-slate-400">{role}</dt><dd className="break-words text-white">{providers.find(provider => provider.id === selected[index])?.model_name || selected[index]}</dd></div>)}<div className="flex flex-wrap justify-between gap-2"><dt className="text-slate-400">Scoring</dt><dd>{scoring}</dd></div><div className="flex justify-between"><dt className="text-slate-400">Time limit</dt><dd>{timeoutSec} seconds</dd></div><div className="flex justify-between"><dt className="text-slate-400">Visibility</dt><dd>{target ? "isolated" : visibility}</dd></div><div className="flex justify-between"><dt className="text-slate-400">Judge</dt><dd>{judgeId ? providers.find(provider => provider.id === judgeId)?.model_name || judgeId : "Platform default"}</dd></div></dl><p className="mt-6 text-xs leading-5 text-slate-400">Starting a battle runs the selected models and may incur provider usage costs. Results appear only after the backend reports them.</p></section>}
      {error && <p role="alert" className="mt-5 break-words rounded-lg border border-rose-300/20 bg-rose-950/20 p-4 text-sm text-rose-200">{error}</p>}
      <BattleSetupActions review={step === 3} disabled={!ready} busy={busy}
        onBack={() => step === 3 ? setStep(2) : navigate("/battles/new")}
        onReview={() => setStep(3)} onStart={launch} />
    </form>}
  </div></div>;
}
