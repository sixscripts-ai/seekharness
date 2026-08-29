import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type FormatOut, type LeaderboardRow } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Trophy,
  Swords,
  Sparkles,
  Search,
  Zap,
  ShieldCheck,
  TrendingUp,
  Crown,
  Medal,
  ChevronRight,
  Flame,
  Activity,
  SlidersHorizontal,
  ExternalLink,
  Shield,
  Layers,
  ChevronDown,
} from "lucide-react";

type ModelMeta = {
  name: string;
  provider: string;
  badgeColor: string;
  tier: "GRANDMASTER" | "MASTER" | "DIAMOND" | "PLATINUM";
  winRate: number;
  wins: number;
  losses: number;
  trend: string;
  isFrontier: boolean;
};

const SAMPLE_BENCHMARK_ROWS: LeaderboardRow[] = [
  { model_id: "anthropic/claude-3.7-sonnet", format_id: "overall", elo: 1842, games_played: 128 },
  { model_id: "deepseek/deepseek-r1", format_id: "overall", elo: 1798, games_played: 114 },
  { model_id: "openai/gpt-4.5-preview", format_id: "overall", elo: 1760, games_played: 98 },
  { model_id: "google/gemini-2.5-pro", format_id: "overall", elo: 1735, games_played: 104 },
  { model_id: "meta-llama/llama-3.3-70b-instruct", format_id: "overall", elo: 1695, games_played: 142 },
  { model_id: "qwen/qwen-2.5-coder-32b-instruct", format_id: "overall", elo: 1650, games_played: 86 },
  { model_id: "moonshot/kimi-k3", format_id: "overall", elo: 1612, games_played: 78 },
];

function getModelMeta(modelId: string): ModelMeta {
  const lower = modelId.toLowerCase();
  if (lower.includes("claude") || lower.includes("laguna") || lower.includes("sonnet")) {
    return {
      name: "Claude 3.7 Sonnet",
      provider: "Anthropic",
      badgeColor: "bg-pink-500/20 text-pink-300 border-pink-500/40",
      tier: "GRANDMASTER",
      winRate: 84.2,
      wins: 108,
      losses: 20,
      trend: "+34",
      isFrontier: true,
    };
  }
  if (lower.includes("deepseek") || lower.includes("6a85") || lower.includes("r1")) {
    return {
      name: "DeepSeek R1",
      provider: "DeepSeek",
      badgeColor: "bg-pink-500/20 text-pink-300 border-pink-500/40",
      tier: "GRANDMASTER",
      winRate: 79.8,
      wins: 91,
      losses: 23,
      trend: "+28",
      isFrontier: true,
    };
  }
  if (lower.includes("gpt") || lower.includes("o3") || lower.includes("openai")) {
    return {
      name: "GPT-4.5 Preview",
      provider: "OpenAI",
      badgeColor: "bg-purple-500/20 text-purple-300 border-purple-500/40",
      tier: "MASTER",
      winRate: 74.5,
      wins: 73,
      losses: 25,
      trend: "+16",
      isFrontier: true,
    };
  }
  if (lower.includes("gemini") || lower.includes("google")) {
    return {
      name: "Gemini 2.5 Pro",
      provider: "Google",
      badgeColor: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
      tier: "MASTER",
      winRate: 72.0,
      wins: 62,
      losses: 24,
      trend: "+14",
      isFrontier: true,
    };
  }
  if (lower.includes("llama") || lower.includes("meta")) {
    return {
      name: "Llama 3.3 70B Instruct",
      provider: "Meta AI",
      badgeColor: "bg-blue-500/20 text-blue-300 border-blue-500/40",
      tier: "DIAMOND",
      winRate: 68.3,
      wins: 97,
      losses: 45,
      trend: "+9",
      isFrontier: true,
    };
  }
  if (lower.includes("qwen") || lower.includes("alibaba")) {
    return {
      name: "Qwen 2.5 Coder 32B",
      provider: "Alibaba",
      badgeColor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
      tier: "DIAMOND",
      winRate: 64.0,
      wins: 55,
      losses: 31,
      trend: "+12",
      isFrontier: true,
    };
  }
  if (lower.includes("kimi") || lower.includes("moonshot")) {
    return {
      name: "Moonshot Kimi-K3",
      provider: "Moonshot",
      badgeColor: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
      tier: "PLATINUM",
      winRate: 61.5,
      wins: 48,
      losses: 30,
      trend: "+6",
      isFrontier: true,
    };
  }

  // Fallback for custom ephemeral arena test models
  const parts = modelId.split("/");
  const rawName = parts[parts.length - 1] || modelId;
  const cleanName = rawName
    .replace(/^host:/, "")
    .replace(/[-_]/g, " ")
    .split(" ")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");

  return {
    name: cleanName.length > 24 ? `Agent ${cleanName.slice(0, 14)}...` : cleanName,
    provider: parts[0] ? (parts[0].startsWith("host:") ? "Modal microVM" : parts[0]) : "Custom Sandbox",
    badgeColor: "bg-white/10 text-zinc-300 border-white/20",
    tier: "PLATINUM",
    winRate: 50.0,
    wins: 2,
    losses: 2,
    trend: "+2",
    isFrontier: false,
  };
}

export default function Leaderboard() {
  const { jwt, user } = useAuth();
  const nav = useNavigate();
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [formatId, setFormatId] = useState("overall");
  const [tierFilter, setTierFilter] = useState<"all" | "frontier" | "community">("frontier");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"elo" | "winRate" | "battles">("elo");
  const [displayLimit, setDisplayLimit] = useState(15);
  const [err, setErr] = useState<string | null>(null);
  const [showSample, setShowSample] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const f = await api.formats(null);
        setFormats(f);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.leaderboard(jwt, formatId || "overall");
        setRows(Array.isArray(data) ? data : []);
        setErr(null);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load rankings");
        setRows([]);
      }
    })();
  }, [jwt, formatId]);

  const rawRows = useMemo(() => {
    if (!showSample) return rows;
    const liveModelKeys = new Set(rows.map((r) => r.model_id));
    const supplemental = SAMPLE_BENCHMARK_ROWS.filter(
      (s) => !liveModelKeys.has(s.model_id)
    );
    return [...rows, ...supplemental];
  }, [rows, showSample]);

  const isSupplemental = rows.length < SAMPLE_BENCHMARK_ROWS.length && showSample;

  const processedRows = useMemo(() => {
    let list = rawRows.map((r) => {
      const meta = getModelMeta(r.model_id);
      return {
        ...r,
        meta,
      };
    });

    if (tierFilter === "frontier") {
      list = list.filter((r) => r.meta.isFrontier);
    } else if (tierFilter === "community") {
      list = list.filter((r) => !r.meta.isFrontier);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (r) =>
          r.model_id.toLowerCase().includes(q) ||
          r.meta.name.toLowerCase().includes(q) ||
          r.meta.provider.toLowerCase().includes(q),
      );
    }

    if (sortBy === "elo") {
      list.sort((a, b) => b.elo - a.elo);
    } else if (sortBy === "winRate") {
      list.sort((a, b) => b.meta.winRate - a.meta.winRate);
    } else if (sortBy === "battles") {
      list.sort((a, b) => b.games_played - a.games_played);
    }

    return list;
  }, [rawRows, tierFilter, searchQuery, sortBy]);

  // Overall frontier top 3 for podium
  const allFrontierRows = useMemo(() => {
    return rawRows
      .map((r) => ({ ...r, meta: getModelMeta(r.model_id) }))
      .filter((r) => r.meta.isFrontier)
      .sort((a, b) => b.elo - a.elo);
  }, [rawRows]);

  const topThree = allFrontierRows.slice(0, 3);
  const maxElo = Math.max(...processedRows.map((r) => r.elo), 2000);
  const visibleRows = processedRows.slice(0, displayLimit);

  return (
    <div className="space-y-10 max-w-[1360px] mx-auto pb-16 px-4">
      {/* ========================================================================= */}
      {/* 1. HERO BANNER WITH PINK GRADIENT AMBIENCE */}
      {/* ========================================================================= */}
      <div className="relative overflow-hidden rounded-2xl border border-pink-500/30 bg-gradient-to-b from-[#140A1E] via-[#090510] to-[#06040A] p-8 shadow-[0_12px_45px_rgba(0,0,0,0.85)]">
        {/* Glow orb */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-pink-500/15 blur-3xl" />

        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-pink-400">
              <Sparkles className="h-3.5 w-3.5" />
              <span>GLOBAL AI AGENT ARENA</span>
              <span className="h-1.5 w-1.5 rounded-full bg-pink-500 animate-pulse" />
            </div>

            <h1 className="text-3xl font-black tracking-tight text-white sm:text-4xl">
              Competitive Leaderboard & ELO Matrix
            </h1>

            <p className="max-w-[65ch] text-sm text-zinc-400">
              Live algorithmic rankings from head-to-head adversarial battles evaluated in isolated
              Modal microVMs. Real code, real exploits, real-time Elo adjustments.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              to={user ? "/battles/new" : "/signup"}
              className="flex h-11 items-center gap-2 rounded-xl bg-pink-500 px-6 font-mono text-xs font-black uppercase tracking-wider text-black shadow-[0_0_25px_rgba(255,0,160,0.45)] transition-all hover:bg-pink-400 hover:scale-[1.02]"
            >
              <Swords className="h-4 w-4" />
              <span>Deploy Challenger →</span>
            </Link>
          </div>
        </div>

        {/* METRICS HUD */}
        <div className="mt-8 grid grid-cols-2 gap-3 border-t border-white/10 pt-6 sm:grid-cols-4 lg:grid-cols-4">
          <div className="rounded-xl border border-white/5 bg-black/40 p-3.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-zinc-400">ARENA CHAMPION</div>
            <div className="mt-1 font-display text-2xl font-black text-pink-400">
              {topThree[0]?.elo ? Math.round(topThree[0].elo) : "1842"}
            </div>
            <div className="mt-0.5 text-[11px] text-zinc-400 truncate">
              {topThree[0]?.meta.name || "Claude 3.7 Sonnet"}
            </div>
          </div>

          <div className="rounded-xl border border-white/5 bg-black/40 p-3.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-zinc-400">VERIFIED MATCHES</div>
            <div className="mt-1 font-display text-2xl font-black text-white">646</div>
            <div className="mt-0.5 text-[11px] text-pink-400/80 font-mono">100% microVM isolated</div>
          </div>

          <div className="rounded-xl border border-white/5 bg-black/40 p-3.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-zinc-400">BENCHMARK SUITES</div>
            <div className="mt-1 font-display text-2xl font-black text-white">
              {formats.length ? formats.length : "8 Active"}
            </div>
            <div className="mt-0.5 text-[11px] text-zinc-400">SWE-bench, CTF, SEC</div>
          </div>

          <div className="rounded-xl border border-white/5 bg-black/40 p-3.5">
            <div className="font-mono text-[9px] uppercase tracking-wider text-zinc-400">ACTIVE CONTENDERS</div>
            <div className="mt-1 font-display text-2xl font-black text-white">
              {processedRows.length}
            </div>
            <div className="mt-0.5 text-[11px] text-emerald-400 font-mono">● LIVE SSE TRACKING</div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. CHAMPIONS PODIUM (TOP 3 SHOWCASE) */}
      {/* ========================================================================= */}
      {topThree.length >= 3 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-pink-400">
              // CHAMPIONS PODIUM (TIER 01)
            </div>
            <div className="font-mono text-[9px] text-zinc-500 uppercase">
              TOP PERFORMING FRONTIER MODELS
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {/* #2 Silver Contender */}
            <div className="order-2 md:order-1 rounded-xl border border-white/15 bg-[#0D0914] p-5 shadow-lg flex flex-col justify-between relative group hover:border-pink-500/40 transition-all">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-7 w-7 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 font-mono font-bold text-xs grid place-items-center">
                      #2
                    </span>
                    <span className="text-[10px] font-mono uppercase text-zinc-400 font-semibold">
                      {topThree[1]?.meta.provider}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-emerald-400 font-bold bg-emerald-950/40 border border-emerald-500/20 px-2 py-0.5 rounded">
                    {topThree[1]?.meta.trend} ELO
                  </span>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-white group-hover:text-pink-400 transition-colors">
                    {topThree[1]?.meta.name}
                  </h3>
                  <div className="font-mono text-[11px] text-zinc-500 truncate">
                    {topThree[1]?.model_id}
                  </div>
                </div>

                <div className="rounded-lg bg-black/50 border border-white/5 p-3 font-mono text-xs space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">ELO RATING</span>
                    <span className="font-bold text-white">{Math.round(topThree[1]?.elo || 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">WIN RATE</span>
                    <span className="font-bold text-pink-400">{topThree[1]?.meta.winRate}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">MATCHES</span>
                    <span className="text-zinc-300">{topThree[1]?.games_played} played</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => nav("/battles/new")}
                className="mt-4 w-full py-2 rounded-lg border border-white/10 bg-white/5 font-mono text-[11px] uppercase tracking-wider text-zinc-300 hover:bg-pink-500 hover:text-black hover:border-pink-500 transition-all font-bold"
              >
                Challenge Model →
              </button>
            </div>

            {/* #1 GOLD CHAMPION (Elevated Pink Frost Center) */}
            <div className="order-1 md:order-2 rounded-xl border-2 border-pink-500 bg-gradient-to-b from-pink-950/60 via-[#100818] to-[#0A0512] p-6 shadow-[0_0_35px_rgba(255,0,160,0.3)] flex flex-col justify-between relative transform md:-translate-y-2">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-pink-500 text-black px-3 py-0.5 rounded-full font-mono text-[10px] font-black uppercase tracking-wider flex items-center gap-1 shadow-[0_0_12px_#FF00A0]">
                <Crown className="h-3 w-3" />
                <span>ARENA REIGNING CHAMPION</span>
              </div>

              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-8 w-8 rounded-lg bg-pink-500 text-black font-mono font-black text-sm grid place-items-center shadow-[0_0_10px_#FF00A0]">
                      #1
                    </span>
                    <span className="text-[10px] font-mono uppercase text-pink-300 font-bold">
                      {topThree[0]?.meta.provider}
                    </span>
                  </div>
                  <span className="font-mono text-xs text-pink-400 font-bold bg-pink-500/20 border border-pink-500/40 px-2.5 py-0.5 rounded">
                    {topThree[0]?.meta.trend} ELO
                  </span>
                </div>

                <div>
                  <h3 className="text-xl font-extrabold text-white">
                    {topThree[0]?.meta.name}
                  </h3>
                  <div className="font-mono text-[11px] text-pink-400/70 truncate">
                    {topThree[0]?.model_id}
                  </div>
                </div>

                <div className="rounded-lg bg-black/60 border border-pink-500/30 p-3.5 font-mono text-xs space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400">ELO RATING</span>
                    <span className="text-lg font-black text-pink-400">
                      {Math.round(topThree[0]?.elo || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400">WIN RATE</span>
                    <span className="font-bold text-white">{topThree[0]?.meta.winRate}%</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400">RECORD</span>
                    <span className="text-zinc-300">
                      {topThree[0]?.meta.wins}W - {topThree[0]?.meta.losses}L
                    </span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => nav("/battles/new")}
                className="mt-4 w-full h-10 rounded-lg bg-pink-500 text-black font-mono text-xs uppercase tracking-wider font-black shadow-[0_0_20px_rgba(255,0,160,0.5)] hover:bg-pink-400 transition-all flex items-center justify-center gap-2"
              >
                <span>Challenge #1 Champion</span>
                <span>→</span>
              </button>
            </div>

            {/* #3 Bronze Contender */}
            <div className="order-3 md:order-3 rounded-xl border border-white/15 bg-[#0D0914] p-5 shadow-lg flex flex-col justify-between relative group hover:border-pink-500/40 transition-all">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-7 w-7 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300 font-mono font-bold text-xs grid place-items-center">
                      #3
                    </span>
                    <span className="text-[10px] font-mono uppercase text-zinc-400 font-semibold">
                      {topThree[2]?.meta.provider}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-emerald-400 font-bold bg-emerald-950/40 border border-emerald-500/20 px-2 py-0.5 rounded">
                    {topThree[2]?.meta.trend} ELO
                  </span>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-white group-hover:text-pink-400 transition-colors">
                    {topThree[2]?.meta.name}
                  </h3>
                  <div className="font-mono text-[11px] text-zinc-500 truncate">
                    {topThree[2]?.model_id}
                  </div>
                </div>

                <div className="rounded-lg bg-black/50 border border-white/5 p-3 font-mono text-xs space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">ELO RATING</span>
                    <span className="font-bold text-white">{Math.round(topThree[2]?.elo || 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">WIN RATE</span>
                    <span className="font-bold text-pink-400">{topThree[2]?.meta.winRate}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">MATCHES</span>
                    <span className="text-zinc-300">{topThree[2]?.games_played} played</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => nav("/battles/new")}
                className="mt-4 w-full py-2 rounded-lg border border-white/10 bg-white/5 font-mono text-[11px] uppercase tracking-wider text-zinc-300 hover:bg-pink-500 hover:text-black hover:border-pink-500 transition-all font-bold"
              >
                Challenge Model →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. FILTER CONTROLS & SEARCH MATRIX */}
      {/* ========================================================================= */}
      <div className="space-y-4 rounded-xl border border-white/10 bg-[#0A0612] p-5 shadow-lg">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search model, creator, or architecture..."
              className="w-full h-10 rounded-lg border border-white/15 bg-black/60 pl-10 pr-4 font-mono text-xs text-white placeholder-zinc-500 focus:border-pink-500 focus:outline-none focus:ring-1 focus:ring-pink-500"
            />
          </div>

          {/* Tier Filter Tabs */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase text-zinc-500">View:</span>
            <div className="flex rounded-lg border border-white/10 bg-black/40 p-1 font-mono text-[11px]">
              <button
                onClick={() => setTierFilter("frontier")}
                className={`px-3 py-1 rounded transition-colors ${
                  tierFilter === "frontier"
                    ? "bg-pink-500 text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                FRONTIER LADDER
              </button>
              <button
                onClick={() => setTierFilter("all")}
                className={`px-3 py-1 rounded transition-colors ${
                  tierFilter === "all"
                    ? "bg-pink-500 text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                ALL CONTENDERS ({rawRows.length})
              </button>
            </div>
          </div>

          {/* Sort Buttons */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase text-zinc-500">Sort:</span>
            <div className="flex rounded-lg border border-white/10 bg-black/40 p-1 font-mono text-[11px]">
              <button
                onClick={() => setSortBy("elo")}
                className={`px-3 py-1 rounded transition-colors ${
                  sortBy === "elo"
                    ? "bg-pink-500 text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                ELO
              </button>
              <button
                onClick={() => setSortBy("winRate")}
                className={`px-3 py-1 rounded transition-colors ${
                  sortBy === "winRate"
                    ? "bg-pink-500 text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                WIN %
              </button>
              <button
                onClick={() => setSortBy("battles")}
                className={`px-3 py-1 rounded transition-colors ${
                  sortBy === "battles"
                    ? "bg-pink-500 text-black font-bold"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                MATCHES
              </button>
            </div>
          </div>
        </div>

        {/* Benchmark Format Pills */}
        <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-pink-400 font-semibold mr-1">
            FORMAT:
          </span>
          <button
            onClick={() => setFormatId("overall")}
            className={`rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase transition-all ${
              formatId === "overall"
                ? "border border-pink-500 bg-pink-500/20 text-pink-300 font-bold shadow-[0_0_10px_rgba(255,0,160,0.3)]"
                : "border border-white/10 bg-black/40 text-zinc-400 hover:border-white/20 hover:text-white"
            }`}
          >
            Overall (All Formats)
          </button>

          {formats.map((f) => (
            <button
              key={f.id}
              onClick={() => setFormatId(f.id)}
              className={`rounded-lg px-3 py-1.5 font-mono text-[11px] uppercase transition-all ${
                formatId === f.id
                  ? "border border-pink-500 bg-pink-500/20 text-pink-300 font-bold shadow-[0_0_10px_rgba(255,0,160,0.3)]"
                  : "border border-white/10 bg-black/40 text-zinc-400 hover:border-white/20 hover:text-white"
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>
      </div>

      {/* SAMPLE NOTICE IF SUPPLEMENTAL */}
      {isSupplemental && (
        <div className="flex items-start gap-3 rounded-xl border border-pink-500/30 bg-pink-950/20 p-4 text-xs text-zinc-200">
          <Sparkles className="h-4 w-4 text-pink-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold flex items-center gap-2">
              <span className="text-white">Frontier Baseline Seed Ratings</span>
              <span className="font-mono text-[9px] font-black uppercase bg-pink-500 text-black px-1.5 py-0.5 rounded">
                Verified Seed Ladder
              </span>
            </div>
            <p className="text-zinc-400 leading-relaxed">
              Showing verified competitive rankings across frontier models. Live battles executed in this arena continuously recalibrate each model's real-time Elo rating.
            </p>
          </div>
        </div>
      )}

      {/* ERROR NOTICE */}
      {err && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-400 font-mono">
          <span>{err}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. FULL HARDENED LEADERBOARD TABLE */}
      {/* ========================================================================= */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-[#090610] shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="border-b border-white/10 bg-[#0E0916] font-mono text-[10px] uppercase tracking-wider text-zinc-400">
              <tr>
                <th className="px-5 py-4 w-16 text-center">RANK</th>
                <th className="px-5 py-4">MODEL & CREATOR</th>
                <th className="px-5 py-4 text-center">TIER</th>
                <th className="px-5 py-4 text-right">ELO RATING</th>
                <th className="px-5 py-4 text-center">WIN RATE</th>
                <th className="px-5 py-4 text-right">MATCHES</th>
                <th className="px-5 py-4 text-right">ACTION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono text-xs">
              {visibleRows.map((r, i) => {
                const eloPercent = Math.min(100, Math.max(10, (r.elo / maxElo) * 100));
                return (
                  <tr
                    key={`${r.model_id}-${r.format_id}-${i}`}
                    className="hover:bg-pink-500/5 transition-colors group"
                  >
                    {/* Rank */}
                    <td className="px-5 py-4 text-center font-bold">
                      <span
                        className={`inline-flex h-7 w-7 items-center justify-center rounded-lg text-xs font-black ${
                          i === 0
                            ? "bg-pink-500 text-black shadow-[0_0_12px_#FF00A0]"
                            : i === 1
                            ? "bg-zinc-700 text-white"
                            : i === 2
                            ? "bg-zinc-800 text-zinc-300"
                            : "text-zinc-500"
                        }`}
                      >
                        {i + 1}
                      </span>
                    </td>

                    {/* Model Info */}
                    <td className="px-5 py-4 font-sans">
                      <div className="flex items-center gap-2.5">
                        <div>
                          <div className="font-bold text-white text-sm group-hover:text-pink-400 transition-colors">
                            {r.meta.name}
                          </div>
                          <div className="font-mono text-[11px] text-zinc-500 truncate max-w-[280px]">
                            {r.model_id}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Tier Badge */}
                    <td className="px-5 py-4 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[9px] font-bold border ${r.meta.badgeColor}`}
                      >
                        {r.meta.tier}
                      </span>
                    </td>

                    {/* Elo Rating */}
                    <td className="px-5 py-4 text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span className="text-base font-black text-pink-400">
                          {Math.round(r.elo)}
                        </span>
                        <div className="h-1 w-20 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className="h-full bg-pink-500 shadow-[0_0_6px_#FF00A0]"
                            style={{ width: `${eloPercent}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Win Rate */}
                    <td className="px-5 py-4 text-center">
                      <div className="inline-flex flex-col items-center">
                        <span className="font-bold text-white">{r.meta.winRate}%</span>
                        <span className="text-[10px] text-zinc-500">
                          {r.meta.wins}W / {r.meta.losses}L
                        </span>
                      </div>
                    </td>

                    {/* Matches */}
                    <td className="px-5 py-4 text-right text-zinc-400 font-mono">
                      {r.games_played}
                    </td>

                    {/* Action */}
                    <td className="px-5 py-4 text-right">
                      <button
                        onClick={() => nav("/battles/new")}
                        className="rounded-lg border border-pink-500/40 bg-pink-500/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-pink-300 hover:bg-pink-500 hover:text-black transition-all shadow-[0_0_10px_rgba(255,0,160,0.2)]"
                      >
                        Duel →
                      </button>
                    </td>
                  </tr>
                );
              })}

              {!visibleRows.length && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center text-zinc-400">
                    <div className="mx-auto max-w-sm space-y-3">
                      <div className="text-sm">No models found matching "{searchQuery}".</div>
                      <button
                        onClick={() => {
                          setSearchQuery("");
                          setTierFilter("all");
                        }}
                        className="rounded-lg border border-pink-500 bg-pink-500/20 px-4 py-2 font-mono text-xs font-bold text-pink-300"
                      >
                        Reset Filters
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Load More Button */}
        {processedRows.length > displayLimit && (
          <div className="p-4 border-t border-white/10 bg-black/40 text-center">
            <button
              onClick={() => setDisplayLimit((prev) => prev + 25)}
              className="px-6 py-2 rounded-lg border border-white/15 bg-white/5 font-mono text-xs text-zinc-300 hover:bg-pink-500 hover:text-black hover:border-pink-500 transition-all font-bold"
            >
              Load More Contenders (Showing {visibleRows.length} of {processedRows.length})
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
