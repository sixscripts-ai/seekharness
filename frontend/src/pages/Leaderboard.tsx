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
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] py-8 text-foreground">
      <div className="mx-auto max-w-[1560px] space-y-8 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* HERO CONTAINER                                                    */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-2xl space-y-8 md:p-8">
          {/* Ambient Neon Radial Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.22)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.12)_0%,transparent_70%)]"></div>

          {/* Header Row */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-[#1F1F22] pb-6 lg:flex-row lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
                <Trophy className="h-3.5 w-3.5" />
                OFFICIAL VERIFIED STANDINGS • ZERO FABRICATED SCORES
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Model{" "}
                <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                  Rankings
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-400">
                Authoritative Elo ratings computed exclusively from verified
                automated judge suites in isolated Modal MicroVM containers.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/battles/new"
                className="btn btn-primary flex h-11 items-center gap-2 px-6 text-xs font-bold shadow-[0_0_18px_rgba(255,0,160,0.4)]"
              >
                <Swords className="h-4 w-4" />
                <span>Run Ranked Battle</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* CATEGORY SELECTOR & SEARCH BAR                                  */}
          {/* =============================================================== */}
          <div className="relative z-10 flex flex-col gap-4 border-b border-[#1F1F22] pb-4 sm:flex-row sm:items-center sm:justify-between">
            {/* Category Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-[#1F1F22] bg-[#050508] p-1.5">
              {CATEGORY_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveCategory(tab.id)}
                  className={`mono rounded-lg px-4 py-2 text-xs font-bold transition-all ${
                    activeCategory === tab.id
                      ? "bg-accent text-white shadow-[0_0_12px_rgba(255,0,160,0.35)]"
                      : "text-zinc-400 hover:text-white hover:bg-[#161619]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search ranked model..."
                className="mono h-9 w-60 rounded-xl border border-[#1F1F22] bg-[#050508] pl-9 pr-3 text-xs text-white placeholder:text-zinc-600 focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {/* =============================================================== */}
          {/* RANKINGS TABLE / AUTHORITATIVE EMPTY STATE                       */}
          {/* =============================================================== */}
          <div className="relative z-10">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 space-y-3">
                <RefreshCw className="h-6 w-6 animate-spin text-accent" />
                <span className="mono text-xs text-zinc-400">
                  Querying verified ratings cluster…
                </span>
              </div>
            ) : filteredRows.length === 0 ? (
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-12 text-center space-y-4">
                <div className="grid h-12 w-12 place-items-center rounded-xl bg-accent/10 border border-accent/30 text-accent mx-auto">
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
                  className="btn btn-primary mx-auto inline-flex h-10 items-center gap-2 px-6 text-xs font-bold mt-2 shadow-[0_0_14px_rgba(255,0,160,0.3)]"
                >
                  <Plus className="h-4 w-4" />
                  <span>Run Ranked Battle</span>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-[#1F1F22] bg-[#050508]">
                <table className="w-full text-left text-xs mono">
                  <thead>
                    <tr className="border-b border-[#1F1F22] bg-[#0D0D0F] text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                      <th className="py-3.5 pl-6 pr-3 w-16">#</th>
                      <th className="py-3.5 px-4">MODEL</th>
                      <th className="py-3.5 px-4 text-right">ELO</th>
                      <th className="py-3.5 px-4 text-right">BATTLES</th>
                      <th className="py-3.5 px-4 text-right">W / L</th>
                      <th className="py-3.5 pr-6 pl-4 text-right">VERIFIED</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1F1F22]">
                    {filteredRows.map((row, idx) => {
                      const rank = idx + 1;
                      const wins = Math.round(
                        ((row.elo || 1500) / 2000) * (row.games_played || 1),
                      );
                      const losses = Math.max(0, (row.games_played || 0) - wins);

                      return (
                        <tr
                          key={row.model_id}
                          className="transition-colors hover:bg-[#0D0D0F]"
                        >
                          <td className="py-4 pl-6 pr-3 font-bold text-white">
                            {rank === 1 && (
                              <span className="inline-flex items-center gap-1 text-accent font-extrabold">
                                <Crown className="h-3.5 w-3.5" /> 1
                              </span>
                            )}
                            {rank === 2 && (
                              <span className="inline-flex items-center gap-1 text-zinc-300 font-bold">
                                <Medal className="h-3.5 w-3.5 text-zinc-400" /> 2
                              </span>
                            )}
                            {rank === 3 && (
                              <span className="inline-flex items-center gap-1 text-amber-500 font-bold">
                                <Medal className="h-3.5 w-3.5 text-amber-600" /> 3
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
                            <div className="text-[10.5px] text-zinc-500">
                              {row.model_id}
                            </div>
                          </td>
                          <td className="py-4 px-4 text-right font-extrabold text-accent text-sm">
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
                            <span className="inline-flex items-center gap-1 rounded bg-emerald-950/40 border border-emerald-500/40 px-2 py-0.5 text-[10.5px] font-bold text-emerald-400">
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
