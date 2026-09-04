import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type BattleOut, type FormatOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Archive,
  CheckCircle2,
  Clock,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";

type FilterStatus = "all" | "targets" | "running" | "completed" | "failed" | "saved";
type SortOption = "newest" | "oldest" | "duration";

function formatDuration(seconds?: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

export default function History() {
  const { jwt, refreshJwt } = useAuth();

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
                  } catch (e) {
                    console.debug("Failed to load battle fallback:", e);
                  }
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
        if (statusFilter === "targets" && !b.target_id) return false;
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
          const matchTarget = Boolean(b.target_id && b.target_id.toLowerCase().includes(q));
          const matchFighters = (b.model_ids || []).some((m) =>
            m.toLowerCase().includes(q),
          );
          if (!matchId && !matchFormat && !matchFighters && !matchTarget) return false;
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
          {err && (
            <div className="relative z-10 flex items-center justify-between rounded-xl border border-red-500/30 bg-red-950/20 px-4 py-3 text-xs text-red-400">
              <div className="flex items-center gap-2">
                <XCircle className="h-4 w-4 shrink-0" />
                <span>{err}</span>
              </div>
              <button
                type="button"
                onClick={() => setErr(null)}
                className="text-zinc-500 hover:text-white"
              >
                Dismiss
              </button>
            </div>
          )}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-white/[0.08] pb-6 lg:flex-row lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1 text-[11px] font-semibold text-cyan-300 shadow-[0_0_16px_rgba(0,210,255,0.25)]">
                <Archive className="h-3.5 w-3.5" />
                HISTORICAL RUN LOGS & VERIFIED REPLAYS
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Battle{" "}
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#00D2FF] via-[#38BDF8] to-[#D946EF] drop-shadow-[0_0_24px_rgba(0,210,255,0.45)]">
                  Archive
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-300">
                Inspect past microVM runs, trace step-by-step terminal outputs,
                examine generated test suites, and review judge scorecards.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/battles/new"
                className="qos-btn-glow flex h-11 items-center gap-2 px-6 text-xs font-bold"
              >
                <Plus className="h-4 w-4" />
                <span>New Battle</span>
              </Link>
            </div>
          </div>

          {/* =============================================================== */}
          {/* FILTER CONTROLS & SEARCH                                         */}
          {/* =============================================================== */}
          <div className="relative z-10 flex flex-col gap-4 border-b border-white/[0.08] pb-4 lg:flex-row lg:items-center lg:justify-between">
            {/* Status Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 rounded-full border border-white/10 bg-[#0F121A] p-1.5">
              {(
                [
                  { id: "all", label: "All" },
                  { id: "targets", label: "Targets" },
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
                  className={`mono rounded-full px-3.5 py-1.5 text-xs font-bold transition-all ${
                    statusFilter === tab.id
                      ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_16px_rgba(0,210,255,0.35)]"
                      : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
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
                className="mono h-9 rounded-full border border-white/10 bg-[#0F121A] px-4 text-xs text-white focus:border-cyan-400 focus:outline-none"
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
                className="mono h-9 rounded-full border border-white/10 bg-[#0F121A] px-4 text-xs text-white focus:border-cyan-400 focus:outline-none"
              >
                <option value="newest">Newest First</option>
                <option value="duration">By Duration</option>
              </select>

              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search battles..."
                  className="mono h-9 w-52 rounded-full border border-white/10 bg-[#0F121A] pl-9 pr-4 text-xs text-white placeholder:text-zinc-500 focus:border-cyan-400 focus:shadow-[0_0_16px_rgba(0,210,255,0.25)] focus:outline-none"
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
                <RefreshCw className="h-6 w-6 animate-spin text-cyan-400" />
                <span className="mono text-xs text-zinc-400">
                  Loading battle archive…
                </span>
              </div>
            ) : filteredBattles.length === 0 ? (
              <div className="rounded-2xl border border-white/[0.08] bg-[#11141E]/80 backdrop-blur-md p-12 text-center space-y-4 shadow-xl">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-400/10 border border-cyan-400/30 text-cyan-400 mx-auto">
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
                  className="qos-btn-glow mx-auto inline-flex h-10 items-center gap-2 px-6 text-xs font-bold mt-2"
                >
                  <Plus className="h-4 w-4" />
                  <span>Launch New Battle</span>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-2xl border border-white/[0.08] bg-[#11141E]/85 backdrop-blur-md shadow-xl">
                <table className="w-full text-left text-xs mono">
                  <thead>
                    <tr className="border-b border-white/[0.08] bg-white/[0.02] text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                      <th className="py-3.5 pl-6 pr-3 w-28">STATUS</th>
                      <th className="py-3.5 px-4">BATTLE / FORMAT</th>
                      <th className="py-3.5 px-4">FIGHTERS</th>
                      <th className="py-3.5 px-4">RESULT / VERDICT</th>
                      <th className="py-3.5 px-4">DURATION</th>
                      <th className="py-3.5 pr-6 pl-4 text-right">ACTION</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {filteredBattles.map((b) => {
                      const isLive = b.status === "running";
                      const isDone = b.status === "completed";
                      const isFailed =
                        b.status === "failed" || b.status === "cancelled";

                      return (
                        <tr
                          key={b.id}
                          className="transition-colors hover:bg-white/[0.03]"
                        >
                          {/* Status */}
                          <td className="py-4 pl-6 pr-3 font-bold">
                            {isLive && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-400/15 px-2.5 py-0.5 text-[10.5px] font-bold text-cyan-300 shadow-[0_0_12px_rgba(0,210,255,0.25)]">
                                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                                ● LIVE
                              </span>
                            )}
                            {isDone && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-950/40 px-2.5 py-0.5 text-[10.5px] font-bold text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.15)]">
                                <CheckCircle2 className="h-3 w-3" />
                                ✓ DONE
                              </span>
                            )}
                            {isFailed && (
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-950/40 px-2.5 py-0.5 text-[10.5px] font-bold text-red-400 shadow-[0_0_12px_rgba(239,68,68,0.15)]">
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
                              {b.custom_title || b.title || (b.target_id ? `Target: ${b.target_id}` : b.format_id)}
                            </div>
                            <div className="text-[10.5px] text-zinc-400 flex flex-wrap items-center gap-2 mt-1">
                              <span>ID: {b.id.slice(0, 12)}…</span>
                              {b.target_id && (
                                <span className="rounded-full border border-cyan-400/40 bg-cyan-400/15 px-2.5 py-0.5 text-[9.5px] font-bold text-cyan-300 shadow-[0_0_10px_rgba(0,210,255,0.2)]">
                                  TARGET · {b.target_id} {b.target_version ? `v${b.target_version}` : ""}
                                </span>
                              )}
                              {b.saved && (
                                <span className="text-cyan-400 font-bold">★ SAVED</span>
                              )}
                            </div>
                          </td>

                          {/* Fighters */}
                          <td className="py-4 px-4">
                            <div className="font-bold text-zinc-200">
                              {(b.model_ids || []).join("  vs  ")}
                            </div>
                            <div className="text-[10.5px] text-zinc-400">
                              Isolated MicroVM execution
                            </div>
                          </td>

                          {/* Result / Verdict */}
                          <td className="py-4 px-4">
                            {isLive && (
                              <span className="text-cyan-400 font-bold animate-pulse">
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
                              <Clock className="h-3 w-3 text-zinc-400" />
                              <span>{formatDuration(b.timeout_seconds)}</span>
                            </div>
                          </td>

                          {/* Action Button */}
                          <td className="py-4 pr-6 pl-4 text-right">
                            <Link
                              to={`/battles/${b.id}`}
                              className="mono inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1.5 text-xs font-bold text-cyan-300 transition-all hover:bg-cyan-400/20 hover:border-cyan-400 hover:shadow-[0_0_12px_rgba(0,210,255,0.25)]"
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
