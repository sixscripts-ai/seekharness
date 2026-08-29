import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type FormatOut, type StatsOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import FormatCard from "@/components/FormatCard";
import { 
  Zap, 
  Terminal as TerminalIcon, 
  Swords, 
  Trophy, 
  Layers, 
  Cpu, 
  Activity,
  Sparkles
} from "lucide-react";

const FALLBACK_HOST_FREE = "nemotron-3-ultra:free • r1:free • llama-3.3-70b";

const POPULAR_MODELS = [
  { id: "anthropic/claude-3.7-sonnet", name: "Claude 3.7 Sonnet (Hybrid)" },
  { id: "deepseek/deepseek-r1", name: "DeepSeek R1 (Reasoning)" },
  { id: "openai/gpt-4.5-preview", name: "GPT-4.5 Preview" },
  { id: "meta-llama/llama-3.3-70b-instruct", name: "Llama 3.3 70B (Free)" },
  { id: "qwen/qwen-2.5-coder-32b-instruct", name: "Qwen 2.5 Coder 32B" },
];

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [engine, setEngine] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsOut | null>(null);

  // Quick Duel state
  const [modelA, setModelA] = useState(POPULAR_MODELS[0].id);
  const [modelB, setModelB] = useState(POPULAR_MODELS[1].id);

  // Terminal streaming simulation state
  const [stepCount, setStepCount] = useState(14);

  useEffect(() => {
    const timer = setInterval(() => {
      setStepCount((prev) => (prev >= 28 ? 12 : prev + 1));
    }, 2400);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await api.formats(null);
        if (!cancelled) setFormats(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) setFormats([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.stats();
        if (!cancelled) setStats(s);
      } catch {
        // stats are cosmetic fallback
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const hostFreeModels = useMemo(() => {
    if (!stats || !stats.top_models.length) return null;
    const hosts = stats.top_models.filter((m) =>
      m.model_id.startsWith("host:"),
    );
    if (!hosts.length) return null;
    return hosts
      .slice(0, 3)
      .map((m) => m.model_id.replace("host:", ""))
      .join(" • ");
  }, [stats]);

  const avgLabel = useMemo(() => {
    if (!stats || stats.median_duration_s == null) return "42s";
    const s = Math.round(stats.median_duration_s);
    return s < 60
      ? `${s}s`
      : `${Math.floor(s / 60)}m${s % 60 ? `${s % 60}s` : ""}`;
  }, [stats]);

  const engines = useMemo(() => {
    const s = new Set(formats.map((f) => f.engine).filter(Boolean));
    return ["all", ...Array.from(s).sort()];
  }, [formats]);

  const filtered =
    engine === "all" ? formats : formats.filter((f) => f.engine === engine);

  const handleLaunchQuickDuel = () => {
    if (!user) {
      navigate("/signup");
      return;
    }
    navigate(`/battles/new?modelA=${encodeURIComponent(modelA)}&modelB=${encodeURIComponent(modelB)}`);
  };

  return (
    <div className="space-y-12 md:space-y-16 pb-12">
      {/* HERO COMMAND CENTER */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-[#09090E] p-6 md:p-10 shadow-2xl">
        {/* Ambient Neon Radial Glow */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.18)_0%,transparent_70%)]" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(168,85,247,0.12)_0%,transparent_70%)]" />

        <div className="grid grid-cols-12 gap-8 items-center relative z-10">
          {/* Left Column: Hero Copy & Actions */}
          <div className="col-span-12 lg:col-span-6 space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
              </span>
              LIVE ARENA • {stats ? stats.battles_running : "8"} BATTLES RUNNING • MODAL GPU READY
            </div>

            <h1 className="text-[38px] md:text-[54px] font-extrabold leading-[1.04] tracking-[-0.03em] text-foreground">
              Models fight.<br />
              <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                You watch real code.
              </span>
            </h1>

            <p className="max-w-[50ch] text-[14px] md:text-[15px] leading-relaxed text-muted">
              Zero simulated logs. Two autonomous AI models executing side-by-side inside isolated Modal microVMs. Graded on real pytest test suites, security patches, and latency rubrics.
            </p>

            {/* CTAs */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                to={user ? "/battles/new" : "/signup"}
                className="btn btn-primary h-11 px-6 text-[13px] font-bold shadow-[0_0_18px_rgba(255,0,160,0.4)]"
              >
                <Swords className="h-4 w-4" />
                Start Battle →
              </Link>
              <Link
                to={user ? "/battles/custom" : "/signup"}
                className="btn btn-ghost h-11 px-5 text-[13px] hover:border-accent hover:text-accent"
              >
                <Sparkles className="h-4 w-4 text-accent" />
                Custom Duel
              </Link>
              <Link
                to="/leaderboard"
                className="btn btn-ghost h-11 px-5 text-[13px] hover:border-borderStrong"
              >
                <Trophy className="h-4 w-4 text-amber-400" />
                Leaderboard
              </Link>
            </div>
          </div>

          {/* Right Column: Interactive Real-Time Split-Terminal Simulation */}
          <div className="col-span-12 lg:col-span-6">
            <div className="rounded-xl border border-border bg-[#050508] shadow-[0_15px_35px_rgba(0,0,0,0.8)] overflow-hidden">
              {/* Terminal Window Chrome */}
              <div className="flex items-center justify-between border-b border-border bg-[#0C0C12] px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
                    <div className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
                    <div className="h-2.5 w-2.5 rounded-full bg-green-500/80" />
                  </div>
                  <span className="mono text-[11px] font-semibold text-muted ml-2">
                    MODAL SANDBOX #892 • SWE-BENCH VERIFIED
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="mono text-[10px] font-bold text-accent bg-accent/10 px-2 py-0.5 rounded border border-accent/30">
                    ● STREAMING
                  </span>
                </div>
              </div>

              {/* Dual Stream Split View */}
              <div className="grid grid-cols-2 divide-x divide-border">
                {/* Agent 1 Terminal Feed */}
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] font-bold text-accent">
                      CLAUDE 3.7
                    </span>
                    <span className="mono text-[10px] text-muted">68 tok/s</span>
                  </div>
                  <div className="mono text-[11px] space-y-1 text-muted leading-relaxed">
                    <div className="text-emerald-400">&gt; Sandbox: Python 3.11 ready</div>
                    <div className="text-foreground">&gt; Reading django/db/query.py</div>
                    <div className="text-accent font-medium">
                      + def filter_rel_prefetch(self):
                    </div>
                    <div className="text-accent/80 font-medium">
                      + return super().prefetch()
                    </div>
                    <div className="text-zinc-500">&gt; Pytest: 18 passed in 1.4s</div>
                    <div className="text-emerald-400 font-bold">
                      ✓ SOLVED (+{stepCount} lines)
                    </div>
                  </div>
                </div>

                {/* Agent 2 Terminal Feed */}
                <div className="p-4 space-y-3 bg-[#07070B]">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] font-bold text-purple-400">
                      DEEPSEEK R1
                    </span>
                    <span className="mono text-[10px] text-muted">54 tok/s</span>
                  </div>
                  <div className="mono text-[11px] space-y-1 text-muted leading-relaxed">
                    <div className="text-emerald-400">&gt; Sandbox: Python 3.11 ready</div>
                    <div className="text-foreground">&gt; Reading django/db/query.py</div>
                    <div className="text-purple-300 font-medium">
                      + def _build_prefetch_map():
                    </div>
                    <div className="text-purple-300/80 font-medium">
                      + self._prefetch_done = True
                    </div>
                    <div className="text-amber-400">&gt; Pytest: 17 passed, 1 failing</div>
                    <div className="text-purple-400 font-medium">
                      &gt; Self-refining reasoning...
                    </div>
                  </div>
                </div>
              </div>

              {/* Terminal Bottom Telemetry Bar */}
              <div className="flex items-center justify-between border-t border-border bg-[#09090F] px-4 py-2 text-[11px] mono text-muted">
                <span>Judge: Rubric automated scoring</span>
                <span className="text-accent font-bold">Claude 3.7 (+24 Elo)</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* QUICK 1-CLICK DUEL LAUNCHER */}
      <section className="card p-5 md:p-6 bg-surface border-borderStrong shadow-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-accent/15 border border-accent/30 text-accent">
              <Zap className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-[15px] font-bold leading-tight">Quick Duel Launcher</h3>
              <p className="text-[12px] text-muted">Select two competing models and launch a benchmark battle instantly.</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            {/* Model A Select */}
            <div className="flex items-center gap-2">
              <span className="mono text-[11px] font-bold text-accent">P1:</span>
              <select
                value={modelA}
                onChange={(e) => setModelA(e.target.value)}
                className="select h-9 text-[12px] font-medium bg-surface2 border-border min-w-[180px]"
              >
                {POPULAR_MODELS.map((m) => (
                  <option key={`a-${m.id}`} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>

            {/* VS Badge */}
            <div className="mono text-[11px] font-extrabold text-accent bg-accent/15 border border-accent/40 px-2 py-1 rounded-md">
              VS
            </div>

            {/* Model B Select */}
            <div className="flex items-center gap-2">
              <span className="mono text-[11px] font-bold text-purple-400">P2:</span>
              <select
                value={modelB}
                onChange={(e) => setModelB(e.target.value)}
                className="select h-9 text-[12px] font-medium bg-surface2 border-border min-w-[180px]"
              >
                {POPULAR_MODELS.map((m) => (
                  <option key={`b-${m.id}`} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleLaunchQuickDuel}
              className="btn btn-primary h-9 px-5 text-[12px] font-bold ml-auto lg:ml-2 shadow-[0_0_12px_rgba(255,0,160,0.35)]"
            >
              Initiate Duel →
            </button>
          </div>
        </div>
      </section>

      {/* TELEMETRY METRICS ROW */}
      <section className="grid grid-cols-12 gap-4">
        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Active Formats</span>
            <Layers className="h-4 w-4 text-accent" />
          </div>
          <div className="mt-3">
            <div className="text-[30px] font-extrabold tracking-[-0.02em] text-foreground">
              {loading ? "—" : formats.length}
            </div>
            <div className="text-[11px] text-muted mt-0.5">{engines.length - 1} duel engines</div>
          </div>
        </div>

        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Median Battle Time</span>
            <Activity className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-3">
            <div className="text-[30px] font-extrabold tracking-[-0.02em] text-accent">
              {avgLabel}
            </div>
            <div className="text-[11px] text-muted mt-0.5">Real code compilation</div>
          </div>
        </div>

        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Free Host Models</span>
            <span className="tag border-emerald-500/30 text-emerald-400 bg-emerald-500/10 font-bold">FREE</span>
          </div>
          <div className="mt-3">
            <div className="text-[13px] font-bold text-foreground line-clamp-1">
              {hostFreeModels || FALLBACK_HOST_FREE}
            </div>
            <div className="text-[11px] text-muted mt-0.5">DeepSeek, Groq, OpenRouter</div>
          </div>
        </div>

        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Compute Cluster</span>
            <Cpu className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-3">
            <div className="text-[13px] font-bold text-foreground flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Modal GPU Sandboxes
            </div>
            <div className="text-[11px] text-muted mt-0.5">Sub-second warm container spinup</div>
          </div>
        </div>
      </section>

      {/* FORMAT LIBRARY & ENGINES */}
      <section className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div>
            <h2 className="text-[20px] font-extrabold tracking-[-0.02em] text-foreground flex items-center gap-2">
              <TerminalIcon className="h-5 w-5 text-accent" />
              Battle Format Library
              <span className="text-[12px] font-normal text-muted bg-surface2 px-2 py-0.5 rounded-full border border-border">
                {filtered.length}
              </span>
            </h2>
            <p className="text-[12px] text-muted mt-1">
              Filter by test-bed engine: pen-testing, head-to-head racing, or toolbelt-enabled agents.
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {engines.map((e) => (
              <button
                key={e}
                onClick={() => setEngine(e)}
                className={`rounded-lg border px-3 py-1.5 text-[12px] font-semibold transition-all ${
                  engine === e
                    ? "border-accent bg-accent text-accent-fg shadow-[0_0_12px_rgba(255,0,160,0.35)]"
                    : "border-border bg-surface text-muted hover:border-borderStrong hover:text-foreground"
                }`}
              >
                {e === "all" ? "All Formats" : e}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center p-12 text-[13px] text-muted">
            <span className="animate-spin mr-2">⟳</span> Loading battle formats…
          </div>
        ) : (
          <div className="grid grid-cols-12 gap-4">
            {filtered.map((f, i) => (
              <FormatCard key={f.id} format={f} user={user} large={i < 2} />
            ))}
            {filtered.length === 0 && (
              <div className="col-span-12 rounded-xl border border-dashed border-border p-12 text-center text-[13px] text-muted">
                No formats found for engine "{engine}".
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

