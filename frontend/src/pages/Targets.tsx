import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  Code2,
  Cpu,
  Database,
  Eye,
  Flame,
  LockKeyhole,
  Play,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Swords,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { api, type TargetSummaryOut } from "@/lib/api";

const DIFFICULTY_ORDER = ["novice", "general", "advanced", "expert"];

function titleCase(value: string) {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function difficultyRank(value: string) {
  const index = DIFFICULTY_ORDER.indexOf(value.toLowerCase());
  return index === -1 ? DIFFICULTY_ORDER.length : index;
}

function compactHash(hash: string) {
  return hash.length > 16 ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : hash;
}

function formatTypeLabel(format: string) {
  switch (format.toLowerCase()) {
    case "builder_breaker":
      return "Builder vs Breaker";
    case "solo":
      return "Solo Benchmark";
    case "ctf":
      return "CTF Challenge";
    case "adversarial_agent":
      return "Adversarial Agent";
    default:
      return titleCase(format);
  }
}

function categoryIcon(category: string) {
  switch (category.toLowerCase()) {
    case "cybersecurity":
    case "cybersecurity-data":
      return <Shield className="h-3.5 w-3.5" />;
    case "systems":
      return <Cpu className="h-3.5 w-3.5" />;
    case "data-sql":
      return <Database className="h-3.5 w-3.5" />;
    case "agent-security":
      return <ShieldAlert className="h-3.5 w-3.5" />;
    case "agent-tool-use":
      return <Terminal className="h-3.5 w-3.5" />;
    case "ctf":
      return <Flame className="h-3.5 w-3.5" />;
    case "software-engineering":
    default:
      return <Code2 className="h-3.5 w-3.5" />;
  }
}

function difficultyBadgeStyle(difficulty: string) {
  switch (difficulty.toLowerCase()) {
    case "novice":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    case "general":
      return "border-cyan-500/30 bg-cyan-500/10 text-cyan-400";
    case "advanced":
      return "border-pink-500/40 bg-pink-500/10 text-pink-400 shadow-[0_0_10px_rgba(255,0,160,0.15)]";
    case "expert":
      return "border-amber-500/40 bg-amber-500/10 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.15)]";
    default:
      return "border-zinc-700 bg-zinc-800 text-zinc-300";
  }
}

export default function Targets() {
  const [params, setParams] = useSearchParams();
  const [targets, setTargets] = useState<TargetSummaryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const search = params.get("q") || "";
  const category = params.get("category") || "all";
  const difficulty = params.get("difficulty") || "all";
  const format = params.get("format") || "all";

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const rows = await api.targets();
        if (!cancelled) setTargets(rows);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load target library");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const facets = useMemo(() => {
    const categories = Array.from(new Set(targets.map((target) => target.category))).sort();
    const formats = Array.from(new Set(targets.map((target) => target.format))).sort();
    const difficulties = Array.from(new Set(targets.map((target) => target.difficulty))).sort(
      (a, b) => difficultyRank(a) - difficultyRank(b),
    );
    const allTags = Array.from(new Set(targets.flatMap((target) => target.tags))).sort();
    return { categories, formats, difficulties, allTags };
  }, [targets]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return targets.filter((target) => {
      if (category !== "all" && target.category.toLowerCase() !== category.toLowerCase()) return false;
      if (difficulty !== "all" && target.difficulty.toLowerCase() !== difficulty.toLowerCase()) return false;
      if (format !== "all" && target.format.toLowerCase() !== format.toLowerCase()) return false;
      if (activeTag && !target.tags.some((t) => t.toLowerCase() === activeTag.toLowerCase())) return false;
      if (!term) return true;
      return [
        target.name,
        target.description,
        target.category,
        target.difficulty,
        target.format,
        target.runtime,
        target.id,
        ...target.tags,
      ].some((value) => value.toLowerCase().includes(term));
    });
  }, [targets, search, category, difficulty, format, activeTag]);

  const advancedCount = targets.filter((target) =>
    ["advanced", "expert"].includes(target.difficulty.toLowerCase()),
  ).length;
  const builderBreakerCount = targets.filter((target) => target.format === "builder_breaker").length;
  const soloCount = targets.length - builderBreakerCount;

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  function clearFilters() {
    setActiveTag(null);
    setParams({}, { replace: true });
  }

  const hasFilters = Boolean(search || category !== "all" || difficulty !== "all" || format !== "all" || activeTag);

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] text-foreground">
      {/* Hero Container */}
      <section className="relative overflow-hidden border-b border-[#1F1F22] bg-[#09090E] px-4 py-8 sm:px-6 lg:py-12">
        {/* Ambient Neon Radial Glows */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.18)_0%,transparent_70%)]" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.1)_0%,transparent_70%)]" />

        <div className="relative z-10 mx-auto max-w-[1560px]">
          <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
                <Boxes className="h-3.5 w-3.5" />
                <span>TARGET LIBRARY V2 · IMMUTABLE BENCHMARKS</span>
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.035em] text-white sm:text-4xl lg:text-5xl">
                Verified Targets for{" "}
                <span className="text-accent drop-shadow-[0_0_25px_rgba(255,0,160,0.5)]">
                  Agent Evaluation
                </span>
              </h1>

              <p className="text-xs leading-relaxed text-zinc-400 sm:text-sm">
                Standardized, tamper-proof repository challenges designed for robust model evaluation.
                Each challenge features a frozen manifest hash, isolated microVM starter workspace,
                visible test harness, and authoritative server-side hidden verification.
              </p>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-4 text-center">
                <div className="text-2xl font-extrabold text-white">{targets.length}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-500">Targets</div>
              </div>
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-4 text-center">
                <div className="text-2xl font-extrabold text-accent">{builderBreakerCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-500">Builder vs Breaker</div>
              </div>
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-4 text-center">
                <div className="text-2xl font-extrabold text-emerald-400">{soloCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-500">Solo / CTF</div>
              </div>
              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-4 text-center">
                <div className="text-2xl font-extrabold text-amber-400">{advancedCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-500">Advanced+</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Filter & Search Bar */}
      <section className="sticky top-14 z-20 border-b border-[#1F1F22] bg-[#0A0A0A]/95 backdrop-blur-md">
        <div className="mx-auto max-w-[1560px] space-y-3 px-4 py-4 sm:px-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            {/* Search Input */}
            <div className="relative min-w-[280px] flex-1">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <input
                value={search}
                onChange={(event) => updateParam("q", event.target.value)}
                placeholder="Search challenges by name, objective, tag, or runtime…"
                className="mono h-10 w-full rounded-xl border border-[#1F1F22] bg-[#050508] pl-10 pr-4 text-xs text-white outline-none transition-colors placeholder:text-zinc-600 focus:border-accent focus:shadow-[0_0_12px_rgba(255,0,160,0.2)]"
              />
            </div>

            {/* Dropdown Filters */}
            <div className="flex flex-wrap items-center gap-2.5">
              <select
                aria-label="Filter by Category"
                value={category}
                onChange={(e) => updateParam("category", e.target.value)}
                className="mono h-10 rounded-xl border border-[#1F1F22] bg-[#050508] px-3 text-xs text-white outline-none focus:border-accent"
              >
                <option value="all">All Categories</option>
                {facets.categories.map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by Difficulty"
                value={difficulty}
                onChange={(e) => updateParam("difficulty", e.target.value)}
                className="mono h-10 rounded-xl border border-[#1F1F22] bg-[#050508] px-3 text-xs text-white outline-none focus:border-accent"
              >
                <option value="all">All Difficulties</option>
                {facets.difficulties.map((d) => (
                  <option key={d} value={d}>
                    {titleCase(d)}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by Format"
                value={format}
                onChange={(e) => updateParam("format", e.target.value)}
                className="mono h-10 rounded-xl border border-[#1F1F22] bg-[#050508] px-3 text-xs text-white outline-none focus:border-accent"
              >
                <option value="all">All Formats</option>
                {facets.formats.map((f) => (
                  <option key={f} value={f}>
                    {formatTypeLabel(f)}
                  </option>
                ))}
              </select>

              {hasFilters && (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="mono flex h-10 items-center gap-1.5 rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 text-xs font-bold text-red-400 hover:bg-red-500/20 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                  Reset
                </button>
              )}
            </div>
          </div>

          {/* Quick Category Chips */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
            <button
              type="button"
              onClick={() => updateParam("category", "all")}
              className={`mono rounded-lg px-3 py-1 text-[11px] font-bold transition-all ${
                category === "all"
                  ? "bg-accent text-white shadow-[0_0_10px_rgba(255,0,160,0.3)]"
                  : "border border-[#1F1F22] bg-[#050508] text-zinc-400 hover:text-white"
              }`}
            >
              All Targets
            </button>
            {facets.categories.map((cat) => {
              const active = category.toLowerCase() === cat.toLowerCase();
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => updateParam("category", cat)}
                  className={`mono inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1 text-[11px] font-bold transition-all ${
                    active
                      ? "bg-accent text-white shadow-[0_0_10px_rgba(255,0,160,0.3)]"
                      : "border border-[#1F1F22] bg-[#050508] text-zinc-400 hover:text-white hover:border-zinc-600"
                  }`}
                >
                  {categoryIcon(cat)}
                  <span>{titleCase(cat)}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* Main Target Grid */}
      <main className="mx-auto max-w-[1560px] px-4 py-8 sm:px-6">
        {/* Results Bar */}
        <div className="mb-6 flex items-center justify-between border-b border-[#1F1F22] pb-3 font-mono text-xs text-zinc-500">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white">{visible.length}</span>
            <span>of</span>
            <span>{targets.length} challenges available</span>
            {activeTag && (
              <span className="inline-flex items-center gap-1 rounded border border-accent/40 bg-accent/15 px-2 py-0.5 text-[10px] text-accent">
                tag: {activeTag}
                <button type="button" onClick={() => setActiveTag(null)} className="hover:text-white">
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            )}
          </div>
          <div className="hidden items-center gap-2 sm:flex">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-[11px] text-zinc-400">All targets run in hardened, isolated microVM sandboxes</span>
          </div>
        </div>

        {/* Catalog Body */}
        {loading ? (
          <div className="flex min-h-[380px] flex-col items-center justify-center space-y-4 rounded-2xl border border-[#1F1F22] bg-[#09090E]">
            <RefreshCw className="h-8 w-8 animate-spin text-accent" />
            <span className="mono text-xs uppercase tracking-wider text-zinc-400">
              Loading Target Library Registry…
            </span>
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-500/40 bg-red-950/20 p-8 text-center">
            <ShieldAlert className="mx-auto h-8 w-8 text-red-400" />
            <h3 className="mt-3 text-base font-bold text-white">Failed to load target registry</h3>
            <p className="mt-1 text-xs text-zinc-400">{error}</p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="btn btn-primary mt-4 inline-flex h-9 items-center gap-2 px-4 text-xs font-bold"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Retry
            </button>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex min-h-[360px] flex-col items-center justify-center space-y-4 rounded-2xl border border-[#1F1F22] bg-[#09090E] p-8 text-center">
            <div className="grid h-12 w-12 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
              <Search className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-bold text-white">No challenges match your filters</h3>
              <p className="text-xs text-zinc-400">
                Try adjusting your search terms or clearing active category and difficulty filters.
              </p>
            </div>
            <button
              type="button"
              onClick={clearFilters}
              className="mono inline-flex h-9 items-center gap-2 rounded-xl border border-accent/40 bg-accent/15 px-4 text-xs font-bold text-accent hover:bg-accent hover:text-white transition-all"
            >
              Reset All Filters
            </button>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((target) => (
              <TargetCard
                key={target.id}
                target={target}
                activeTag={activeTag}
                onSelectTag={(tag) => setActiveTag(activeTag === tag ? null : tag)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function TargetCard({
  target,
  activeTag,
  onSelectTag,
}: {
  target: TargetSummaryOut;
  activeTag: string | null;
  onSelectTag: (tag: string) => void;
}) {
  const isBuilderBreaker = target.format === "builder_breaker";

  return (
    <article className="group relative flex flex-col justify-between rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl transition-all duration-200 hover:border-pink-500/40 hover:shadow-[0_0_25px_rgba(255,0,160,0.12)]">
      <div>
        {/* Card Header: Badges */}
        <div className="flex items-center justify-between gap-2 border-b border-[#1F1F22] pb-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={`mono inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${difficultyBadgeStyle(
                target.difficulty,
              )}`}
            >
              {target.difficulty}
            </span>
            <span className="mono inline-flex items-center gap-1 rounded-full border border-white/10 bg-[#050508] px-2.5 py-0.5 text-[10px] font-semibold text-zinc-400">
              {categoryIcon(target.category)}
              <span>{titleCase(target.category)}</span>
            </span>
          </div>

          <span className="mono text-[10px] font-semibold text-zinc-500">v{target.version}</span>
        </div>

        {/* Title & Format */}
        <div className="mt-4 space-y-1.5">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-lg font-bold tracking-tight text-white group-hover:text-pink-400 transition-colors">
              {target.name}
            </h3>
            <span className="mono shrink-0 rounded border border-white/[0.08] bg-[#050508] px-2 py-0.5 text-[9.5px] font-semibold text-zinc-400">
              {target.runtime}
            </span>
          </div>

          <div className="mono flex items-center gap-2 text-[10px] text-accent">
            {isBuilderBreaker ? <Swords className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            <span className="font-semibold uppercase tracking-wider">{formatTypeLabel(target.format)}</span>
          </div>
        </div>

        {/* Description */}
        <p className="mt-3 text-xs leading-relaxed text-zinc-400 line-clamp-3">
          {target.description}
        </p>

        {/* Verification & Safety Specs */}
        <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl border border-[#1F1F22] bg-[#050508] p-3 mono text-[10px]">
          <div className="space-y-0.5">
            <div className="text-zinc-500 text-[9px] uppercase tracking-wider flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              <span>Verification</span>
            </div>
            <div className="font-bold text-zinc-300">
              {target.visible_test_count} visible · {target.hidden_test_count} hidden
            </div>
          </div>

          <div className="space-y-0.5">
            <div className="text-zinc-500 text-[9px] uppercase tracking-wider flex items-center gap-1">
              {target.network ? <Zap className="h-3 w-3 text-amber-400" /> : <LockKeyhole className="h-3 w-3 text-zinc-400" />}
              <span>Isolation</span>
            </div>
            <div className="font-bold text-zinc-300">
              {target.network ? "Network Allowed" : "MicroVM Sealed"}
            </div>
          </div>
        </div>

        {/* Tags */}
        <div className="mt-4 flex flex-wrap gap-1.5">
          {target.tags.slice(0, 4).map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => onSelectTag(tag)}
              className={`mono rounded border px-2 py-0.5 text-[9px] transition-colors ${
                activeTag === tag
                  ? "border-accent bg-accent/20 text-accent font-bold"
                  : "border-[#1F1F22] bg-[#050508] text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
              }`}
            >
              #{tag}
            </button>
          ))}
        </div>
      </div>

      {/* Card Footer: Actions */}
      <div className="mt-6 flex items-center justify-between border-t border-[#1F1F22] pt-4">
        <span className="mono text-[9px] text-zinc-600 truncate max-w-[120px]" title={target.manifest_hash}>
          sha256:{compactHash(target.manifest_hash)}
        </span>

        <div className="flex items-center gap-2">
          <Link
            to={`/targets/${encodeURIComponent(target.id)}`}
            className="mono flex h-8 items-center gap-1.5 rounded-lg border border-[#1F1F22] bg-[#050508] px-3 text-[11px] font-bold text-zinc-300 hover:border-zinc-500 hover:text-white transition-colors"
          >
            <Eye className="h-3 w-3" />
            <span>Briefing</span>
          </Link>

          <Link
            to={`/battles/new?target=${encodeURIComponent(target.id)}`}
            className="mono flex h-8 items-center gap-1.5 rounded-lg border border-accent bg-accent px-3.5 text-[11px] font-bold text-white shadow-[0_0_12px_rgba(255,0,160,0.3)] hover:bg-accent-hover transition-all"
          >
            <span>Run</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </div>
    </article>
  );
}
