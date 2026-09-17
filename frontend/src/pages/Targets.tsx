import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Search, Plus } from "lucide-react";
import { api, isCustomFormat, type BattleDraftOut, type BattleTemplate, type FormatOut, type TargetSummaryOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatScoring, savedChallengeIds } from "@/lib/challengeNavigation";

type Challenge = { key: string; title: string; description: string; kind: "Built-in" | "Template" | "Saved"; meta: string[]; href: string; detail?: string };

export function ChallengeLibrary({ picker = false }: { picker?: boolean }) {
  const { user, jwt } = useAuth();
  const [targets, setTargets] = useState<TargetSummaryOut[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [templates, setTemplates] = useState<BattleTemplate[]>([]);
  const [drafts, setDrafts] = useState<BattleDraftOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("All");
  const [difficulty, setDifficulty] = useState("All");
  const userId = user?.$id;
  const hasToken = Boolean(jwt);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDrafts([]);
    setErrors([]);
    const token = useAuth.getState().jwt;
    const ids = userId && token ? savedChallengeIds(userId) : [];
    void Promise.allSettled([api.targets(), api.formats(token), api.getBattleTemplates()]).then(async ([targetRows, formatRows, templateRows]) => {
      const failures: string[] = [];
      if (cancelled) return;
      if (targetRows.status === "fulfilled") setTargets(targetRows.value); else { setTargets([]); failures.push("Built-in challenges could not be loaded."); }
      if (formatRows.status === "fulfilled") setFormats(formatRows.value.filter(format => !isCustomFormat(format))); else { setFormats([]); failures.push("Preset challenges could not be loaded."); }
      if (templateRows.status === "fulfilled") setTemplates(templateRows.value); else { setTemplates([]); failures.push("Custom templates could not be loaded."); }
      const saved = await Promise.allSettled(ids.map(id => api.getBattleDraft(token!, id)));
      if (cancelled) return;
      setDrafts(saved.flatMap(result => result.status === "fulfilled" ? [result.value] : []));
      if (saved.some(result => result.status === "rejected")) failures.push("Some saved challenges are unavailable. Their saved links have been kept.");
      setErrors(failures);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [userId, hasToken, reload]);

  const challenges = useMemo<Challenge[]>(() => [
    ...targets.map(target => ({
      key: "target:" + target.id, title: target.name, description: target.description, kind: "Built-in" as const,
      meta: [target.format === "builder_breaker" ? "Builder vs. Breaker" : "Solo or head-to-head", target.runtime, target.difficulty],
      href: "/battles/new?target=" + encodeURIComponent(target.id), detail: "/challenges/" + encodeURIComponent(target.id),
    })),
    ...formats.map(format => ({
      key: "format:" + format.id, title: format.name, description: format.description || "A preset challenge with its own roles and execution rules.", kind: "Template" as const,
      meta: [formatScoring(format)], href: "/battles/new?format=" + encodeURIComponent(format.id),
    })),
    ...templates.map(template => ({
      key: "template:" + template.id, title: template.title, description: template.brief, kind: "Template" as const,
      meta: [template.category, template.mode === "verified" ? "Test-scored" : "Judge-scored"],
      href: "/battles/new?custom=1&template=" + encodeURIComponent(template.id),
    })),
    ...drafts.map(draft => ({
      key: "draft:" + draft.id, title: draft.spec.title || "Untitled challenge", description: draft.spec.brief || "Continue editing your custom challenge.", kind: "Saved" as const,
      meta: [draft.mode === "verified" ? "Test-scored" : "Judge-scored", draft.status === "launched" ? "Reusable challenge" : draft.status],
      href: "/battles/new?custom=1&draft=" + encodeURIComponent(draft.id),
    })),
  ], [targets, formats, templates, drafts]);

  const visible = challenges.filter(challenge => (kind === "All" || challenge.kind === kind) &&
    (difficulty === "All" || challenge.meta.includes(difficulty)) &&
    [challenge.title, challenge.description, ...challenge.meta].join(" ").toLowerCase().includes(query.trim().toLowerCase()));

  return <>
    {picker && <div className="mb-7 flex items-center gap-5 border-b border-white/10 text-sm"><span className="border-b-2 border-cyan-300 pb-3 text-white">From library</span><Link className="pb-3 text-slate-400 hover:text-white" to="/battles/new?custom=1">Create your own</Link></div>}
    <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
      <label className="relative flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-500" /><input className="input pl-10" aria-label="Search challenges" placeholder="Search a task, skill, or runtime" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <div className="grid grid-cols-2 gap-3 lg:w-[330px]">
        <select aria-label="Challenge source" className="select" value={kind} onChange={event => setKind(event.target.value)}>{["All", "Built-in", "Template", "Saved"].map(value => <option key={value}>{value}</option>)}</select>
        <select aria-label="Difficulty" className="select" value={difficulty} onChange={event => setDifficulty(event.target.value)}>{["All", "novice", "general", "advanced", "expert"].map(value => <option key={value} value={value}>{value === "All" ? "Any difficulty" : value}</option>)}</select>
      </div>
    </div>
    {errors.length > 0 && <div role="alert" className="mb-6 rounded-lg border border-amber-400/20 bg-amber-950/20 p-4 text-sm text-amber-200">{errors.map(error => <p key={error}>{error}</p>)}<button type="button" className="mt-2 underline" onClick={() => setReload(value => value + 1)}>Try again</button></div>}
    {loading ? <p role="status" className="py-12 text-sm text-slate-400">Loading the challenge library…</p> : <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>{visible.length} {visible.length === 1 ? "challenge" : "challenges"}</span>{kind === "Saved" && <span>Saved links on this browser; challenge content is stored on your account.</span>}</div>
      {visible.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visible.map(challenge => <article key={challenge.key} className="flex min-w-0 flex-col rounded-xl border border-white/10 bg-[#11141E] p-5">
          <div className="mb-4 flex items-center justify-between gap-3 text-xs"><span className={challenge.kind === "Saved" ? "text-fuchsia-300" : "text-slate-400"}>{challenge.kind}</span>{challenge.detail && <Link to={challenge.detail} className="text-slate-400 hover:text-white">Details <span aria-hidden="true">↗</span><span className="sr-only">: {challenge.title}</span></Link>}</div>
          <h2 className="font-display text-lg font-medium leading-snug text-white">{challenge.title}</h2>
          <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-400">{challenge.description}</p>
          <div className="mb-6 mt-4 flex flex-wrap gap-2">{challenge.meta.filter(Boolean).map((meta, index) => <span key={index} className="rounded bg-white/5 px-2 py-1 text-[11px] text-slate-400">{meta.replace(/_/g, " ")}</span>)}</div>
          <Link to={challenge.href} className="mt-auto flex min-h-10 items-center justify-between border-t border-white/10 pt-3 text-sm font-medium text-cyan-300 hover:text-cyan-100" aria-label={(challenge.kind === "Saved" ? "Open " : challenge.key.startsWith("template:") ? "Customize " : "Fight: ") + challenge.title}>{challenge.kind === "Saved" ? "Open challenge" : challenge.key.startsWith("template:") ? "Customize" : "Fight →"}{(challenge.kind === "Saved" || challenge.key.startsWith("template:")) && <ArrowUpRight className="h-4 w-4" />}</Link>
        </article>)}
      </div> : <div className="rounded-xl border border-dashed border-white/15 px-6 py-14 text-center"><h2 className="text-lg text-white">{kind === "Saved" ? "No saved challenges yet" : "No matching challenges"}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">{kind === "Saved" ? user ? "Create your own challenge and choose Save to library to find it here." : "Log in to access your saved challenges." : "Try another search or clear the filters."}</p><Link to={kind === "Saved" && !user ? "/login?next=%2Fchallenges" : "/battles/new?custom=1"} className="btn btn-ghost mt-5">{kind === "Saved" && !user ? "Log in" : "Create your own"}</Link></div>}
    </>}
  </>;
}

export default function Targets() {
  return <div className="battle-workspace min-h-[calc(100vh-64px)] bg-[#08090D]/95"><div className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8 sm:py-12">
    <header className="mb-9 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><h1 className="font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">Challenges</h1><p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">Pick what your models should solve. The challenge defines the setup.</p></div><Link to="/battles/new?custom=1" className="btn btn-ghost gap-2 self-start"><Plus className="h-4 w-4" />Create your own</Link></header>
    <ChallengeLibrary />
  </div></div>;
}
