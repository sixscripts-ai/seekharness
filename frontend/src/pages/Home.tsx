import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type BattleOut,
  type StatsOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Plus,
  Radio,
  Sparkles,
  Swords,
} from "lucide-react";

export default function Home() {
  const { jwt, refreshJwt } = useAuth();

  const [stats, setStats] = useState<StatsOut | null>(null);
  const [statsFailed, setStatsFailed] = useState(false);
  const [recentBattles, setRecentBattles] = useState<BattleOut[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setLoading(true);
      try {
        const sData = await api.stats().catch(() => null);

        if (cancelled) return;
        setStats(sData);
        setStatsFailed(sData === null);

        const token = (await refreshJwt()) || jwt;
        if (token) {
          const bList = await api.listBattles(token).catch(() => []);
          if (cancelled) return;
          setRecentBattles(Array.isArray(bList) ? bList : []);
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

  return (
    <div className="min-h-[calc(100vh-56px)] bg-transparent py-8 text-foreground relative z-10">
      <div className="mx-auto max-w-[1560px] space-y-10 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* 1. HERO ARENA OVERVIEW COCKPIT                                    */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0C0E15]/85 backdrop-blur-xl p-6 shadow-2xl space-y-8 md:p-10">
          {/* Ambient Radiant Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(0,210,255,0.18)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(217,70,239,0.14)_0%,transparent_70%)]"></div>

          {/* Hero Header & Tagline */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-white/[0.08] pb-8 lg:flex-row lg:items-end">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1 text-[11px] font-semibold text-cyan-300 shadow-[0_0_16px_rgba(0,210,255,0.25)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400"></span>
                </span>
                HERMETIC CODE GENERATION & ADVERSARIAL REASONING ARENA
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white sm:text-4xl md:text-5xl">
                Models compete.{" "}
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#00D2FF] via-[#38BDF8] to-[#D946EF] drop-shadow-[0_0_24px_rgba(0,210,255,0.45)]">
                  Evidence decides.
                </span>
              </h1>
              <p className="text-xs leading-relaxed text-zinc-300 sm:text-sm">
                Frontier LLMs face off in isolated Modal MicroVMs. Automated
                harnesses enforce builder implementations, breaker exploits, and
                hard pytest acceptance suites with zero simulated results.
              </p>
            </div>

            {/* Quick Action Buttons */}
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to="/battles/new"
                className="qos-btn-glow flex h-11 items-center gap-2 px-6 text-xs font-bold"
              >
                <Swords className="h-4 w-4" />
                <span>Deploy Battle</span>
              </Link>
              <Link
                to="/battles/custom"
                className="mono flex h-11 items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] backdrop-blur-md px-5 text-xs font-bold text-zinc-200 transition-all hover:border-cyan-400/60 hover:text-white hover:shadow-[0_0_16px_rgba(0,210,255,0.2)]"
              >
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                <span>Custom Challenge</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* 2. ARENA ACTIVITY TELEMETRY DECK                                 */}
          {/* =============================================================== */}
          <div className="relative z-10 grid grid-cols-12 gap-6">
            {/* Real Stats Metric Box (4 cols) */}
            <div className="col-span-12 flex flex-col justify-between rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-6 shadow-xl lg:col-span-4 space-y-6">
              <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-cyan-400" />
                  <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                    Arena Activity
                  </span>
                </div>
                <span className="mono text-[10px] text-zinc-400">
                  REAL-TIME CLUSTER
                </span>
              </div>

              <div className="space-y-3 mono text-xs">
                <div className="flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-950/30 px-3.5 py-2.5 text-emerald-400 font-bold shadow-[0_0_12px_rgba(16,185,129,0.15)]">
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

                <div className="flex items-center justify-between rounded-xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5 text-zinc-300">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />
                    <span>COMPLETED TOTAL</span>
                  </div>
                  <span className="text-sm font-bold text-white">
                    {loading
                      ? "—"
                      : stats?.battles_total ?? completedBattles.length}
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-xl border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5 text-zinc-400">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3.5 w-3.5 text-zinc-400" />
                    <span>MEDIAN EXEC TIME</span>
                  </div>
                  <span className="font-bold text-zinc-200">
                    {loading || !stats || stats.median_duration_s == null
                      ? "—"
                      : `${Math.round(stats.median_duration_s)}s`}
                  </span>
                </div>
              </div>

              <div className="border-t border-white/[0.08] pt-3 text-[11px] text-zinc-400 mono">
                {statsFailed && !loading ? (
                  "Cluster telemetry unavailable right now — values above reflect your own battles."
                ) : (
                  "Platform: Modal MicroVM sandbox cluster · Pytest isolated test execution"
                )}
              </div>
            </div>

            {/* Live Active Battle or Clean Empty State (8 cols) */}
            <div className="col-span-12 rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-6 shadow-xl lg:col-span-8 flex flex-col justify-between space-y-4">
              <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse"></span>
                  <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                    {activeLiveBattle ? "Active Battle Stream" : "Active Battle Status"}
                  </span>
                </div>
                <Link
                  to="/battles"
                  className="mono text-[11px] text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 transition-colors"
                >
                  <span>Battle Archive</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {activeLiveBattle ? (
                <div className="space-y-4 py-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="mono text-[10px] uppercase font-bold text-cyan-400">
                        {activeLiveBattle.format_id}
                      </div>
                      <h3 className="text-base font-extrabold text-white">
                        {activeLiveBattle.title || "Live Adversarial Match"}
                      </h3>
                    </div>
                    <span className="mono inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-400/15 px-3 py-0.5 text-xs font-bold text-cyan-300 self-start shadow-[0_0_12px_rgba(0,210,255,0.25)]">
                      <Radio className="h-3 w-3 animate-pulse" />
                      LIVE EXECUTION
                    </span>
                  </div>

                  {/* Fighter Sequence Pipeline */}
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
                    <div className="flex items-center justify-between mono text-xs">
                      <span className="font-bold text-white">
                        {(activeLiveBattle.model_ids || [])[0] || "Fighter A"}
                      </span>
                      <span className="text-zinc-400 font-medium">
                        BUILD → SNAPSHOT → BREAK → VERIFY → JUDGE
                      </span>
                      <span className="font-bold text-magenta-neon">
                        {(activeLiveBattle.model_ids || [])[1] || "Fighter B"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs pt-1 border-t border-white/[0.08] text-zinc-400 mono">
                      <span>Status: <strong className="text-emerald-400">EXECUTING IN MODAL</strong></span>
                      <span>ID: <strong className="text-zinc-300">{activeLiveBattle.id.slice(0, 10)}…</strong></span>
                    </div>
                  </div>

                  <div className="flex justify-end pt-1">
                    <Link
                      to={`/battles/${activeLiveBattle.id}`}
                      className="qos-btn-glow h-9 px-5 text-xs font-bold flex items-center gap-2"
                    >
                      <span>OPEN BATTLE →</span>
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center space-y-3 my-auto">
                  <Radio className="mx-auto h-8 w-8 text-zinc-500" />
                  <h4 className="text-sm font-bold text-white">
                    NO ACTIVE BATTLES
                  </h4>
                  <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                    No sandboxes are currently running. Launch a preset format or
                    design a custom acceptance test challenge.
                  </p>
                  <Link
                    to="/battles/new"
                    className="qos-btn-glow mx-auto inline-flex h-9 items-center gap-2 px-5 text-xs font-bold mt-2"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Deploy A Battle</span>
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
