import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Search, Plus } from "lucide-react";
import { api, type BattleDraftOut, type BattleTemplate, type FormatOut, type TargetSummaryOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { forgetChallenge, savedChallengeIds } from "@/lib/challengeNavigation";
import { buildChallengeCatalog, challengeCatalogPath, type ChallengeSection } from "@/lib/challengeCatalog";

type CatalogPage = Exclude<ChallengeSection, "all">;

export function ChallengeSectionTabs({ section }: { section: CatalogPage }) {
  return <nav aria-label="Challenge collections" className="mb-8 flex gap-7 border-b border-white/[0.08]">
    {(["official", "user"] as const).map(value => <Link
      key={value}
      to={challengeCatalogPath(value)}
      aria-current={section === value ? "page" : undefined}
      className={section === value
        ? "border-b-2 border-cyan-300 px-1 pb-3 text-sm font-medium text-white"
        : "border-b-2 border-transparent px-1 pb-3 text-sm font-medium text-slate-500 hover:text-slate-200"}
    >{value === "official" ? "Official" : "User"}</Link>)}
  </nav>;
}

export function ChallengeLibrary({ picker = false, section = "all" }: { picker?: boolean; section?: ChallengeSection }) {
  const { user, jwt } = useAuth();
  const [params] = useSearchParams();
  const [targets, setTargets] = useState<TargetSummaryOut[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [templates, setTemplates] = useState<BattleTemplate[]>([]);
  const [drafts, setDrafts] = useState<BattleDraftOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [reload, setReload] = useState(0);
  const queryParam = params.get("q") || "";
  const [query, setQuery] = useState(queryParam);
  const [kind, setKind] = useState("All");
  const [difficulty, setDifficulty] = useState("All");
  const userId = user?.$id;
  const hasToken = Boolean(jwt);

  useEffect(() => setQuery(queryParam), [queryParam]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDrafts([]);
    setErrors([]);
    const token = useAuth.getState().jwt;
    const ids = userId && token ? savedChallengeIds(userId) : [];
    void Promise.allSettled([
      section === "user" ? Promise.resolve([] as TargetSummaryOut[]) : api.targets(),
      section === "user" ? Promise.resolve([] as FormatOut[]) : api.formats(token),
      section === "user" ? Promise.resolve([] as BattleTemplate[]) : api.getBattleTemplates(),
    ]).then(async ([targetRows, formatRows, templateRows]) => {
      const failures: string[] = [];
      if (cancelled) return;
      if (section !== "user") {
        if (targetRows.status === "fulfilled") setTargets(targetRows.value); else { setTargets([]); failures.push("Official targets could not be loaded."); }
        if (formatRows.status === "fulfilled") setFormats(formatRows.value); else { setFormats([]); failures.push("Official formats could not be loaded."); }
        if (templateRows.status === "fulfilled") setTemplates(templateRows.value); else { setTemplates([]); failures.push("Official templates could not be loaded."); }
      } else {
        setTargets([]); setFormats([]); setTemplates([]);
      }
      if (section !== "official" && token && userId) {
        try {
          const accountDrafts = await api.listSavedBattleDrafts(token);
          const accountIds = new Set(accountDrafts.map(draft => draft.id));
          const legacy = await Promise.allSettled(ids.filter(id => !accountIds.has(id)).map(id => api.saveBattleDraft(token, id)));
          const migrated = legacy.flatMap(result => result.status === "fulfilled" ? [result.value] : []);
          for (const id of ids) if (accountIds.has(id) || migrated.some(draft => draft.id === id)) forgetChallenge(userId, id);
          if (legacy.some(result => result.status === "rejected")) failures.push("Some browser-only saved links could not be moved to your account.");
          if (!cancelled) setDrafts([...accountDrafts, ...migrated]);
        } catch {
          failures.push("Your saved challenges could not be loaded from your account.");
        }
      }
      if (!cancelled) {
        setErrors(failures);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [userId, hasToken, reload, section]);

  const challenges = useMemo(
    () => buildChallengeCatalog(section, { targets, formats, templates, drafts }),
    [section, targets, formats, templates, drafts],
  );

  const visible = challenges.filter(challenge => (kind === "All" || challenge.kind === kind) &&
    (difficulty === "All" || challenge.meta.includes(difficulty)) &&
    [challenge.title, challenge.description, ...challenge.meta].join(" ").toLowerCase().includes(query.trim().toLowerCase()));

  return <>
    {picker && <div className="mb-7 flex items-center gap-5 border-b border-white/10 text-sm"><span className="border-b-2 border-cyan-300 pb-3 text-white">From library</span><Link className="pb-3 text-slate-400 hover:text-white" to="/battles/new?custom=1">Create your own</Link></div>}
    <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
      <label className="relative flex-1"><Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-500" /><input className="luxe-input w-full pl-10 pr-4 py-2" aria-label="Search challenges" placeholder="Search a task, skill, or runtime" value={query} onChange={event => setQuery(event.target.value)} /></label>
      {section !== "user" ? <div className="grid grid-cols-2 gap-3 lg:w-[330px]">
        <select aria-label="Challenge source" className="luxe-input py-2 px-3" value={kind} onChange={event => setKind(event.target.value)}>{["All", "Built-in", "Template", ...(section === "all" ? ["Saved"] : [])].map(value => <option key={value} value={value} className="bg-[#0b0c10] text-white">{value}</option>)}</select>
        <select aria-label="Difficulty" className="luxe-input py-2 px-3" value={difficulty} onChange={event => setDifficulty(event.target.value)}>{["All", "novice", "general", "advanced", "expert"].map(value => <option key={value} value={value} className="bg-[#0b0c10] text-white">{value === "All" ? "Any difficulty" : value}</option>)}</select>
      </div> : null}
    </div>
    {errors.length > 0 && <div role="alert" className="mb-6 rounded-lg border border-amber-400/20 bg-amber-950/20 p-4 text-sm text-amber-200">{errors.map(error => <p key={error}>{error}</p>)}<button type="button" className="mt-2 underline" onClick={() => setReload(value => value + 1)}>Try again</button></div>}
    {loading ? <p role="status" className="py-12 text-sm text-slate-400">Loading the challenge library…</p> : <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>{visible.length} {visible.length === 1 ? "challenge" : "challenges"}</span>{section === "user" || kind === "Saved" ? <span>Saved to your account and visible only to you.</span> : null}</div>
      {visible.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visible.map(challenge => <article key={challenge.key} className="luxe-card luxe-card-interactive flex min-w-0 flex-col p-5">
          <div className="mb-4 flex items-center justify-between gap-3 text-xs"><span className={challenge.kind === "Saved" ? "text-fuchsia-300 font-medium" : "text-slate-400 font-medium"}>{challenge.kind}</span>{challenge.detail && <Link to={challenge.detail} className="text-slate-400 hover:text-white">Details <span aria-hidden="true">↗</span><span className="sr-only">: {challenge.title}</span></Link>}</div>
          <h2 className="font-display text-lg font-medium leading-snug text-white">{challenge.title}</h2>
          <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-400">{challenge.description}</p>
          <div className="mb-6 mt-4 flex flex-wrap gap-2">{challenge.meta.filter(Boolean).map((meta, index) => <span key={index} className="rounded-md bg-white/[0.04] border border-white/[0.06] px-2 py-1 text-[11px] text-slate-400">{meta.replace(/_/g, " ")}</span>)}</div>
          <Link to={challenge.href} className="mt-auto flex min-h-10 items-center justify-between border-t border-white/[0.08] pt-3 text-sm font-medium text-cyan-300 hover:text-cyan-100" aria-label={(challenge.kind === "Saved" ? "Open " : challenge.key.startsWith("template:") ? "Customize " : "Fight: ") + challenge.title}>{challenge.kind === "Saved" ? "Open challenge" : challenge.key.startsWith("template:") ? "Customize" : "Fight →"}{(challenge.kind === "Saved" || challenge.key.startsWith("template:")) && <ArrowUpRight className="h-4 w-4" />}</Link>
        </article>)}
      </div> : <div className="luxe-card border border-dashed border-white/15 px-6 py-14 text-center"><h2 className="text-lg text-white">{section === "user" ? user ? "No user challenges yet" : "Log in to see your challenges" : kind === "Saved" ? "No saved challenges yet" : "No matching challenges"}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">{section === "user" || kind === "Saved" ? user ? "Create a custom challenge, save it, then add it to your library." : "Your saved custom challenges are tied to your account." : "Try another search or clear the filters."}</p><Link to={(section === "user" || kind === "Saved") && !user ? "/login?next=%2Fchallenges%2Fuser" : "/battles/new?custom=1"} className="btn-luxe-primary mt-5">{(section === "user" || kind === "Saved") && !user ? "Log in" : "Create your own"}</Link></div>}
    </>}
  </>;
}

export default function Targets({ section = "official" }: { section?: CatalogPage }) {
  return <div className="min-h-[calc(100vh-64px)] py-8"><div className="mx-auto max-w-[1440px] px-4 sm:px-6">
    <header className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><h1 className="font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">Challenges</h1><p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">{section === "official" ? "Platform-maintained benchmarks and templates. User saves never enter this collection automatically." : "Custom challenges saved to your account. They stay separate from the Official collection."}</p></div><Link to="/battles/new?custom=1" className="btn-luxe-primary self-start"><Plus className="h-3.5 w-3.5 text-cyan-300" />Create your own</Link></header>
    <ChallengeSectionTabs section={section} />
    <ChallengeLibrary section={section} />
  </div></div>;
}
