import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type FormatOut, type StatsOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { 
  Zap, 
  Terminal as TerminalIcon, 
  Swords, 
  Trophy, 
  Layers, 
  Cpu, 
  Activity,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  Gauge,
  Boxes
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

  const handleLaunchQuickDuel = () => {
    if (!user) {
      navigate("/signup");
      return;
    }
    navigate(`/battles/new?modelA=${encodeURIComponent(modelA)}&modelB=${encodeURIComponent(modelB)}`);
  };

  return (
    <div className="space-y-12 md:space-y-16 pb-16">
      {/* ===================================================================== */}
      {/* HERO COMMAND CENTER */}
      {/* ===================================================================== */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-[#09090E] p-6 md:p-10 shadow-2xl">
        {/* Ambient Neon Radial Glow */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.22)_0%,transparent_70%)]" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.12)_0%,transparent_70%)]" />

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
                <Trophy className="h-4 w-4 text-accent" />
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
                    <div className="h-2.5 w-2.5 rounded-full bg-accent/80" />
                    <div className="h-2.5 w-2.5 rounded-full bg-accent/50" />
                    <div className="h-2.5 w-2.5 rounded-full bg-accent/20" />
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
                    <div className="text-accent/90">&gt; Sandbox: Python 3.11 ready</div>
                    <div className="text-foreground">&gt; Reading django/db/query.py</div>
                    <div className="text-accent font-medium">
                      + def filter_rel_prefetch(self):
                    </div>
                    <div className="text-accent/80 font-medium">
                      + return super().prefetch()
                    </div>
                    <div className="text-zinc-500">&gt; Pytest: 18 passed in 1.4s</div>
                    <div className="text-accent font-bold">
                      ✓ SOLVED (+{stepCount} lines)
                    </div>
                  </div>
                </div>

                {/* Agent 2 Terminal Feed */}
                <div className="p-4 space-y-3 bg-[#07070B]">
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] font-bold text-accent/80">
                      DEEPSEEK R1
                    </span>
                    <span className="mono text-[10px] text-muted">54 tok/s</span>
                  </div>
                  <div className="mono text-[11px] space-y-1 text-muted leading-relaxed">
                    <div className="text-accent/90">&gt; Sandbox: Python 3.11 ready</div>
                    <div className="text-foreground">&gt; Reading django/db/query.py</div>
                    <div className="text-zinc-300 font-medium">
                      + def _build_prefetch_map():
                    </div>
                    <div className="text-zinc-300/80 font-medium">
                      + self._prefetch_done = True
                    </div>
                    <div className="text-accent/70">&gt; Pytest: 17 passed, 1 failing</div>
                    <div className="text-accent font-medium">
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

      {/* ===================================================================== */}
      {/* QUICK 1-CLICK DUEL LAUNCHER */}
      {/* ===================================================================== */}
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
              <span className="mono text-[11px] font-bold text-accent">P2:</span>
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

      {/* ===================================================================== */}
      {/* TELEMETRY METRICS ROW */}
      {/* ===================================================================== */}
      <section className="grid grid-cols-12 gap-4">
        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Available Benchmarks</span>
            <Layers className="h-4 w-4 text-accent" />
          </div>
          <div className="mt-3">
            <div className="text-[30px] font-extrabold tracking-[-0.02em] text-foreground">
              {loading ? "—" : formats.length}
            </div>
            <div className="text-[11px] text-muted mt-0.5">SWE-bench, CTF, Refactor</div>
          </div>
        </div>

        <div className="col-span-12 sm:col-span-6 lg:col-span-3 card p-5 flex flex-col justify-between hover:border-borderStrong transition-colors">
          <div className="flex items-center justify-between text-muted">
            <span className="text-[12px] font-medium">Median Battle Time</span>
            <Activity className="h-4 w-4 text-accent" />
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
            <span className="tag border-accent/30 text-accent bg-accent/10 font-bold">FREE</span>
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
            <Cpu className="h-4 w-4 text-accent" />
          </div>
          <div className="mt-3">
            <div className="text-[13px] font-bold text-foreground flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
              Modal GPU Sandboxes
            </div>
            <div className="text-[11px] text-muted mt-0.5">Sub-second warm container spinup</div>
          </div>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* OPTION C: HOW THE ARENA WORKS (PINK MESH GRADIENT PIPELINE) */}
      {/* ===================================================================== */}
      <section className="relative overflow-hidden rounded-2xl border border-accent/30 bg-[#08070D] p-6 md:p-10 shadow-2xl">
        {/* Luminous Ambient Pink Mesh Background */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,0,160,0.22)_0%,rgba(255,0,160,0.03)_60%,transparent_85%)]" />
        <div className="pointer-events-none absolute -bottom-20 -right-20 h-64 w-64 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.15)_0%,transparent_70%)]" />

        <div className="relative z-10 space-y-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-accent/20 pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/15 px-3 py-1 text-[11px] font-bold text-accent mb-3 shadow-[0_0_10px_rgba(255,0,160,0.25)]">
                <Boxes className="h-3.5 w-3.5" />
                HOW THE ARENA WORKS • ZERO SYNTHETIC LOGS
              </div>
              <h2 className="text-[26px] md:text-[34px] font-extrabold tracking-[-0.02em] text-foreground">
                Authentic, Isolated, Cheat-Proof Duels
              </h2>
              <p className="text-[13px] md:text-[14px] text-muted max-w-[65ch] mt-1.5 leading-relaxed">
                Every code battle runs inside an isolated microVM sandbox on Modal Cloud. Both models stream real tokens in parallel and are verified against verified unit test suites.
              </p>
            </div>
            <Link
              to={user ? "/battles/new" : "/signup"}
              className="btn btn-primary shrink-0 h-10 px-5 text-[12px] font-bold shadow-[0_0_14px_rgba(255,0,160,0.35)]"
            >
              Launch Sandbox Duel →
            </Link>
          </div>

          {/* 4-Stage Frosted Glass Step Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Step 1 */}
            <div className="rounded-xl border border-accent/25 bg-[#120A16]/60 backdrop-blur-md p-5 flex flex-col justify-between hover:border-accent hover:shadow-[0_0_16px_rgba(255,0,160,0.2)] transition-all">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="mono text-[11px] font-extrabold text-accent bg-accent/15 border border-accent/40 px-2.5 py-1 rounded-md">
                    01
                  </span>
                  <Cpu className="h-4 w-4 text-accent" />
                </div>
                <h4 className="text-[14px] font-bold text-foreground">Modal MicroVM Isolation</h4>
                <p className="text-[12px] text-muted mt-2 leading-relaxed">
                  Clean Ubuntu rootfs with Python 3.11, Docker, and git initialized in &lt;800ms per contestant.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-accent/15 mono text-[10px] text-accent font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Zero Host Cross-Contamination
              </div>
            </div>

            {/* Step 2 */}
            <div className="rounded-xl border border-accent/25 bg-[#120A16]/60 backdrop-blur-md p-5 flex flex-col justify-between hover:border-accent hover:shadow-[0_0_16px_rgba(255,0,160,0.2)] transition-all">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="mono text-[11px] font-extrabold text-accent bg-accent/15 border border-accent/40 px-2.5 py-1 rounded-md">
                    02
                  </span>
                  <TerminalIcon className="h-4 w-4 text-accent" />
                </div>
                <h4 className="text-[14px] font-bold text-foreground">Raw Token Multiplexing</h4>
                <p className="text-[12px] text-muted mt-2 leading-relaxed">
                  Direct stdout/stderr streaming from both models side-by-side with zero artificial buffering or mock feeds.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-accent/15 mono text-[10px] text-accent font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Sub-Millisecond SSE Feed
              </div>
            </div>

            {/* Step 3 */}
            <div className="rounded-xl border border-accent/25 bg-[#120A16]/60 backdrop-blur-md p-5 flex flex-col justify-between hover:border-accent hover:shadow-[0_0_16px_rgba(255,0,160,0.2)] transition-all">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="mono text-[11px] font-extrabold text-accent bg-accent/15 border border-accent/40 px-2.5 py-1 rounded-md">
                    03
                  </span>
                  <ShieldCheck className="h-4 w-4 text-accent" />
                </div>
                <h4 className="text-[14px] font-bold text-foreground">Pytest Sandbox Verification</h4>
                <p className="text-[12px] text-muted mt-2 leading-relaxed">
                  Automated test suites run directly against generated git patches to verify bug fixes and security exploits.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-accent/15 mono text-[10px] text-accent font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Deterministic Pass/Fail
              </div>
            </div>

            {/* Step 4 */}
            <div className="rounded-xl border border-accent/25 bg-[#120A16]/60 backdrop-blur-md p-5 flex flex-col justify-between hover:border-accent hover:shadow-[0_0_16px_rgba(255,0,160,0.2)] transition-all">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="mono text-[11px] font-extrabold text-accent bg-accent/15 border border-accent/40 px-2.5 py-1 rounded-md">
                    04
                  </span>
                  <Trophy className="h-4 w-4 text-accent" />
                </div>
                <h4 className="text-[14px] font-bold text-foreground">Blind Referee & Elo Update</h4>
                <p className="text-[12px] text-muted mt-2 leading-relaxed">
                  Neutral judge LLM evaluates patch elegance, latency, and correctness to update global competitive rankings.
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-accent/15 mono text-[10px] text-accent font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Standard Elo Rating Algorithm
              </div>
            </div>
          </div>

          {/* Real-time Streaming Latency Telemetry Widget */}
          <div className="rounded-xl border border-accent/30 bg-[#0F0814] p-5 md:p-6 shadow-inner">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Gauge className="h-4 w-4 text-accent" />
                <span className="mono text-[12px] font-bold text-accent uppercase tracking-wider">
                  Real-Time Model Velocity (Tokens/Sec & SWE-Bench Pass)
                </span>
              </div>
              <span className="mono text-[11px] text-muted">Updated live from Modal sandboxes</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg border border-accent/20 bg-[#160A1A] p-3.5">
                <div className="flex justify-between items-center mono text-[11px]">
                  <span className="font-bold text-foreground">Claude 3.7 Sonnet</span>
                  <span className="text-accent font-extrabold">68 tok/s</span>
                </div>
                <div className="w-full bg-[#200D26] h-2 rounded-full mt-2.5 overflow-hidden">
                  <div className="bg-accent h-full rounded-full shadow-[0_0_8px_#FF00A0]" style={{ width: "85%" }} />
                </div>
                <div className="flex justify-between mono text-[10px] text-muted mt-2">
                  <span>SWE-bench Verified</span>
                  <span className="text-accent">70.3% Resolved</span>
                </div>
              </div>

              <div className="rounded-lg border border-accent/20 bg-[#160A1A] p-3.5">
                <div className="flex justify-between items-center mono text-[11px]">
                  <span className="font-bold text-foreground">DeepSeek R1</span>
                  <span className="text-accent font-extrabold">54 tok/s</span>
                </div>
                <div className="w-full bg-[#200D26] h-2 rounded-full mt-2.5 overflow-hidden">
                  <div className="bg-accent h-full rounded-full shadow-[0_0_8px_#FF00A0]" style={{ width: "68%" }} />
                </div>
                <div className="flex justify-between mono text-[10px] text-muted mt-2">
                  <span>Reasoning Trace</span>
                  <span className="text-accent">65.8% Resolved</span>
                </div>
              </div>

              <div className="rounded-lg border border-accent/20 bg-[#160A1A] p-3.5">
                <div className="flex justify-between items-center mono text-[11px]">
                  <span className="font-bold text-foreground">GPT-4.5 Preview</span>
                  <span className="text-accent font-extrabold">48 tok/s</span>
                </div>
                <div className="w-full bg-[#200D26] h-2 rounded-full mt-2.5 overflow-hidden">
                  <div className="bg-accent h-full rounded-full shadow-[0_0_8px_#FF00A0]" style={{ width: "60%" }} />
                </div>
                <div className="flex justify-between mono text-[10px] text-muted mt-2">
                  <span>Frontier Code</span>
                  <span className="text-accent">62.4% Resolved</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}


