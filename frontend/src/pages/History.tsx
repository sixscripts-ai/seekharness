import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { 
  RefreshCw, 
  Search, 
  ArrowUpRight, 
  Swords, 
  ChevronDown, 
  ChevronUp, 
  Cpu, 
  Sparkles,
  CheckCircle2,
  Clock,
  Layers
} from "lucide-react";
import { api, type BattleOut, type FormatOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { battleCreatedAt } from "@/lib/challengeNavigation";

const activeStatuses = new Set(["queued", "running"]);

export default function History() {
  const { user, loading: authLoading } = useAuth();
  const [params] = useSearchParams();
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState(params.get("q") || "");
  const [filter, setFilter] = useState("all");
  const [traceOpenA, setTraceOpenA] = useState(true);
  const [traceOpenB, setTraceOpenB] = useState(true);
  const userId = user?.$id;

  // Sync search query from URL parameter if header search was used
  useEffect(() => {
    const q = params.get("q");
    if (q !== null) setQuery(q);
  }, [params]);

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
        // Auto-refresh lifecycle state while battles are active
        if (rows.some(row => activeStatuses.has(row.status))) timer = setTimeout(load, 15000);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load battles.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    setLoading(true);
    void load();
    void api.formats().then(rows => { if (!cancelled) setFormats(rows); }).catch(() => {});
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
  const featuredBattle = active[0] || recent[0] || null;

  return (
    <div className="min-h-[calc(100vh-64px)] py-8">
      <div className="mx-auto max-w-[1440px] space-y-8 px-4 sm:px-6">

        {/* Page Header with Action Bar */}
        <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                Battles
              </h1>
              {active.length > 0 && (
                <span className="luxe-badge-live">
                  <span className="pulse-dot" />
                  {active.length} Active
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Autonomous agent evaluations, red-team probing, and programmatic verification.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {user && (
              <button 
                type="button" 
                disabled={loading} 
                onClick={() => setReload(v => v + 1)} 
                className="btn-luxe-primary h-9 px-3 text-xs gap-1.5"
                title="Refresh battle state"
              >
                <RefreshCw className={`h-3.5 w-3.5 text-cyan-300 ${loading ? "animate-spin" : ""}`} />
                <span>Refresh</span>
              </button>
            )}
            <Link to="/battles/new" className="btn-luxe-primary h-9 px-4 text-xs font-semibold text-white">
              <span>+ New Battle</span>
            </Link>
          </div>
        </header>

        {authLoading ? (
          <div className="luxe-card p-12 text-center text-slate-400">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent mb-3" />
            <p className="text-xs">Checking your session…</p>
          </div>
        ) : !user ? (
          <div className="luxe-card p-8 md:p-12">
            <div className="grid gap-8 md:grid-cols-[1.3fr_1fr] items-center">
              <div>
                <span className="text-xs font-semibold uppercase tracking-widest text-cyan-300">
                  Arena Control
                </span>
                <h2 className="mt-3 font-display text-3xl font-semibold leading-tight text-white">
                  A challenge. Your models. Verified execution.
                </h2>
                <p className="mt-4 max-w-lg text-xs leading-relaxed text-slate-400">
                  Run Builder vs. Breaker adversarial challenges or evaluate single models against strict programmatic tests in isolated microVM sandboxes.
                </p>
                <Link to="/login?next=%2Fbattles" className="btn-luxe-primary mt-6 inline-flex px-5 py-2 text-xs">
                  Sign in to view battles
                </Link>
              </div>
              <Link to="/challenges" className="luxe-card-interactive luxe-card p-6 block group">
                <span className="text-xs font-medium text-cyan-300">Challenge Library</span>
                <h3 className="mt-2 font-display text-lg font-semibold text-white">
                  Explore 14+ Verified Benchmarks
                </h3>
                <p className="mt-2 text-xs leading-relaxed text-slate-400">
                  From SQL injection defenses to OAuth PKCE replay mitigations and memory leak triage.
                </p>
                <div className="mt-4 flex items-center gap-1.5 text-xs text-cyan-300 group-hover:text-cyan-200">
                  <span>Browse challenges</span>
                  <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </div>
              </Link>
            </div>
          </div>
        ) : (
          <>
            {/* HERO: BATTLE TIMELINE (Matching luxe_precision_ui_1789621377673.jpg) */}
            {featuredBattle && (
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
                      Battle Timeline
                    </span>
                    <span className="text-slate-600">/</span>
                    <span className="text-xs font-mono text-cyan-300">
                      {featuredBattle.id.slice(0, 12)}
                    </span>
                  </div>
                  <Link 
                    to={`/battles/${featuredBattle.id}`}
                    className="flex items-center gap-1.5 text-xs font-medium text-cyan-300 hover:text-cyan-200 transition-colors"
                  >
                    <span>Inspect Live Console</span>
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </div>

                {/* Dual Model Cards with Visual Timeline Node */}
                <div className="relative grid gap-6 lg:grid-cols-[1fr_auto_1fr] items-start">
                  
                  {/* Model A Card */}
                  <div className="luxe-card p-5 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/5 text-cyan-300 font-mono text-sm font-bold shadow-inner">
                          A
                        </div>
                        <div>
                          <div className="font-display font-semibold text-sm text-white">
                            {featuredBattle.model_ids[0] || "Model A"}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {featuredBattle.target_id ? "Builder / Defensive implementation" : "Fighter Slot 1"}
                          </div>
                        </div>
                      </div>
                      <span className="luxe-badge-live">
                        <span className="pulse-dot" />
                        Live Verification
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 border-y border-white/[0.06] py-3 text-center">
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Status</div>
                        <div className="text-xs font-semibold text-white capitalize">{featuredBattle.status}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Timeout</div>
                        <div className="text-xs font-semibold text-white">{featuredBattle.timeout_seconds || 600}s</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Sandbox</div>
                        <div className="text-xs font-semibold text-emerald-400">Isolated</div>
                      </div>
                    </div>

                    {/* Reasoning Trace Accordion */}
                    <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                      <button
                        type="button"
                        onClick={() => setTraceOpenA(!traceOpenA)}
                        className="flex w-full items-center justify-between text-xs font-medium text-slate-300 hover:text-white"
                      >
                        <span className="flex items-center gap-1.5">
                          <Cpu className="h-3.5 w-3.5 text-cyan-400" />
                          <span>Reasoning Trace</span>
                        </span>
                        {traceOpenA ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      </button>
                      {traceOpenA && (
                        <div className="mt-2.5 space-y-1.5 text-[11px] font-mono leading-relaxed text-slate-400 border-t border-white/[0.04] pt-2">
                          <p><span className="text-cyan-400">Step 1:</span> Inspect challenge specifications and workspace assets.</p>
                          <p><span className="text-cyan-400">Step 2:</span> Execute automated test baseline inside MicroVM.</p>
                          <p><span className="text-cyan-400">Step 3:</span> Synthesize patch & verify program correctness.</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Central Visual Connector (Desktop only) */}
                  <div className="hidden lg:flex flex-col items-center justify-center self-stretch px-2 py-4">
                    <div className="h-full w-px bg-gradient-to-b from-transparent via-white/20 to-transparent relative">
                      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 grid h-8 w-8 place-items-center rounded-full border border-white/20 bg-[#0C0E15] shadow-md">
                        <Swords className="h-3.5 w-3.5 text-slate-400" />
                      </div>
                    </div>
                    <div className="mt-3 text-[10px] uppercase font-bold tracking-widest text-slate-500">
                      VS
                    </div>
                  </div>

                  {/* Model B Card */}
                  <div className="luxe-card p-5 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/5 text-purple-300 font-mono text-sm font-bold shadow-inner">
                          B
                        </div>
                        <div>
                          <div className="font-display font-semibold text-sm text-white">
                            {featuredBattle.model_ids[1] || (featuredBattle.model_ids.length === 1 ? "Programmatic Evaluator" : "Model B")}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {featuredBattle.target_id ? "Breaker / Adversarial probe" : "Fighter Slot 2"}
                          </div>
                        </div>
                      </div>
                      <span className="luxe-badge-live">
                        <span className="pulse-dot" />
                        Live Verification
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 border-y border-white/[0.06] py-3 text-center">
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Scoring</div>
                        <div className="text-xs font-semibold text-white">Verified</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Round</div>
                        <div className="text-xs font-semibold text-white">Isolated</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-slate-500 uppercase">Auditor</div>
                        <div className="text-xs font-semibold text-cyan-400">Host Verifier</div>
                      </div>
                    </div>

                    {/* Reasoning Trace Accordion */}
                    <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                      <button
                        type="button"
                        onClick={() => setTraceOpenB(!traceOpenB)}
                        className="flex w-full items-center justify-between text-xs font-medium text-slate-300 hover:text-white"
                      >
                        <span className="flex items-center gap-1.5">
                          <Cpu className="h-3.5 w-3.5 text-purple-400" />
                          <span>Reasoning Trace</span>
                        </span>
                        {traceOpenB ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      </button>
                      {traceOpenB && (
                        <div className="mt-2.5 space-y-1.5 text-[11px] font-mono leading-relaxed text-slate-400 border-t border-white/[0.04] pt-2">
                          <p><span className="text-purple-400">Probe 1:</span> Blackbox port scan and endpoint discovery.</p>
                          <p><span className="text-purple-400">Probe 2:</span> Fuzzing attack vectors for unauthorized privilege escalation.</p>
                          <p><span className="text-purple-400">Probe 3:</span> Payload injection against candidate target endpoints.</p>
                        </div>
                      )}
                    </div>
                  </div>

                </div>
              </section>
            )}

            {/* Filter & Search Bar */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-4">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by challenge, model, or ID..."
                  aria-label="Filter battles"
                  className="luxe-input w-full pl-9 pr-4 py-2 text-xs"
                />
              </div>

              <div className="flex items-center gap-2 text-xs text-slate-400">
                <span>Filter:</span>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="luxe-input py-1.5 px-3 text-xs"
                  aria-label="Status filter"
                >
                  <option value="all">All Battles</option>
                  <option value="running">Running</option>
                  <option value="queued">Queued</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                  <option value="saved">Saved</option>
                </select>
              </div>
            </div>

            {error && (
              <div role="alert" className="luxe-card p-4 text-xs text-rose-300 border-rose-500/20 bg-rose-950/20">
                {error} Use Refresh to try again.
              </div>
            )}

            {/* Active Battles Table (Matching Active Battles list in mockup) */}
            {active.length > 0 && (
              <section className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-cyan-300">
                    Active Battles
                  </span>
                  <span className="rounded-full bg-cyan-400/10 border border-cyan-400/20 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                    {active.length}
                  </span>
                </div>

                <div className="space-y-2">
                  {active.map((battle) => (
                    <div 
                      key={battle.id}
                      className="luxe-card luxe-card-interactive p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="grid h-8 w-8 place-items-center rounded-lg border border-cyan-400/30 bg-cyan-400/10 text-cyan-300 font-mono text-xs">
                          <Swords className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-xs font-semibold text-white">
                            {title(battle)}
                          </div>
                          <div className="truncate text-[11px] text-slate-400">
                            {battle.model_ids.join(" vs ")}
                          </div>
                        </div>
                      </div>

                      {/* Mock progress bar matching the mockup */}
                      <div className="flex items-center gap-4 sm:w-64">
                        <div className="flex-1">
                          <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full w-2/3 animate-pulse" />
                          </div>
                        </div>
                        <span className="text-[11px] font-mono text-slate-400">Live</span>
                      </div>

                      <div className="flex items-center gap-3">
                        <Link 
                          to={`/battles/${battle.id}`}
                          className="btn-luxe-primary h-8 px-3 text-xs"
                        >
                          <span>View Details</span>
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Recent Results Section */}
            <section className="space-y-3">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Recent Results
              </div>

              {!filtered.length ? (
                <div className="luxe-card p-12 text-center text-slate-400">
                  <p className="text-xs">No matching battles found.</p>
                </div>
              ) : (
                <div className="luxe-card divide-y divide-white/[0.06] overflow-hidden">
                  {recent.map((battle) => {
                    const timestamp = battleCreatedAt(battle);
                    return (
                      <Link
                        key={battle.id}
                        to={`/battles/${battle.id}`}
                        className="group flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 hover:bg-white/[0.02] transition-colors"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 font-medium text-xs text-white group-hover:text-cyan-300 transition-colors">
                            <span className="truncate">{title(battle)}</span>
                            <ArrowUpRight className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="mt-1 truncate text-[11px] text-slate-400">
                            {battle.model_ids.join(" vs ")}
                          </div>
                        </div>

                        <div className="text-[11px] text-slate-500 font-mono">
                          {timestamp ? new Date(timestamp).toLocaleDateString() : "—"}
                        </div>

                        <div>
                          <span className={`inline-block rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                            battle.status === "completed" 
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : battle.status === "failed"
                              ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              : "bg-white/5 text-slate-300 border border-white/10"
                          }`}>
                            {battle.status}
                          </span>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}

      </div>
    </div>
  );
}
