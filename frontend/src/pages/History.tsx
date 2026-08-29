import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type BattleOut, type FormatOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Archive,
  ArrowRight,
  CheckCircle2,
  Clock,
  Filter,
  Layers,
  Play,
  Plus,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Swords,
  XCircle,
} from "lucide-react";

type FilterStatus = "all" | "running" | "completed" | "failed" | "saved";
type SortOption = "newest" | "oldest" | "duration";

function formatDuration(seconds?: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function formatRelativeDate(isoOrMs?: string | number): string {
  if (!isoOrMs) return "Recently";
  const date = new Date(isoOrMs);
  const diffSec = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diffSec < 60) return "Just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return date.toLocaleDateString();
}

export default function History() {
  const { user, jwt, refreshJwt } = useAuth();
  const navigate = useNavigate();

  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Filter & Search States
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("all");
  const [formatFilter, setFormatFilter] = useState<string>("all");
  const [sortOption, setSortOption] = useState<SortOption>("newest");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadArchive() {
      setLoading(true);
      setErr(null);
      try {
        const token = (await refreshJwt()) || jwt;
        const [fList, bList] = await Promise.all([
          api.formats(null).catch(() => []),
          token
            ? api.listBattles(token).catch(async () => {
                // Fallback to local session ids
                const ids = JSON.parse(
                  localStorage.getItem("arena_battle_ids") || "[]",
                ) as string[];
                const loaded: BattleOut[] = [];
                for (const id of ids.slice(0, 30)) {
                  try {
                    loaded.push(await api.getBattle(token, id));
                  } catch {}
                }
                return loaded;
              })
            : [],
        ]);

        if (cancelled) return;
        setFormats(fList);
        setBattles(Array.isArray(bList) ? bList : []);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Failed to load battle archive");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadArchive();
    return () => {
      cancelled = true;
    };
  }, [jwt, refreshJwt]);

  const filteredBattles = useMemo(() => {
    return battles
      .filter((b) => {
        // Status filter
        if (statusFilter === "running" && b.status !== "running") return false;
        if (statusFilter === "completed" && b.status !== "completed")
          return false;
        if (
          statusFilter === "failed" &&
          b.status !== "failed" &&
          b.status !== "cancelled"
        )
          return false;
        if (statusFilter === "saved" && !b.saved) return false;

        // Format filter
        if (formatFilter !== "all" && b.format_id !== formatFilter) return false;

        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchId = b.id.toLowerCase().includes(q);
          const matchFormat = b.format_id.toLowerCase().includes(q);
          const matchFighters = (b.model_ids || []).some((m) =>
            m.toLowerCase().includes(q),
          );
          if (!matchId && !matchFormat && !matchFighters) return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (sortOption === "duration") {
          return (b.timeout_seconds || 0) - (a.timeout_seconds || 0);
        }
        return 0; // Default order from API is chronological
      });
  }, [battles, statusFilter, formatFilter, sortOption, searchQuery]);

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
                <Archive className="h-3.5 w-3.5" />
                HISTORICAL RUN LOGS & VERIFIED REPLAYS
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Battle{" "}
                <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                  Archive
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-400">
                Inspect past microVM runs, trace step-by-step terminal outputs,
                examine generated test suites, and review judge scorecards.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/battles/new"
                className="btn btn-primary flex h-11 items-center gap-2 px-6 text-xs font-bold shadow-[0_0_18px_rgba(255,0,160,0.4)]"
              >
                <Plus className="h-4 w-4" />
                <span>New Battle</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* FILTER CONTROLS & SEARCH                                         */}
          {/* =============================================================== */}
          <div className="relative z-10 flex flex-col gap-4 border-b border-[#1F1F22] pb-4 lg:flex-row lg:items-center lg:justify-between">
            {/* Status Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-[#1F1F22] bg-[#050508] p-1.5">
              {(
                [
                  { id: "all", label: "All" },
                  { id: "running", label: "Running" },
                  { id: "completed", label: "Completed" },
                  { id: "failed", label: "Failed" },
                  { id: "saved", label: "Saved" },
                ] as { id: FilterStatus; label: string }[]
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setStatusFilter(tab.id)}
                  className={`mono rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                    statusFilter === tab.id
                      ? "bg-accent text-white shadow-[0_0_12px_rgba(255,0,160,0.3)]"
                      : "text-zinc-400 hover:text-white hover:bg-[#161619]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Dropdowns and Search */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Format Filter */}
              <select
                value={formatFilter}
                onChange={(e) => setFormatFilter(e.target.value)}
                className="mono h-9 rounded-xl border border-[#1F1F22] bg-[#050508] px-3 text-xs text-white focus:border-accent focus:outline-none"
              >
                <option value="all">All Formats</option>
                {formats.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>

              {/* Sort Filter */}
              <select
                value={sortOption}
                onChange={(e) => setSortOption(e.target.value as SortOption)}
                className="mono h-9 rounded-xl border border-[#1F1F22] bg-[#050508] px-3 text-xs text-white focus:border-accent focus:outline-none"
              >
                <option value="newest">Newest First</option>
                <option value="duration">By Duration</option>
              </select>

              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search battles..."
                  className="mono h-9 w-52 rounded-xl border border-[#1F1F22] bg-[#050508] pl-9 pr-3 text-xs text-white placeholder:text-zinc-600 focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* =============================================================== */}
          {/* ARCHIVE TABLE OR EMPTY STATE                                     */}
          {/* =============================================================== */}
          <div className="relative z-10">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 space-y-3">
                <RefreshCw className="h-6 w-6 animate-spin text-accent" />
                <span className="mono text-xs text-zinc-400">
                  Loading battle archive…
                </span>
              </div>
            ) : filteredBattles.length === 0 ? (
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-12 text-center space-y-4">
                <div className="grid h-12 w-12 place-items-center rounded-xl bg-accent/10 border border-accent/30 text-accent mx-auto">
                  <Archive className="h-6 w-6" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="text-base font-extrabold text-white">
                    NO ARCHIVED BATTLES FOUND
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    {searchQuery || statusFilter !== "all"
                      ? "No records matched your active filter criteria."
                      : "You haven't run or saved any battles in this workspace session yet."}
                  </p>
                </div>
                <Link
                  to="/battles/new"
                  className="btn btn-primary mx-auto inline-flex h-10 items-center gap-2 px-6 text-xs font-bold mt-2 shadow-[0_0_14px_rgba(255,0,160,0.3)]"
                >
                  <Plus className="h-4 w-4" />
                  <span>Launch New Battle</span>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-[#1F1F22] bg-[#050508]">
                <table className="w-full text-left text-xs mono">
                  <thead>
                    <tr className="border-b border-[#1F1F22] bg-[#0D0D0F] text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                      <th className="py-3.5 pl-6 pr-3 w-28">STATUS</th>
                      <th className="py-3.5 px-4">BATTLE / FORMAT</th>
                      <th className="py-3.5 px-4">FIGHTERS</th>
                      <th className="py-3.5 px-4">RESULT / VERDICT</th>
                      <th className="py-3.5 px-4">DURATION</th>
                      <th className="py-3.5 pr-6 pl-4 text-right">ACTION</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1F1F22]">
                    {filteredBattles.map((b) => {
                      const isLive = b.status === "running";
                      const isDone = b.status === "completed";
                      const isFailed =
                        b.status === "failed" || b.status === "cancelled";

                      return (
                        <tr
                          key={b.id}
                          className="transition-colors hover:bg-[#0D0D0F]"
                        >
                          {/* Status */}
                          <td className="py-4 pl-6 pr-3 font-bold">
                            {isLive && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/15 px-2.5 py-0.5 text-[10.5px] font-bold text-accent">
                                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-ping" />
                                ● LIVE
                              </span>
                            )}
                            {isDone && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-2.5 py-0.5 text-[10.5px] font-bold text-emerald-400">
                                <CheckCircle2 className="h-3 w-3" />
                                ✓ DONE
                              </span>
                            )}
                            {isFailed && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-950/40 px-2.5 py-0.5 text-[10.5px] font-bold text-red-400">
                                <XCircle className="h-3 w-3" />
                                × FAILED
                              </span>
                            )}
                            {!isLive && !isDone && !isFailed && (
                              <span className="text-zinc-500 uppercase text-[10.5px]">
                                {b.status}
                              </span>
                            )}
                          </td>

                          {/* Battle & Format */}
                          <td className="py-4 px-4">
                            <div className="font-bold text-white text-sm">
                              {b.title || b.format_id}
                            </div>
                            <div className="text-[10.5px] text-zinc-500 flex items-center gap-2 mt-0.5">
                              <span>ID: {b.id.slice(0, 12)}…</span>
                              {b.saved && (
                                <span className="text-accent font-bold">★ SAVED</span>
                              )}
                            </div>
                          </td>

                          {/* Fighters */}
                          <td className="py-4 px-4">
                            <div className="font-bold text-zinc-200">
                              {(b.model_ids || []).join("  vs  ")}
                            </div>
                            <div className="text-[10.5px] text-zinc-500">
                              Isolated MicroVM execution
                            </div>
                          </td>

                          {/* Result / Verdict */}
                          <td className="py-4 px-4">
                            {isLive && (
                              <span className="text-accent font-bold">
                                Running Phase Pipeline…
                              </span>
                            )}
                            {isDone && (
                              <span className="text-emerald-400 font-bold flex items-center gap-1.5">
                                <ShieldCheck className="h-3.5 w-3.5" />
                                Verified Result
                              </span>
                            )}
                            {isFailed && (
                              <span className="text-red-400 font-bold">
                                Execution Error / Timeout
                              </span>
                            )}
                          </td>

                          {/* Duration */}
                          <td className="py-4 px-4 text-zinc-400 text-xs">
                            <div className="flex items-center gap-1.5">
                              <Clock className="h-3 w-3 text-zinc-500" />
                              <span>{formatDuration(b.timeout_seconds)}</span>
                            </div>
                          </td>

                          {/* Action Button */}
                          <td className="py-4 pr-6 pl-4 text-right">
                            <Link
                              to={`/battles/${b.id}`}
                              className="mono inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3.5 py-1.5 text-xs font-bold text-accent transition-all hover:bg-accent/20 hover:border-accent"
                            >
                              <span>{isLive ? "View Live →" : "Replay →"}</span>
                            </Link>
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
