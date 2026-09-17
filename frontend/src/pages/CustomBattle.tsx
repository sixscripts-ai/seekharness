import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, splitProviders, type BattleDraftOut, type BattleSpec, type BattleTemplate, type ProviderOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { forgetChallenge, modelSlots, validModelSlots } from "@/lib/challengeNavigation";
import BattleSetupHeader from "@/components/BattleSetupHeader";
import BattleModelFields from "@/components/BattleModelFields";
import ProviderSelect from "@/components/ProviderSelect";

type Mode = "quick" | "verified";

export default function CustomBattle() {
  const { user, jwt, loading: authLoading, refreshJwt } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const requestedDraft = params.get("draft");
  const requestedTemplate = params.get("template");
  const userId = user?.$id;
  const hasToken = Boolean(jwt);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [mode, setMode] = useState<Mode>(params.get("mode") === "verified" ? "verified" : "quick");
  const [draft, setDraft] = useState<BattleDraftOut | null>(null);
  const [template, setTemplate] = useState<BattleTemplate | null>(null);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [testCode, setTestCode] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [judgeId, setJudgeId] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [save, setSave] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [reload, setReload] = useState(0);

  function acceptDraft(value: BattleDraftOut) {
    setDraft(value);
    setMode(value.mode);
    setTitle(value.spec.title || "");
    setBrief(value.spec.brief || "");
    setTestCode(value.spec.test_code || "");
  }

  useEffect(() => {
    if (!userId || !hasToken) return;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    const token = useAuth.getState().jwt!;
    void Promise.all([
      api.providers(token),
      requestedDraft ? api.getBattleDraft(token, requestedDraft) : Promise.resolve(null),
      requestedTemplate ? api.getBattleTemplates() : Promise.resolve([]),
    ]).then(([rows, saved, templates]) => {
      if (cancelled) return;
      setProviders(rows);
      setSelected(previous => modelSlots(previous, rows, 2));
      if (saved) acceptDraft(saved);
      else if (requestedTemplate) {
        const found = templates.find(value => value.id === requestedTemplate);
        if (!found) throw new Error("This template is no longer available. Choose another from the library.");
        setTemplate(found);
        setMode(found.mode);
        setTitle(found.title);
        setBrief(found.brief);
      }
    }).catch(err => { if (!cancelled) setLoadError(err instanceof Error ? err.message : "Could not load custom setup."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [userId, hasToken, requestedDraft, requestedTemplate, reload]);

  const dirty = Boolean(draft && (title !== (draft.spec.title || "") || brief !== (draft.spec.brief || "") || (mode === "verified" && testCode !== (draft.spec.test_code || ""))));
  const draftReady = draft?.status === "ready" && !dirty && !loading && !loadError;
  const { host, yours } = splitProviders(providers);
  const modelsReady = validModelSlots(selected, providers, selected.length) && selected.length >= 2 &&
    (!judgeId || providers.some(provider => provider.id === judgeId)) &&
    Number.isInteger(timeoutSec) && timeoutSec >= 30 && timeoutSec <= 3600;
  const launched = draft?.status === "launched";

  async function tokenOrThrow() {
    const token = await refreshJwt();
    if (!token) throw new Error("Your session ended. Log in again to continue.");
    return token;
  }
  async function perform(action: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(action); setError(""); setNotice("");
    try { await operation(); }
    catch (err) { setError(err instanceof Error ? err.message : "The request could not be completed."); }
    finally { setBusy(""); }
  }
  async function currentDraft(token: string) {
    if (draft && !launched) return draft;
    const created = await api.createBattleDraft(token, { mode });
    // Preserve a newly created draft even if the following operation fails.
    setDraft(created);
    return created;
  }
  function generate(event: React.FormEvent) {
    event.preventDefault();
    if (!message.trim() || launched) return;
    void perform("generate", async () => {
      const token = await tokenOrThrow();
      const current = await currentDraft(token);
      const updated = await api.postDraftMessage(token, current.id, { content: message.trim() });
      acceptDraft(updated);
      setMessage("");
    });
  }
  function saveSpec() {
    void perform("save", async () => {
      const token = await tokenOrThrow();
      const current = await currentDraft(token);
      const spec: Partial<BattleSpec> = {
        ...(launched ? draft?.spec : {}),
        ...(template && (!draft || draft.revision === 0) ? {
          deliverables: template.deliverables, constraints: template.constraints,
          required_artifacts: template.required_artifacts, judge_rubric: template.judge_rubric, languages: template.languages,
        } : {}),
        title, brief, test_code: mode === "verified" ? testCode : null,
      };
      const updated = await api.patchDraftSpec(token, current.id, spec);
      acceptDraft(updated);
      if (updated.status !== "ready") setNotice("Draft saved. Complete its requirements before choosing models.");
      else setNotice(launched ? "A new draft is ready. The original battle is unchanged." : "Challenge saved and ready for model selection.");
    });
  }
  function saveToLibrary() {
    if (!draft || dirty) return;
    void perform("library", async () => {
      const token = await tokenOrThrow();
      acceptDraft(await api.saveBattleDraft(token, draft.id));
      if (userId) forgetChallenge(userId, draft.id);
      setNotice("Saved to your account library. You can open it on another device.");
    });
  }
  function removeFromLibrary() {
    if (!draft) return;
    void perform("library", async () => {
      const token = await tokenOrThrow();
      acceptDraft(await api.unsaveBattleDraft(token, draft.id));
      if (userId) forgetChallenge(userId, draft.id);
      setNotice("Removed from your challenge library. This draft still exists at its direct link.");
    });
  }
  function addModel() {
    if (selected.length < 6) setSelected(previous => modelSlots(previous, providers, previous.length + 1));
  }
  function launch() {
    if (!draft || !draftReady || !modelsReady || step !== 3) return;
    void perform("launch", async () => {
      const token = await tokenOrThrow();
      const result = await api.launchDraft(token, draft.id, {
        revision: draft.revision, model_ids: selected, timeout_seconds: timeoutSec, save,
        judge_provider_id: judgeId || null,
      });
      navigate("/battles/" + result.id);
    });
  }

  return <div className="battle-workspace min-h-[calc(100vh-64px)] bg-[#08090D]/95"><div className="mx-auto max-w-[1100px] px-4 py-8 sm:px-8 sm:py-12">
    <BattleSetupHeader step={step} onStep={value => { if (!busy) setStep(value); }} />
    {authLoading ? <p role="status">Checking your session…</p> : !user ? <div className="py-12 text-center"><h2 className="text-xl text-white">Log in to create a challenge</h2><p className="mt-2 text-sm text-slate-400">Write a brief, choose how it is scored, then select your models.</p><Link to={"/login?next=" + encodeURIComponent("/battles/new?" + params)} className="btn btn-primary mt-6">Log in</Link></div> : loading ? <p role="status" className="py-10 text-slate-400">Loading your setup…</p> : loadError ? <div role="alert"><p className="break-words text-rose-300">{loadError}</p><button className="btn btn-ghost mt-5" onClick={() => setReload(value => value + 1)}>Try again</button></div> : <>
      {step === 1 && <>
        <div className="mb-7 flex items-center gap-5 border-b border-white/10 text-sm"><Link to="/battles/new" className="pb-3 text-slate-400 hover:text-white">From library</Link><span className="border-b-2 border-cyan-300 pb-3 text-white">Create your own</span></div>
        <fieldset disabled={Boolean(draft) || Boolean(template) || Boolean(busy)} className="mb-7"><legend className="mb-3 text-lg font-medium text-white">How should this challenge be scored?</legend><div className="grid gap-3 sm:grid-cols-2">{(["quick", "verified"] as const).map(value => <label key={value} className={"flex gap-3 rounded-lg border p-4 " + (mode === value ? "border-cyan-300/60 bg-cyan-300/5" : "border-white/10")}><input type="radio" name="scoring" checked={mode === value} onChange={() => setMode(value)} className="mt-1 accent-cyan-300" /><span><span className="block text-sm font-medium text-white">{value === "quick" ? "Judge-scored" : "Test-scored"}</span><span className="mt-1 block text-xs leading-5 text-slate-400">{value === "quick" ? "Compare work against a rubric. No deterministic correctness claim." : "Use executable acceptance tests, with judge feedback alongside."}</span></span></label>)}</div>{draft && <p className="mt-2 text-xs text-slate-500">Scoring is fixed for this draft. Start a new challenge to change it.</p>}</fieldset>
        {launched && <p className="mb-5 rounded-lg border border-cyan-300/20 p-4 text-sm text-slate-300">This challenge has already run. Choose “Create reusable copy” to start a new draft without changing the original battle.</p>}
        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <section className="min-w-0 rounded-xl border border-white/10 bg-[#11141E] p-5"><h2 className="mb-2 text-lg text-white">Describe the task</h2><p className="mb-5 text-sm leading-6 text-slate-400">Tell the architect what to build, what to deliver, and what counts as success.</p>
            {draft?.transcript?.length ? <div className="mb-5 max-h-72 space-y-4 overflow-y-auto" aria-label="Challenge conversation">{draft.transcript.map((entry, index) => <div key={index}><p className="mb-1 text-xs text-cyan-300">{entry.role === "user" ? "You" : "Architect"}</p><p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-300">{entry.content}</p></div>)}</div> : null}
            <form onSubmit={generate}><label className="text-sm text-slate-400">Your instructions<textarea className="input mt-2 min-h-40 resize-y" value={message} onChange={event => setMessage(event.target.value)} placeholder="Describe the task and how a good solution should behave…" disabled={Boolean(busy) || launched} /></label><button className="btn btn-ghost mt-3 w-full" disabled={Boolean(busy) || !message.trim() || launched}>{busy === "generate" ? "Preparing challenge…" : draft ? "Update from instructions" : "Generate challenge"}</button><p className="mt-3 text-xs leading-5 text-slate-500">Test generation may use a model. Review the resulting brief and tests before running.</p></form>
          </section>
          <section className="min-w-0 space-y-4 rounded-xl border border-white/10 bg-[#11141E] p-5"><h2 className="text-lg text-white">Challenge brief</h2>
            <label className="block text-sm text-slate-400">Title<input className="input mt-2" value={title} onChange={event => setTitle(event.target.value)} disabled={Boolean(busy)} placeholder="Give the challenge a clear name" /></label>
            <label className="block text-sm text-slate-400">Task and requirements<textarea className="input mt-2 min-h-48 resize-y" value={brief} onChange={event => setBrief(event.target.value)} disabled={Boolean(busy)} placeholder="What should the models produce?" /></label>
            {mode === "verified" && <label className="block text-sm text-slate-400">Acceptance tests<textarea className="input mt-2 min-h-48 resize-y font-mono text-xs" spellCheck={false} value={testCode} onChange={event => setTestCode(event.target.value)} disabled={Boolean(busy)} /><span className="mt-2 block text-xs leading-5 text-slate-500">The backend validates these tests before marking the draft ready. A saved draft is not a verified battle result.</span></label>}
            {draft && <details className="text-sm text-slate-400"><summary className="cursor-pointer">Full specification · revision {draft.revision}</summary><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(draft.spec, null, 2)}</pre></details>}
            <div className="flex flex-wrap gap-3"><button type="button" className="btn btn-ghost" onClick={saveSpec} disabled={Boolean(busy) || !title.trim() || !brief.trim()}>{busy === "save" ? "Saving…" : launched ? "Create reusable copy" : "Save challenge"}</button>{draft && <button type="button" className="btn btn-ghost" onClick={draft.saved ? removeFromLibrary : saveToLibrary} disabled={Boolean(busy) || dirty}>{busy === "library" ? "Updating library…" : draft.saved ? "Remove from library" : "Save to library"}</button>}</div>
            {dirty && <p className="text-xs text-amber-200">Save your changes before continuing.</p>}
            {draft?.architect_error && <p role="alert" className="break-words text-xs text-amber-200">{draft.architect_error}</p>}
          </section>
        </div>
      </>}
      {step === 2 && <>
        <div className="mb-7 border-b border-white/10 pb-5"><p className="text-xs text-slate-500">Your challenge</p><h2 className="mt-2 text-2xl text-white">{draft?.spec.title}</h2><p className="mt-2 text-sm text-slate-400">{mode === "verified" ? "Test-scored" : "Judge-scored"} · Custom challenges compare 2–6 models.</p></div>
        <BattleModelFields roles={selected.map((_, index) => "Model " + String.fromCharCode(65 + index))} selected={selected} onChange={setSelected} providers={providers} />
        <div className="mt-4 flex gap-3"><button type="button" className="btn btn-ghost" onClick={addModel} disabled={selected.length >= 6}>Add model</button>{selected.length > 2 && <button type="button" className="btn btn-ghost" onClick={() => setSelected(value => value.slice(0, -1))}>Remove last model</button>}</div>
        <div className="mt-7 grid gap-5 sm:grid-cols-2"><label className="text-sm text-slate-400">Time limit (seconds)<input type="number" min={30} max={3600} step={1} className="input mt-2" value={timeoutSec} onChange={event => setTimeoutSec(Number(event.target.value))} /></label><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={save} onChange={event => setSave(event.target.checked)} />Save battle in history</label></div>
        <div className="mt-6"><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={Boolean(judgeId)} onChange={event => setJudgeId(event.target.checked ? providers[0]?.id || "" : "")} />Choose a judge model (otherwise use platform default)</label>{judgeId && <label className="mt-3 block text-sm text-slate-400">Judge model<ProviderSelect value={judgeId} onChange={setJudgeId} host={host} yours={yours} /></label>}</div>
      </>}
      {step === 3 && <section className="rounded-xl border border-white/10 bg-[#11141E] p-6"><h2 className="text-2xl text-white">{draft?.spec.title}</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-400">{draft?.spec.brief}</p><dl className="mt-7 space-y-4 text-sm"><div className="flex justify-between gap-3"><dt className="text-slate-500">Scoring</dt><dd>{mode === "verified" ? "Acceptance tests + judge feedback" : "Judge rubric only"}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Draft revision</dt><dd>{draft?.revision}</dd></div>{selected.map((id, index) => <div key={id + index} className="flex flex-wrap justify-between gap-3"><dt className="text-slate-500">Model {String.fromCharCode(65 + index)}</dt><dd>{providers.find(provider => provider.id === id)?.model_name || id}</dd></div>)}<div className="flex justify-between gap-3"><dt className="text-slate-500">Time limit</dt><dd>{timeoutSec} seconds</dd></div></dl><p className="mt-7 text-xs leading-5 text-slate-400">Starting a battle runs these models and may incur provider usage costs. The backend freezes this draft revision and determines the result.</p></section>}
      {notice && <p role="status" className="mt-5 text-sm text-cyan-200">{notice}</p>}
      {error && <p role="alert" className="mt-5 break-words rounded-lg border border-rose-300/20 bg-rose-950/20 p-4 text-sm text-rose-200">{error}</p>}
      <div className="mt-8 flex items-center justify-between gap-4 border-t border-white/10 pt-6">{step === 1 ? <Link to="/battles/new" className="text-sm text-slate-400">Back to library</Link> : <button type="button" disabled={Boolean(busy)} onClick={() => setStep(step === 3 ? 2 : 1)} className="btn btn-ghost">Back</button>}
        {step === 1 ? <button type="button" className="btn btn-primary" disabled={!draftReady || Boolean(busy)} onClick={() => setStep(2)}>Choose models</button> : step === 2 ? <button type="button" className="btn btn-primary" disabled={!modelsReady || !draftReady} onClick={() => setStep(3)}>Review battle</button> : <button type="button" className="btn btn-primary" disabled={!draftReady || !modelsReady || Boolean(busy)} onClick={launch}>{busy === "launch" ? "Starting…" : "Start battle"}</button>}
      </div>
    </>}
  </div></div>;
}
