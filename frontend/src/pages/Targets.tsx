import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  Code2,
  Cpu,
  Database,
  Eye,
  FileCode2,
  Files,
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
import { api, type TargetDetailOut, type TargetSummaryOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function titleCase(value: string) {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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

  const [previewTarget, setPreviewTarget] = useState<TargetSummaryOut | null>(null);

  const facets = useMemo(() => {
    const categories = Array.from(new Set(targets.map((target) => target.category))).sort();
    const formats = Array.from(new Set(targets.map((target) => target.format))).sort();
    const allTags = Array.from(new Set(targets.flatMap((target) => target.tags))).sort();
    return { categories, formats, allTags };
  }, [targets]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return targets.filter((target) => {
      if (category !== "all" && target.category.toLowerCase() !== category.toLowerCase()) return false;
      if (format !== "all" && target.format.toLowerCase() !== format.toLowerCase()) return false;
      if (activeTag && !target.tags.some((t) => t.toLowerCase() === activeTag.toLowerCase())) return false;
      if (!term) return true;
      return [
        target.name,
        target.description,
        target.category,
        target.format,
        target.runtime,
        target.id,
        ...target.tags,
      ].some((value) => value.toLowerCase().includes(term));
    });
  }, [targets, search, category, format, activeTag]);

  const sealedCount = targets.filter((target) => !target.network).length;
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

  const hasFilters = Boolean(search || category !== "all" || format !== "all" || activeTag);

  return (
    <div className="min-h-[calc(100vh-64px)] bg-transparent text-foreground relative z-10">
      {/* Hero Container */}
      <section className="relative overflow-hidden border-b border-white/[0.08] bg-[#0C0E15]/85 backdrop-blur-xl px-4 py-8 sm:px-6 lg:py-12">
        {/* Ambient Radiant Glows */}
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(0,210,255,0.18)_0%,transparent_70%)]" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(217,70,239,0.14)_0%,transparent_70%)]" />

        <div className="relative z-10 mx-auto max-w-[1560px]">
          <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1 text-[11px] font-semibold text-cyan-300 shadow-[0_0_16px_rgba(0,210,255,0.25)]">
                <Boxes className="h-3.5 w-3.5" />
                <span>TARGET LIBRARY V2 · IMMUTABLE BENCHMARKS</span>
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.035em] text-white sm:text-4xl lg:text-5xl">
                Verified Targets for{" "}
                <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#00D2FF] via-[#38BDF8] to-[#D946EF] drop-shadow-[0_0_24px_rgba(0,210,255,0.45)]">
                  Agent Evaluation
                </span>
              </h1>

              <p className="text-xs leading-relaxed text-zinc-300 sm:text-sm">
                Standardized, tamper-proof repository challenges designed for robust model evaluation.
                Each challenge features a frozen manifest hash, isolated microVM starter workspace,
                visible test harness, and authoritative server-side hidden verification.
              </p>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
              <div className="rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-4 text-center shadow-lg">
                <div className="text-2xl font-extrabold text-white">{targets.length}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-400">Targets</div>
              </div>
              <div className="rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-4 text-center shadow-lg">
                <div className="text-2xl font-extrabold text-cyan-400">{builderBreakerCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-400">Builder vs Breaker</div>
              </div>
              <div className="rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-4 text-center shadow-lg">
                <div className="text-2xl font-extrabold text-emerald-400">{soloCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-400">Solo / CTF</div>
              </div>
              <div className="rounded-xl border border-white/[0.08] bg-[#11141E]/90 backdrop-blur-md p-4 text-center shadow-lg">
                <div className="text-2xl font-extrabold text-amber-400">{sealedCount}</div>
                <div className="mono mt-1 text-[9.5px] uppercase tracking-wider text-zinc-400">MicroVM Sealed</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Filter & Search Bar */}
      <section className="sticky top-16 z-20 border-b border-white/[0.08] bg-[#08090D]/85 backdrop-blur-xl">
        <div className="mx-auto max-w-[1560px] space-y-3 px-4 py-4 sm:px-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            {/* Search Input */}
            <div className="relative min-w-[280px] flex-1">
              <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <input
                value={search}
                onChange={(event) => updateParam("q", event.target.value)}
                placeholder="Search challenges by name, objective, tag, or runtime…"
                className="mono h-10 w-full rounded-full border border-white/10 bg-[#0F121A] pl-10 pr-4 text-xs text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-cyan-400 focus:shadow-[0_0_16px_rgba(0,210,255,0.25)]"
              />
            </div>

            {/* Dropdown Filters */}
            <div className="flex flex-wrap items-center gap-2.5">
              <select
                aria-label="Filter by Category"
                value={category}
                onChange={(e) => updateParam("category", e.target.value)}
                className="mono h-10 rounded-full border border-white/10 bg-[#0F121A] px-4 text-xs text-white outline-none focus:border-cyan-400"
              >
                <option value="all">All Categories</option>
                {facets.categories.map((c) => (
                  <option key={c} value={c}>
                    {titleCase(c)}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by Format"
                value={format}
                onChange={(e) => updateParam("format", e.target.value)}
                className="mono h-10 rounded-full border border-white/10 bg-[#0F121A] px-4 text-xs text-white outline-none focus:border-cyan-400"
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
                  className="mono flex h-10 items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-4 text-xs font-bold text-red-400 hover:bg-red-500/20 transition-colors"
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
              className={`mono rounded-full px-3.5 py-1 text-[11px] font-bold transition-all ${
                category === "all"
                  ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_16px_rgba(0,210,255,0.35)]"
                  : "border border-white/10 bg-white/[0.04] text-zinc-300 hover:text-white"
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
                  className={`mono inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1 text-[11px] font-bold transition-all ${
                    active
                      ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_16px_rgba(0,210,255,0.35)]"
                      : "border border-white/10 bg-white/[0.04] text-zinc-300 hover:text-white hover:border-cyan-400/40"
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
        <div className="mb-6 flex items-center justify-between border-b border-white/[0.08] pb-3 font-mono text-xs text-zinc-400">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white">{visible.length}</span>
            <span>of</span>
            <span>{targets.length} challenges available</span>
            {activeTag && (
              <span className="inline-flex items-center gap-1 rounded-full border border-cyan-400/40 bg-cyan-400/15 px-2.5 py-0.5 text-[10px] text-cyan-300">
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
          <div className="flex min-h-[380px] flex-col items-center justify-center space-y-4 rounded-2xl border border-white/[0.08] bg-[#11141E]/80 backdrop-blur-md">
            <RefreshCw className="h-8 w-8 animate-spin text-cyan-400" />
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
              className="qos-btn-glow mt-4 inline-flex h-9 items-center gap-2 px-4 text-xs font-bold"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Retry
            </button>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex min-h-[360px] flex-col items-center justify-center space-y-4 rounded-2xl border border-white/[0.08] bg-[#11141E]/80 backdrop-blur-md p-8 text-center">
            <div className="grid h-12 w-12 place-items-center rounded-2xl border border-cyan-400/30 bg-cyan-400/10 text-cyan-400">
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
              className="mono inline-flex h-9 items-center gap-2 rounded-full border border-cyan-400/40 bg-cyan-400/15 px-4 text-xs font-bold text-cyan-300 hover:bg-cyan-400 hover:text-white transition-all shadow-[0_0_12px_rgba(0,210,255,0.25)]"
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
                onPreview={setPreviewTarget}
              />
            ))}
          </div>
        )}
      </main>

      {/* Centered Preview Modal */}
      {previewTarget && (
        <TargetPreviewModal
          target={previewTarget}
          onClose={() => setPreviewTarget(null)}
        />
      )}
    </div>
  );
}

function TargetCard({
  target,
  activeTag,
  onSelectTag,
  onPreview,
}: {
  target: TargetSummaryOut;
  activeTag: string | null;
  onSelectTag: (tag: string) => void;
  onPreview: (target: TargetSummaryOut) => void;
}) {
  const isBuilderBreaker = target.format === "builder_breaker";

  return (
    <article className="group relative flex h-full flex-col justify-between rounded-2xl border border-white/[0.08] bg-[#11141E]/85 backdrop-blur-md p-6 shadow-xl transition-all duration-300 hover:border-cyan-400/50 hover:shadow-[0_0_30px_rgba(0,210,255,0.2)] hover:-translate-y-1">
      <div>
        {/* Card Header: Category & Version */}
        <div className="flex items-center justify-between gap-2 border-b border-white/[0.08] pb-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mono inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-0.5 text-[10px] font-semibold text-zinc-300">
              {categoryIcon(target.category)}
              <span>{titleCase(target.category)}</span>
            </span>
          </div>

          <span className="mono text-[10px] font-semibold text-zinc-500">v{target.version}</span>
        </div>

        {/* Title & Format */}
        <div className="mt-4 space-y-1.5">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-lg font-bold tracking-tight text-white group-hover:text-cyan-300 transition-colors">
              {target.name}
            </h3>
            <span className="mono shrink-0 rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-0.5 text-[9.5px] font-semibold text-zinc-300">
              {target.runtime}
            </span>
          </div>

          <div className="mono flex items-center gap-2 text-[10px] text-cyan-400">
            {isBuilderBreaker ? <Swords className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            <span className="font-semibold uppercase tracking-wider">{formatTypeLabel(target.format)}</span>
          </div>
        </div>

        {/* Description */}
        <p className="mt-3 text-xs leading-relaxed text-zinc-400 line-clamp-3">
          {target.description}
        </p>

        {/* Verification & Safety Specs */}
        <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 mono text-[10px]">
          <div className="space-y-0.5">
            <div className="text-zinc-400 text-[9px] uppercase tracking-wider flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              <span>Verification</span>
            </div>
            <div className="font-bold text-zinc-200">
              {target.visible_test_count} visible · {target.hidden_test_count} hidden
            </div>
          </div>

          <div className="space-y-0.5">
            <div className="text-zinc-400 text-[9px] uppercase tracking-wider flex items-center gap-1">
              {target.network ? <Zap className="h-3 w-3 text-amber-400" /> : <LockKeyhole className="h-3 w-3 text-zinc-400" />}
              <span>Isolation</span>
            </div>
            <div className="font-bold text-zinc-200">
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
              className={`mono rounded-full border px-2.5 py-0.5 text-[9px] transition-colors ${
                activeTag === tag
                  ? "border-cyan-400 bg-cyan-400/20 text-cyan-300 font-bold shadow-[0_0_10px_rgba(0,210,255,0.2)]"
                  : "border-white/10 bg-white/[0.03] text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
              }`}
            >
              #{tag}
            </button>
          ))}
        </div>
      </div>

      {/* Card Footer: Actions */}
      <div className="mt-6 flex items-center justify-between border-t border-white/[0.08] pt-4">
        <span className="mono text-[9px] text-zinc-500 truncate max-w-[120px]" title={target.manifest_hash}>
          sha256:{compactHash(target.manifest_hash)}
        </span>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPreview(target)}
            className="mono flex h-8 items-center gap-1.5 rounded-full border border-white/15 bg-white/[0.04] px-3.5 text-[11px] font-bold text-zinc-200 hover:border-cyan-400/50 hover:text-white transition-colors"
          >
            <Eye className="h-3 w-3" />
            <span>Preview</span>
          </button>

          <Link
            to={`/battles/new?target=${encodeURIComponent(target.id)}`}
            className="mono flex h-8 items-center gap-1.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-4 text-[11px] font-bold text-white shadow-[0_0_16px_rgba(0,210,255,0.35)] hover:shadow-[0_0_24px_rgba(0,210,255,0.5)] transition-all"
          >
            <span>Run</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </div>
    </article>
  );
}

function TargetPreviewModal({
  target,
  onClose,
}: {
  target: TargetSummaryOut;
  onClose: () => void;
}) {
  const { jwt } = useAuth();
  const [detail, setDetail] = useState<TargetDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "files" | "tests">("overview");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    api
      .target(target.id, jwt)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        // Fallback gracefully to summary if detailed call fails
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [target.id, jwt]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const files = detail?.starter_files || [];
  const tests = detail?.visible_tests || [];
  const objectives = detail?.objectives || [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-white/15 bg-[#0C0E17] shadow-2xl shadow-cyan-500/10 text-left overflow-hidden">
        {/* Top Header */}
        <div className="border-b border-white/[0.08] p-6 pb-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[10px] font-semibold text-zinc-300">
                  {categoryIcon(target.category)}
                  <span>{titleCase(target.category)}</span>
                </span>
                <span className="mono rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-cyan-300">
                  {target.runtime}
                </span>
                <span className="mono rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[10px] font-semibold text-zinc-400">
                  {formatTypeLabel(target.format)}
                </span>
              </div>
              <h2 className="text-xl font-extrabold tracking-tight text-white sm:text-2xl">
                {target.name}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 text-zinc-400 hover:border-white/20 hover:text-white transition-colors"
              aria-label="Close modal"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Navigation Tabs */}
          <div className="mt-4 flex items-center gap-2 border-t border-white/[0.06] pt-3">
            <button
              type="button"
              onClick={() => setActiveTab("overview")}
              className={`mono rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeTab === "overview"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-[0_0_12px_rgba(0,210,255,0.2)]"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("files")}
              className={`mono flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeTab === "files"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-[0_0_12px_rgba(0,210,255,0.2)]"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Files className="h-3.5 w-3.5" />
              <span>Starter Files</span>
              {files.length > 0 && (
                <span className="rounded-full bg-white/10 px-1.5 py-0.2 text-[9px]">
                  {files.length}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("tests")}
              className={`mono flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                activeTab === "tests"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-[0_0_12px_rgba(0,210,255,0.2)]"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <FileCode2 className="h-3.5 w-3.5" />
              <span>Verification Tests</span>
              <span className="rounded-full bg-white/10 px-1.5 py-0.2 text-[9px]">
                {target.visible_test_count}
              </span>
            </button>
          </div>
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 text-xs leading-relaxed text-zinc-300">
          {activeTab === "overview" && (
            <div className="space-y-4">
              <div>
                <h4 className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1">
                  Description
                </h4>
                <p className="text-zinc-300">{target.description}</p>
              </div>

              {objectives.length > 0 && (
                <div>
                  <h4 className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-2">
                    Key Objectives
                  </h4>
                  <div className="space-y-1.5">
                    {objectives.map((obj, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2.5 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5"
                      >
                        <span className="mono text-[10px] font-bold text-cyan-400">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span className="text-zinc-300">{obj}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Specs Grid */}
              <div className="grid grid-cols-2 gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3.5 mono text-[11px]">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Test Harness</span>
                  </div>
                  <div className="font-semibold text-white">
                    {target.visible_test_count} visible · {target.hidden_test_count} hidden
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-zinc-400 text-[10px] uppercase tracking-wider">
                    {target.network ? (
                      <Zap className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <LockKeyhole className="h-3.5 w-3.5 text-zinc-400" />
                    )}
                    <span>Sandbox Policy</span>
                  </div>
                  <div className="font-semibold text-white">
                    {target.network ? "Network Allowed" : "MicroVM Sealed"}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "files" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                  Starter Workspace Files
                </h4>
                <span className="mono text-[10px] text-zinc-500">Mounted at container init</span>
              </div>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-5 w-5 animate-spin text-cyan-400" />
                </div>
              ) : files.length > 0 ? (
                <div className="space-y-1 rounded-xl border border-white/[0.08] bg-white/[0.02] p-2 mono text-[11px]">
                  {files.map((file, idx) => (
                    <div
                      key={file}
                      className="flex items-center gap-2 rounded px-2.5 py-1.5 text-zinc-300 hover:bg-white/[0.04]"
                    >
                      <span className="text-[10px] text-zinc-500 w-5 select-none">
                        {String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="font-medium text-cyan-300 break-all">{file}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-6 text-center text-zinc-500 mono text-xs">
                  Starter files will be generated upon microVM allocation.
                </div>
              )}
            </div>
          )}

          {activeTab === "tests" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                  Visible Verification Suite
                </h4>
                <span className="mono text-[10px] text-zinc-500">
                  {target.visible_test_count} visible test suites
                </span>
              </div>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="h-5 w-5 animate-spin text-cyan-400" />
                </div>
              ) : tests.length > 0 ? (
                <div className="space-y-1 rounded-xl border border-white/[0.08] bg-white/[0.02] p-2 mono text-[11px]">
                  {tests.map((test, idx) => (
                    <div
                      key={test}
                      className="flex items-center gap-2 rounded px-2.5 py-1.5 text-zinc-300 hover:bg-white/[0.04]"
                    >
                      <span className="text-[10px] text-zinc-500 w-5 select-none">
                        {String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="font-medium text-emerald-400 break-all">{test}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs text-zinc-400">
                  Public tests are run in-sandbox via the verifier command. Hidden evaluator tests are scored authoritatively server-side.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer Actions */}
        <div className="flex items-center justify-between border-t border-white/[0.08] bg-white/[0.02] px-6 py-4">
          <Link
            to={`/targets/${encodeURIComponent(target.id)}`}
            className="mono text-xs font-semibold text-zinc-400 hover:text-cyan-300 transition-colors"
          >
            Open Full Briefing →
          </Link>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="mono rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-bold text-zinc-300 hover:border-white/20 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <Link
              to={`/battles/new?target=${encodeURIComponent(target.id)}`}
              className="mono flex items-center gap-1.5 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-5 py-2 text-xs font-bold text-white shadow-[0_0_16px_rgba(0,210,255,0.35)] hover:shadow-[0_0_24px_rgba(0,210,255,0.5)] transition-all"
            >
              <span>Launch Battle</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
