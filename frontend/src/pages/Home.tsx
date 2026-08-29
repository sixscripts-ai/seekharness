import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  type BattleOut,
  type FormatOut,
  type ProviderOut,
  type StatsOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useHiddenProviders } from "@/lib/hiddenProviders";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Flame,
  Layers,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Sparkles,
  Swords,
  Trophy,
  Zap,
} from "lucide-react";

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function Home() {
  const { user, jwt, refreshJwt } = useAuth();
  const { isHidden } = useHiddenProviders();
  const navigate = useNavigate();

  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [stats, setStats] = useState<StatsOut | null>(null);
  const [statsFailed, setStatsFailed] = useState(false);
  const [recentBattles, setRecentBattles] = useState<BattleOut[]>([]);
  const [loading, setLoading] = useState(true);

  // Quick Duel selected models
  const [fighterA, setFighterA] = useState<string>("");
  const [fighterB, setFighterB] = useState<string>("");
  const [selectedFormat, setSelectedFormat] = useState<string>("");
  const [launching, setLaunching] = useState(false);

  const visibleProviders = useMemo(
    () => providers.filter((p) => !isHidden(p.id)),
    [providers, isHidden],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setLoading(true);
      try {
        const [fList, sData] = await Promise.all([
          api.formats(null).catch(() => []),
          api.stats().catch(() => null),
        ]);

        if (cancelled) return;
        setFormats(Array.isArray(fList) ? fList : []);
        setStats(sData);
        setStatsFailed(sData === null);

        if (fList.length > 0) {
          setSelectedFormat(fList[0].id);
        }

        // If authenticated, load real battles & providers
        const token = (await refreshJwt()) || jwt;
        if (token) {
          const [pList, bList] = await Promise.all([
            api.providers(token).catch(() => []),
            api.listBattles(token).catch(() => []),
          ]);

          if (cancelled) return;
          setProviders(pList);
          setRecentBattles(bList);

          if (pList.length >= 2) {
            setFighterA(pList[0].id);
            setFighterB(pList[1].id);
          } else if (pList.length === 1) {
            setFighterA(pList[0].id);
            setFighterB(pList[0].id);
          }
        }
      } catch (e) {
        console.error("Failed to load arena home data:", e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadData();
    return () => {
      cancelled = true;
    };
  }, [jwt, refreshJwt]);

  // Derived Activity Counts
  const { runningBattles, completedBattles, activeLiveBattle } = useMemo(() => {
    const running = recentBattles.filter((b) => b.status === "running");
    const completed = recentBattles.filter((b) => b.status === "completed");
    return {
      runningBattles: running,
      completedBattles: completed,
      activeLiveBattle: running[0] || null,
    };
  }, [recentBattles]);

  async function handleQuickLaunch(e: React.FormEvent) {
    e.preventDefault();
    if (!fighterA || !fighterB || !selectedFormat) return;

    setLaunching(true);
    try {
      const token = (await refreshJwt()) || jwt;
      if (!token) {
        navigate(
          `/battles/new?format=${encodeURIComponent(
            selectedFormat,
          )}&modelA=${encodeURIComponent(fighterA)}&modelB=${encodeURIComponent(
            fighterB,
          )}`,
        );
        return;
      }

      const res = await api.createBattle(token, {
        format_id: selectedFormat,
        model_ids: [fighterA, fighterB],
        timeout_seconds: 600,
        save: true,
      });
      navigate(`/battles/${res.id}`);
    } catch (e) {
      console.error("Quick duel launch error:", e);
      navigate("/battles/new");
    } finally {
      setLaunching(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] py-8 text-foreground">
      <div className="mx-auto max-w-[1560px] space-y-10 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* 1. HERO ARENA OVERVIEW COCKPIT                                    */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-2xl space-y-8 md:p-10">
          {/* Ambient Neon Radial Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.22)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.12)_0%,transparent_70%)]"></div>

          {/* Hero Header & Tagline */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-[#1F1F22] pb-8 lg:flex-row lg:items-end">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
                </span>
                HERMETIC CODE GENERATION & ADVERSARIAL REASONING ARENA
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white sm:text-4xl md:text-5xl">
                Models compete.{" "}
                <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                  Evidence decides.
                </span>
              </h1>
              <p className="text-xs leading-relaxed text-zinc-400 sm:text-sm">
                Frontier LLMs face off in isolated Modal MicroVMs. Automated
                harnesses enforce builder implementations, breaker exploits, and
                hard pytest acceptance suites with zero simulated results.
              </p>
            </div>

            {/* Quick Action Buttons */}
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to="/battles/new"
                className="btn btn-primary flex h-11 items-center gap-2 px-6 text-xs font-bold shadow-[0_0_18px_rgba(255,0,160,0.4)]"
              >
                <Swords className="h-4 w-4" />
                <span>Deploy Battle</span>
              </Link>
              <Link
                to="/battles/custom"
                className="mono flex h-11 items-center gap-2 rounded-lg border border-[#2A2A2E] bg-[#050508] px-5 text-xs font-bold text-zinc-300 transition-all hover:border-accent/60 hover:text-white"
              >
                <Sparkles className="h-3.5 w-3.5 text-accent" />
                <span>Custom Challenge</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* 2. ARENA ACTIVITY TELEMETRY DECK                                 */}
          {/* =============================================================== */}
          <div className="relative z-10 grid grid-cols-12 gap-6">
            {/* Real Stats Metric Box (4 cols) */}
            <div className="col-span-12 flex flex-col justify-between rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl lg:col-span-4 space-y-6">
              <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-accent" />
                  <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                    Arena Activity
                  </span>
                </div>
                <span className="mono text-[10px] text-zinc-500">
                  REAL-TIME CLUSTER
                </span>
              </div>

              <div className="space-y-3 mono text-xs">
                <div className="flex items-center justify-between rounded-lg border border-emerald-500/20 bg-emerald-950/20 px-3.5 py-2 text-emerald-400 font-bold">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span>RUNNING BATTLES</span>
                  </div>
                  <span className="text-sm">
                    {loading
                      ? "—"
                      : stats?.battles_running ?? runningBattles.length}
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-[#1F1F22] bg-[#0D0D0F] px-3.5 py-2 text-zinc-300">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5 text-accent" />
                    <span>COMPLETED TOTAL</span>
                  </div>
                  <span className="text-sm font-bold text-white">
                    {loading
                      ? "—"
                      : stats?.battles_total ?? completedBattles.length}
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-lg border border-[#1F1F22] bg-[#0D0D0F] px-3.5 py-2 text-zinc-400">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3.5 w-3.5 text-zinc-500" />
                    <span>MEDIAN EXEC TIME</span>
                  </div>
                  <span className="font-bold text-zinc-200">
                    {loading || !stats || stats.median_duration_s == null
                      ? "—"
                      : `${Math.round(stats.median_duration_s)}s`}
                  </span>
                </div>
              </div>

              <div className="border-t border-[#1F1F22] pt-3 text-[11px] text-zinc-500 mono">
                {statsFailed && !loading ? (
                  "Cluster telemetry unavailable right now — values above reflect your own battles."
                ) : (
                  "Platform: Modal MicroVM sandbox cluster · Pytest isolated test execution"
                )}
              </div>
            </div>

            {/* Live Active Battle or Clean Empty State (8 cols) */}
            <div className="col-span-12 rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl lg:col-span-8 flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-accent animate-pulse"></span>
                  <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                    {activeLiveBattle ? "Active Battle Stream" : "Active Battle Status"}
                  </span>
                </div>
                <Link
                  to="/battles"
                  className="mono text-[11px] text-accent hover:underline flex items-center gap-1"
                >
                  <span>Battle Archive</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {activeLiveBattle ? (
                <div className="space-y-4 py-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="mono text-[10px] uppercase font-bold text-accent">
                        {activeLiveBattle.format_id}
                      </div>
                      <h3 className="text-base font-extrabold text-white">
                        {activeLiveBattle.title || "Live Adversarial Match"}
                      </h3>
                    </div>
                    <span className="mono inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/15 px-3 py-0.5 text-xs font-bold text-accent self-start">
                      <Radio className="h-3 w-3 animate-pulse" />
                      LIVE EXECUTION
                    </span>
                  </div>

                  {/* Fighter Sequence Pipeline */}
                  <div className="rounded-lg border border-[#1F1F22] bg-[#09090E] p-4 space-y-3">
                    <div className="flex items-center justify-between mono text-xs">
                      <span className="font-bold text-white">
                        {(activeLiveBattle.model_ids || [])[0] || "Fighter A"}
                      </span>
                      <span className="text-zinc-500 font-medium">
                        BUILD → SNAPSHOT → BREAK → VERIFY → JUDGE
                      </span>
                      <span className="font-bold text-accent">
                        {(activeLiveBattle.model_ids || [])[1] || "Fighter B"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs pt-1 border-t border-[#1F1F22] text-zinc-400 mono">
                      <span>Status: <strong className="text-emerald-400">EXECUTING IN MODAL</strong></span>
                      <span>ID: <strong className="text-zinc-300">{activeLiveBattle.id.slice(0, 10)}…</strong></span>
                    </div>
                  </div>

                  <div className="flex justify-end pt-1">
                    <Link
                      to={`/battles/${activeLiveBattle.id}`}
                      className="btn btn-primary h-9 px-5 text-xs font-bold flex items-center gap-2"
                    >
                      <span>OPEN BATTLE →</span>
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center space-y-3 my-auto">
                  <Radio className="mx-auto h-8 w-8 text-zinc-600" />
                  <h4 className="text-sm font-bold text-white">
                    NO ACTIVE BATTLES
                  </h4>
                  <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                    No sandboxes are currently running. Launch a preset format or
                    design a custom acceptance test challenge.
                  </p>
                  <Link
                    to="/battles/new"
                    className="btn btn-primary mx-auto inline-flex h-9 items-center gap-2 px-5 text-xs font-bold mt-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Deploy A Battle</span>
                  </Link>
                </div>
              )}
            </div>
          </div>

          {/* =============================================================== */}
          {/* 3. RECENT VERIFIED RESULTS & DYNAMIC QUICK DUEL                  */}
          {/* =============================================================== */}
          <div className="relative z-10 grid grid-cols-12 gap-6 pt-4">
            {/* Recent Verified Results (7 cols) */}
            <div className="col-span-12 rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl lg:col-span-7 flex flex-col justify-between space-y-5">
              <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-accent" />
                  <h2 className="mono text-xs font-bold uppercase tracking-wider text-white">
                    Recent Verified Results
                  </h2>
                </div>
                <Link
                  to="/leaderboard"
                  className="mono text-[11px] text-zinc-400 hover:text-white"
                >
                  View Rankings →
                </Link>
              </div>

              {completedBattles.length === 0 ? (
                <div className="py-8 text-center space-y-2">
                  <Trophy className="mx-auto h-7 w-7 text-zinc-600" />
                  <p className="text-xs text-zinc-400">
                    No verified completed battles in your current session history.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {completedBattles.slice(0, 3).map((b) => (
                    <Link
                      key={b.id}
                      to={`/battles/${b.id}`}
                      className="block rounded-lg border border-[#1F1F22] bg-[#09090E] p-4 transition-all hover:border-accent/40"
                    >
                      <div className="flex items-center justify-between">
                        <div className="space-y-1">
                          <div className="mono text-[10px] text-accent font-bold">
                            {b.format_id}
                          </div>
                          <div className="text-xs font-bold text-white">
                            {(b.model_ids || []).join("  vs  ")}
                          </div>
                        </div>
                        <div className="mono text-right text-xs">
                          <span className="text-emerald-400 font-bold">
                            VERIFIED RESULT
                          </span>
                          <div className="text-[10px] text-zinc-500">
                            Replay available →
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}

              <div className="border-t border-[#1F1F22] pt-3 flex items-center justify-between mono text-[11px] text-zinc-500">
                <span>All matches evaluated in ephemeral isolated microVMs.</span>
                <Link to="/battles" className="text-accent hover:underline">
                  All Archive Records
                </Link>
              </div>
            </div>

            {/* Dynamic Quick Duel Launcher (5 cols) */}
            <div className="col-span-12 rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl lg:col-span-5 flex flex-col justify-between space-y-5">
              <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-accent" />
                  <h2 className="mono text-xs font-bold uppercase tracking-wider text-white">
                    Quick Match Launcher
                  </h2>
                </div>
                <span className="mono text-[10px] text-zinc-500">ONE-CLICK LAUNCH</span>
              </div>

              <form onSubmit={handleQuickLaunch} className="space-y-3.5">
                <div>
                  <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                    Format
                  </label>
                  <select
                    value={selectedFormat}
                    onChange={(e) => setSelectedFormat(e.target.value)}
                    className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-3 py-2 text-xs text-white focus:border-accent focus:outline-none"
                  >
                    {formats.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Fighter A
                    </label>
                    <select
                      value={fighterA}
                      onChange={(e) => setFighterA(e.target.value)}
                      className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-2.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                    >
                      {visibleProviders.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                      {visibleProviders.length === 0 && (
                        <option value="host:modal-kimi">Kimi K3 (Platform)</option>
                      )}
                    </select>
                  </div>

                  <div>
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Fighter B
                    </label>
                    <select
                      value={fighterB}
                      onChange={(e) => setFighterB(e.target.value)}
                      className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-2.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                    >
                      {visibleProviders.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                      {visibleProviders.length === 0 && (
                        <option value="host:openrouter-free">DeepSeek R1 (Platform)</option>
                      )}
                    </select>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={launching}
                  className="btn btn-primary flex h-10 w-full items-center justify-center gap-2 text-xs font-bold shadow-[0_0_14px_rgba(255,0,160,0.3)] mt-2"
                >
                  {launching ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      <span>Provisioning Sandbox…</span>
                    </>
                  ) : (
                    <>
                      <Play className="h-3.5 w-3.5" />
                      <span>Launch Instant Match</span>
                    </>
                  )}
                </button>
              </form>

              <div className="mono text-[10px] text-zinc-500 text-center">
                Runs on unranked sandbox runtime. Replay automatically preserved.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
