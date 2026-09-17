import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Search, ArrowUpRight } from "lucide-react";
import { api, type BattleOut, type FormatOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { battleCreatedAt } from "@/lib/challengeNavigation";

const activeStatuses = new Set(["queued", "running"]);

export default function History() {
  const { user, loading: authLoading } = useAuth();
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const userId = user?.$id;

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setBattles([]);
    if (!userId) { setLoading(false); return; }
    async function load() {
      try {
        const token = await useAuth.getState().refreshJwt();
        if (!token) throw new Error("Your session ended. Log in to load your battles.");
        const rows = await api.listBattles(token);
        if (cancelled) return;
        setBattles(rows);
        setError("");
        // Refresh lifecycle state only while something is still queued or running.
        if (rows.some(row => activeStatuses.has(row.status))) timer = setTimeout(load, 15000);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load battles.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    setLoading(true);
    void load();
    void api.formats().then(rows => { if (!cancelled) setFormats(rows); }).catch(() => {
      // Format labels are optional; the battle's own contract/id stays visible.
    });
    return () => { cancelled = true; clearTimeout(timer); };
  }, [userId, reload]);

  const title = (battle: BattleOut) => battle.title || battle.custom_title || battle.target_id ||
    formats.find(format => format.id === battle.format_id)?.name || battle.format_id || "Untitled battle";
  const filtered = useMemo(() => battles.filter(battle => {
    const matchesFilter = filter === "all" || (filter === "saved" ? battle.saved : battle.status === filter);
    const text = [battle.id, battle.title, battle.custom_title, battle.target_id, battle.format_id, ...battle.model_ids].join(" ").toLowerCase();
    return matchesFilter && text.includes(query.toLowerCase().trim());
  }).sort((a, b) => battleCreatedAt(b) - battleCreatedAt(a)), [battles, filter, query]);
  const active = filtered.filter(battle => activeStatuses.has(battle.status));
  const recent = filtered.filter(battle => !activeStatuses.has(battle.status));

  function battleRow(battle: BattleOut) {
    const failure = battle.failure_reason || battle.termination_reason;
    const timestamp = battleCreatedAt(battle);
    return <Link key={battle.id} to={"/battles/" + battle.id} className="group grid gap-3 border-t border-white/10 px-4 py-5 hover:bg-white/[0.03] sm:grid-cols-[minmax(0,1fr)_150px_100px] sm:items-center sm:px-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2 font-medium text-white"><span className="truncate">{title(battle)}</span><ArrowUpRight className="h-4 w-4 shrink-0 text-slate-500 group-hover:text-cyan-300" /></div>
        <div className="mt-1 break-words text-xs leading-relaxed text-slate-400">{battle.model_ids.join(" vs ")}</div>
        {failure && <p className="mt-2 break-words text-xs text-rose-300">{failure.replace(/_/g, " ")}</p>}
      </div>
      <div className="text-xs text-slate-500">{timestamp ? new Date(timestamp).toLocaleString() : "Time unavailable"}</div>
      <div className="sm:text-right"><span className={"inline-block rounded-md px-2 py-1 text-xs " + (battle.status === "running" ? "bg-cyan-400/10 text-cyan-300" : battle.status === "failed" ? "bg-rose-400/10 text-rose-300" : "bg-white/5 text-slate-300")}>{battle.status || "Unknown"}</span></div>
    </Link>;
  }

  return <div className="battle-workspace min-h-[calc(100vh-64px)] bg-[#08090D]/95">
    <div className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8 sm:py-12">
      <header className="mb-9 flex items-start justify-between gap-4">
        <div><h1 className="font-display text-3xl font-semibold tracking-tight text-white sm:text-4xl">Battles</h1><p className="mt-2 text-sm text-slate-400">Follow a run. Inspect the result. Try the next challenge.</p></div>
        {user && <button type="button" disabled={loading} onClick={() => setReload(value => value + 1)} className="btn btn-ghost h-10 gap-2" aria-label="Refresh battles"><RefreshCw className="h-4 w-4" /><span className="hidden sm:inline">Refresh</span></button>}
      </header>
      {authLoading ? <p role="status" className="text-slate-400">Checking your session…</p> : !user ? <div className="grid gap-8 border-y border-white/10 py-12 md:grid-cols-[1.2fr_1fr]">
        <div><h2 className="max-w-md font-display text-3xl leading-tight text-white">A challenge.<br />Your models.<br />A result you can inspect.</h2><p className="mt-5 max-w-md text-sm leading-6 text-slate-400">Choose from the challenge library or write your own. Sign in to run battles and keep your results in one place.</p><Link to="/login?next=%2Fbattles" className="btn btn-primary mt-6">Log in to see your battles</Link></div>
        <Link to="/challenges" className="group flex flex-col justify-between rounded-xl border border-cyan-300/20 bg-[#11141E] p-7"><div><span className="text-sm text-cyan-300">Challenge library</span><h2 className="mt-3 font-display text-2xl text-white">Find something worth testing.</h2><p className="mt-3 text-sm leading-6 text-slate-400">Coding tasks, security challenges, and templates for your next experiment.</p></div><span className="mt-8 flex items-center gap-2 text-sm text-white">Browse challenges <ArrowUpRight className="h-4 w-4" /></span></Link>
      </div> : <>
        <div className="mb-7 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="relative sm:w-80"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-500" /><input aria-label="Search battles" className="input pl-10" placeholder="Search challenges, models, or battle ID" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <label className="flex items-center gap-3 text-sm text-slate-400">Show<select className="select w-auto" value={filter} onChange={event => setFilter(event.target.value)}>{["all", "running", "queued", "completed", "failed", "cancelled", "saved"].map(value => <option key={value} value={value}>{value === "all" ? "All battles" : value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
        </div>
        {error && <p role="alert" className="mb-5 break-words rounded-lg border border-rose-400/20 bg-rose-950/20 p-4 text-sm text-rose-200">{error} Use Refresh to try again.</p>}
        {loading ? <p role="status" className="py-12 text-slate-400">Loading battles…</p> : !filtered.length && !error ? <div className="rounded-xl border border-dashed border-white/15 py-14 text-center"><h2 className="text-xl text-white">{battles.length ? "No matching battles" : "Your first battle starts with a challenge."}</h2><p className="mt-2 text-sm text-slate-400">{battles.length ? "Try a different search or filter." : "Pick a task from the library, then choose the models."}</p><Link to="/battles/new" className="btn btn-primary mt-6">Choose a challenge</Link></div> : <>
          {active.length > 0 && <section className="mb-9 overflow-hidden rounded-xl border border-cyan-300/20 bg-[#11141E]" aria-label="Active battles"><h2 className="px-6 py-4 text-sm font-semibold text-cyan-300">In progress <span className="ml-2 text-slate-500">{active.length}</span></h2>{active.map(battleRow)}</section>}
          <section aria-label="Recent results"><h2 className="mb-4 text-lg font-medium text-white">Recent results</h2>{recent.length ? <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11141E]/60">{recent.map(battleRow)}</div> : <p className="text-sm text-slate-500">No finished battles in this view.</p>}</section>
        </>}
      </>}
    </div>
  </div>;
}
