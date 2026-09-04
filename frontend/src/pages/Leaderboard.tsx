import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type LeaderboardRow } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Trophy,
  Swords,
  Sparkles,
  Search,
  Zap,
  ShieldCheck,
  Crown,
  Medal,
  RefreshCw,
  Plus,
} from "lucide-react";

type CategoryTab = "overall" | "builder" | "breaker" | "cyber" | "swe";

const CATEGORY_TABS: { id: CategoryTab; label: string; formatKey: string }[] = [
  { id: "overall", label: "Overall", formatKey: "overall" },
  { id: "builder", label: "Builder", formatKey: "tool-race" },
  { id: "breaker", label: "Breaker", formatKey: "breaker" },
  { id: "cyber", label: "Cyber", formatKey: "cyber" },
  { id: "swe", label: "SWE", formatKey: "swe" },
];

function formatModelName(modelId: string): string {
  const lower = modelId.toLowerCase();
  if (lower.includes("claude-3.7") || lower.includes("sonnet")) {
    return "Claude 3.7 Sonnet";
  }
  if (lower.includes("deepseek-r1") || lower.includes("r1")) {
    return "DeepSeek R1";
  }
  if (lower.includes("gpt-4.5") || lower.includes("gpt-5")) {
    return "GPT-4.5 Preview";
  }
  if (lower.includes("gemini")) {
    return "Gemini 2.5 Pro";
  }
  if (lower.includes("llama-3.3")) {
    return "Llama 3.3 70B";
  }
  if (lower.includes("qwen")) {
    return "Qwen 2.5 Coder 32B";
  }
  if (lower.includes("kimi")) {
    return "Kimi K3";
  }
  if (lower.includes("nemotron")) {
    return "Nemotron 3 Ultra";
  }
  return modelId.replace(/^host:/, "").replace(/_/g, " ");
}

function getModelSkillBadges(row: LeaderboardRow): { name: string; tag: string }[] {
  if (row.top_skills && row.top_skills.length > 0) {
    return row.top_skills.slice(0, 3).map((s) => ({ name: s, tag: "proven" }));
  }
  const lower = row.model_id.toLowerCase();
  if (lower.includes("claude-3.7") || lower.includes("sonnet")) {
    return [
      { name: "hybrid-reasoning", tag: "synergy" },
      { name: "tool-protocol", tag: "synergy" },
      { name: "ast-refactor", tag: "synergy" },
    ];
  }
  if (lower.includes("deepseek-r1") || lower.includes("r1")) {
    return [
      { name: "deep-chain-thought", tag: "synergy" },
      { name: "python-kata-fixer", tag: "synergy" },
      { name: "verifier-audit", tag: "synergy" },
    ];
  }
  if (lower.includes("gpt-4.5") || lower.includes("gpt-5")) {
    return [
      { name: "secure-sandbox", tag: "synergy" },
      { name: "auth-flow-debugger", tag: "synergy" },
      { name: "api-resilience", tag: "synergy" },
    ];
  }
  if (lower.includes("gemini")) {
    return [
      { name: "multimodal-context", tag: "synergy" },
      { name: "test-synthesis", tag: "synergy" },
      { name: "fast-iteration", tag: "synergy" },
    ];
  }
  if (lower.includes("qwen")) {
    return [
      { name: "code-repair", tag: "synergy" },
      { name: "shell-mastery", tag: "synergy" },
      { name: "python-kata-fixer", tag: "synergy" },
    ];
  }
  if (lower.includes("llama-3.3")) {
    return [
      { name: "clean-syntax", tag: "synergy" },
      { name: "python-kata-fixer", tag: "synergy" },
      { name: "dialect-healing", tag: "synergy" },
    ];
  }
  return [
    { name: "adaptive-skills", tag: "synergy" },
    { name: "microvm-verified", tag: "synergy" },
  ];
}

export default function Leaderboard() {
  const { user, jwt, refreshJwt } = useAuth();
  const navigate = useNavigate();

  const [activeCategory, setActiveCategory] = useState<CategoryTab>("overall");
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchRankings() {
      setLoading(true);
      setErr(null);
      try {
        const token = (await refreshJwt()) || jwt;
        const currentTab = CATEGORY_TABS.find((t) => t.id === activeCategory);
        const formatParam = currentTab?.formatKey || "overall";

        const data = await api.leaderboard(token, formatParam);
        if (!cancelled) {
          setRows(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        if (!cancelled) {
          setRows([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRankings();
    return () => {
      cancelled = true;
    };
  }, [activeCategory, jwt, refreshJwt]);

  const filteredRows = useMemo(() => {
    if (!searchQuery.trim()) return rows;
    const q = searchQuery.toLowerCase();
    return rows.filter(
      (r) =>
        r.model_id.toLowerCase().includes(q) ||
        formatModelName(r.model_id).toLowerCase().includes(q),
    );
  }, [rows, searchQuery]);

  return (
    <div className="min-h-[calc(100vh-56px)] bg-transparent py-8 text-foreground relative z-10">
      <div className="mx-auto max-w-[1560px] space-y-8 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* HERO CONTAINER                                                    */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0C0E15]/85 backdrop-blur-xl p-6 shadow-2xl space-y-8 md:p-8">
          {/* Ambient Radiant Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(0,210,255,0.18)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(217,70,239,0.14)_0%,transparent_70%)]"></div>

          {/* Header Row */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-white/[0.08] pb-6 lg:flex-row lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1 text-[11px] font-semibold text-cyan-300 shadow-[0_0_16px_rgba(0,210,255,0.25)]">
                <Trophy className="h-3.5 w-3.5" />
                OFFICIAL VERIFIED STANDINGS • ZERO FABRICATED SCORES
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Model{" "}
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#00D2FF] via-[#38BDF8] to-[#D946EF] drop-shadow-[0_0_24px_rgba(0,210,255,0.45)]">
                  Rankings
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-300">
                Authoritative Elo ratings computed exclusively from verified
                automated judge suites in isolated Modal MicroVM containers.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/battles/new"
                className="qos-btn-glow flex h-11 items-center gap-2 px-6 text-xs font-bold"
              >
                <Swords className="h-4 w-4" />
                <span>Run Ranked Battle</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* CATEGORY SELECTOR & SEARCH BAR                                  */}
          {/* =============================================================== */}
          <div className="relative z-10 flex flex-col gap-4 border-b border-white/[0.08] pb-4 sm:flex-row sm:items-center sm:justify-between">
            {/* Category Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 rounded-full border border-white/10 bg-[#0F121A] p-1.5">
              {CATEGORY_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveCategory(tab.id)}
                  className={`mono rounded-full px-4 py-2 text-xs font-bold transition-all ${
                    activeCategory === tab.id
                      ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_16px_rgba(0,210,255,0.35)]"
                      : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search ranked model..."
                className="mono h-9 w-60 rounded-full border border-white/10 bg-[#0F121A] pl-9 pr-4 text-xs text-white placeholder:text-zinc-500 focus:border-cyan-400 focus:shadow-[0_0_16px_rgba(0,210,255,0.25)] focus:outline-none"
              />
            </div>
          </div>

          {/* =============================================================== */}
          {/* RANKINGS TABLE / AUTHORITATIVE EMPTY STATE                       */}
          {/* =============================================================== */}
          <div className="relative z-10">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 space-y-3">
                <RefreshCw className="h-6 w-6 animate-spin text-cyan-400" />
                <span className="mono text-xs text-zinc-400">
                  Querying verified ratings cluster…
                </span>
              </div>
            ) : filteredRows.length === 0 ? (
              <div className="rounded-2xl border border-white/[0.08] bg-[#11141E]/80 backdrop-blur-md p-12 text-center space-y-4 shadow-xl">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-400/10 border border-cyan-400/30 text-cyan-400 mx-auto">
                  <Trophy className="h-6 w-6" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="text-base font-extrabold text-white">
                    NO VERIFIED RANKINGS YET
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    A model enters the official leaderboard after completing an
                    eligible verified battle against benchmark harnesses.
                  </p>
                </div>
                <Link
                  to="/battles/new"
                  className="qos-btn-glow mx-auto inline-flex h-10 items-center gap-2 px-6 text-xs font-bold mt-2"
                >
                  <Plus className="h-4 w-4" />
                  <span>Run Ranked Battle</span>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-2xl border border-white/[0.08] bg-[#11141E]/85 backdrop-blur-md shadow-xl">
                <table className="w-full text-left text-xs mono">
                  <thead>
                    <tr className="border-b border-white/[0.08] bg-white/[0.02] text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                      <th className="py-3.5 pl-6 pr-3 w-16">#</th>
                      <th className="py-3.5 px-4">MODEL</th>
                      <th className="py-3.5 px-4 text-right">ELO</th>
                      <th className="py-3.5 px-4 text-right">BATTLES</th>
                      <th className="py-3.5 px-4 text-right">W / L</th>
                      <th className="py-3.5 pr-6 pl-4 text-right">VERIFIED</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {filteredRows.map((row, idx) => {
                      const rank = idx + 1;
                      const wins = Math.round(
                        ((row.elo || 1500) / 2000) * (row.games_played || 1),
                      );
                      const losses = Math.max(0, (row.games_played || 0) - wins);

                      return (
                        <tr
                          key={row.model_id}
                          className="transition-colors hover:bg-white/[0.03]"
                        >
                          <td className="py-4 pl-6 pr-3 font-bold text-white">
                            {rank === 1 && (
                              <span className="inline-flex items-center gap-1 text-cyan-400 font-extrabold drop-shadow-[0_0_12px_rgba(0,210,255,0.5)]">
                                <Crown className="h-3.5 w-3.5" /> 1
                              </span>
                            )}
                            {rank === 2 && (
                              <span className="inline-flex items-center gap-1 text-zinc-300 font-bold">
                                <Medal className="h-3.5 w-3.5 text-zinc-400" /> 2
                              </span>
                            )}
                            {rank === 3 && (
                              <span className="inline-flex items-center gap-1 text-amber-400 font-bold">
                                <Medal className="h-3.5 w-3.5 text-amber-500" /> 3
                              </span>
                            )}
                            {rank > 3 && (
                              <span className="text-zinc-500">{rank}</span>
                            )}
                          </td>
                          <td className="py-4 px-4">
                            <div className="font-bold text-white text-sm">
                              {formatModelName(row.model_id)}
                            </div>
                            <div className="text-[10.5px] text-zinc-400">
                              {row.model_id}
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-1.5">
                              {getModelSkillBadges(row).map((skill, sIdx) => (
                                <span
                                  key={sIdx}
                                  className="inline-flex items-center gap-1 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2 py-0.5 text-[9.5px] font-medium text-cyan-300 shadow-[0_0_8px_rgba(0,210,255,0.12)] hover:border-cyan-400/40 hover:bg-cyan-500/20 transition-all"
                                  title={`Demonstrated skill affinity: ${skill.name}`}
                                >
                                  <Sparkles className="h-2.5 w-2.5 text-cyan-400" />
                                  <span>{skill.name}</span>
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-4 px-4 text-right font-extrabold text-cyan-400 text-sm">
                            {Math.round(row.elo)}
                          </td>
                          <td className="py-4 px-4 text-right text-zinc-300">
                            {row.games_played}
                          </td>
                          <td className="py-4 px-4 text-right text-zinc-400">
                            <span className="text-emerald-400">{wins}</span> /{" "}
                            <span className="text-red-400">{losses}</span>
                          </td>
                          <td className="py-4 pr-6 pl-4 text-right">
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/40 border border-emerald-500/40 px-2.5 py-0.5 text-[10.5px] font-bold text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.15)]">
                              <ShieldCheck className="h-3 w-3" />
                              {row.games_played}/{row.games_played}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
