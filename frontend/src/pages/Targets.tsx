import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  FlaskConical,
  GitBranch,
  LockKeyhole,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
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

export default function Targets() {
  const [params, setParams] = useSearchParams();
  const [targets, setTargets] = useState<TargetSummaryOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    return { categories, formats, difficulties };
  }, [targets]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return targets.filter((target) => {
      if (category !== "all" && target.category !== category) return false;
      if (difficulty !== "all" && target.difficulty !== difficulty) return false;
      if (format !== "all" && target.format !== format) return false;
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
  }, [targets, search, category, difficulty, format]);

  const advancedCount = targets.filter((target) =>
    ["advanced", "expert"].includes(target.difficulty.toLowerCase()),
  ).length;
  const verifiedCount = targets.filter((target) => target.hidden_test_count > 0).length;
  const handoffCount = targets.filter((target) => target.handoff_required).length;

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  }

  function clearFilters() {
    setParams({}, { replace: true });
  }

  const hasFilters = Boolean(search || category !== "all" || difficulty !== "all" || format !== "all");

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#070707] text-white">
      <section className="border-b border-[#232326] bg-[#09090E]">
        <div className="mx-auto max-w-[1560px] px-4 py-10 sm:px-6 lg:py-14">
          <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-4xl">
              <div className="mb-4 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-zinc-500">
                <span className="border border-accent/40 bg-accent/10 px-2.5 py-1 text-accent">
                  Target Library v1
                </span>
                <span>Immutable benchmark bundles</span>
              </div>
              <h1 className="text-3xl font-bold tracking-[-0.04em] sm:text-4xl lg:text-5xl">
                Verified targets for repeatable agent evaluation.
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-zinc-400">
                Select a frozen challenge package with a versioned manifest, isolated starter workspace,
                visible checks, evaluator-only verification, and reproducible evidence requirements.
              </p>
            </div>

            <div className="grid min-w-full grid-cols-2 border border-[#242428] bg-[#242428] gap-px sm:min-w-[520px] sm:grid-cols-4">
              <Stat value={targets.length} label="Targets" />
              <Stat value={verifiedCount} label="Hidden verified" />
              <Stat value={advancedCount} label="Advanced+" />
              <Stat value={handoffCount} label="Handoff flows" />
            </div>
          </div>
        </div>
      </section>

      <section className="sticky top-14 z-30 border-b border-[#232326] bg-[#070707]/95 backdrop-blur">
        <div className="mx-auto max-w-[1560px] px-4 py-4 sm:px-6">
          <div className="grid gap-3 lg:grid-cols-[minmax(280px,1.5fr)_repeat(3,minmax(160px,0.6fr))_auto]">
            <label className="relative block">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
              <input
                value={search}
                onChange={(event) => updateParam("q", event.target.value)}
                placeholder="Search targets, runtimes, tags…"
                className="h-10 w-full border border-[#2A2A2E] bg-[#0B0B0D] pl-10 pr-3 text-xs text-white outline-none transition-colors placeholder:text-zinc-600 focus:border-accent"
              />
            </label>

            <FilterSelect
              label="Category"
              value={category}
              options={facets.categories}
              onChange={(value) => updateParam("category", value)}
            />
            <FilterSelect
              label="Difficulty"
              value={difficulty}
              options={facets.difficulties}
              onChange={(value) => updateParam("difficulty", value)}
            />
            <FilterSelect
              label="Format"
              value={format}
              options={facets.formats}
              onChange={(value) => updateParam("format", value)}
            />

            <button
              type="button"
              onClick={clearFilters}
              disabled={!hasFilters}
              className="flex h-10 items-center justify-center gap-2 border border-[#2A2A2E] px-3 font-mono text-[10px] uppercase tracking-[0.1em] text-zinc-400 enabled:hover:border-zinc-500 enabled:hover:text-white disabled:opacity-35"
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </button>
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-[1560px] px-4 py-8 sm:px-6">
        <div className="mb-4 flex items-center justify-between border-b border-[#1F1F22] pb-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-zinc-500">
            {loading ? "Loading catalog" : `${visible.length} of ${targets.length} targets`}
          </div>
          <div className="hidden items-center gap-2 font-mono text-[9px] uppercase tracking-[0.1em] text-zinc-600 sm:flex">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
            Public metadata only · evaluator assets remain server-side
          </div>
        </div>

        {loading ? (
          <div className="grid min-h-[360px] place-items-center border border-[#1F1F22] bg-[#09090B]">
            <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.12em] text-zinc-500">
              <RefreshCw className="h-4 w-4 animate-spin text-accent" />
              Reading target registry
            </div>
          </div>
        ) : error ? (
          <div className="border border-red-500/40 bg-red-500/5 p-6 text-sm text-red-300">
            {error}
          </div>
        ) : visible.length === 0 ? (
          <div className="grid min-h-[340px] place-items-center border border-[#1F1F22] bg-[#09090B] p-8 text-center">
            <div>
              <Search className="mx-auto h-7 w-7 text-zinc-700" />
              <div className="mt-4 text-sm font-semibold">No targets match this view.</div>
              <button
                type="button"
                onClick={clearFilters}
                className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-accent hover:text-accent-hover"
              >
                Reset filters
              </button>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((target) => (
              <TargetCard key={target.id} target={target} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="bg-[#0A0A0D] p-4">
      <div className="text-xl font-semibold tracking-[-0.03em] text-white">{value}</div>
      <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-500">{label}</div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 border border-[#2A2A2E] bg-[#0B0B0D] px-3 font-mono text-[10px] uppercase tracking-[0.08em] text-zinc-300 outline-none focus:border-accent"
    >
      <option value="all">All {label.toLowerCase()}s</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {titleCase(option)}
        </option>
      ))}
    </select>
  );
}

function TargetCard({ target }: { target: TargetSummaryOut }) {
  return (
    <article className="group flex min-h-[390px] flex-col border border-[#232326] bg-[#0A0A0D] transition-colors hover:border-[#3A3A40]">
      <div className="flex items-center justify-between border-b border-[#1F1F22] px-5 py-3">
        <div className="flex min-w-0 items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-500">
          <span className="truncate text-accent">{target.category}</span>
          <span className="text-zinc-700">/</span>
          <span>{target.difficulty}</span>
        </div>
        <span className="font-mono text-[9px] text-zinc-600">v{target.version}</span>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-white">{target.name}</h2>
            <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.11em] text-zinc-600">
              target://{target.id}
            </div>
          </div>
          <div className="grid h-9 w-9 shrink-0 place-items-center border border-accent/30 bg-accent/10 text-accent">
            <Boxes className="h-4 w-4" />
          </div>
        </div>

        <p className="mt-5 min-h-[66px] text-[12px] leading-[1.6] text-zinc-400">{target.description}</p>

        <div className="mt-5 grid grid-cols-2 gap-px border border-[#1F1F22] bg-[#1F1F22]">
          <Meta icon={<GitBranch className="h-3.5 w-3.5" />} label="Format" value={titleCase(target.format)} />
          <Meta icon={<FlaskConical className="h-3.5 w-3.5" />} label="Runtime" value={target.runtime} />
          <Meta
            icon={<ShieldCheck className="h-3.5 w-3.5" />}
            label="Verification"
            value={`${target.visible_test_count} visible · ${target.hidden_test_count} hidden`}
          />
          <Meta
            icon={target.network ? <Network className="h-3.5 w-3.5" /> : <LockKeyhole className="h-3.5 w-3.5" />}
            label="Network"
            value={target.network ? "Enabled" : "Sealed"}
          />
        </div>

        <div className="mt-4 flex min-h-[44px] flex-wrap content-start gap-1.5">
          {target.tags.slice(0, 5).map((tag) => (
            <span key={tag} className="border border-[#27272B] bg-[#0D0D10] px-2 py-1 font-mono text-[8px] text-zinc-500">
              {tag}
            </span>
          ))}
        </div>

        <div className="mt-auto flex items-center justify-between border-t border-[#1F1F22] pt-4">
          <div className="font-mono text-[8px] uppercase tracking-[0.08em] text-zinc-600" title={target.manifest_hash}>
            sha256:{compactHash(target.manifest_hash)}
          </div>
          <div className="flex items-center gap-2">
            <Link
              to={`/targets/${encodeURIComponent(target.id)}`}
              className="border border-[#2A2A2E] px-3 py-2 font-mono text-[9px] uppercase tracking-[0.09em] text-zinc-300 hover:border-zinc-500 hover:text-white"
            >
              Inspect
            </Link>
            <Link
              to={`/battles/new?target=${encodeURIComponent(target.id)}`}
              className="flex items-center gap-2 border border-accent bg-accent px-3 py-2 font-mono text-[9px] font-bold uppercase tracking-[0.09em] text-white hover:bg-accent-hover"
            >
              Run target
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

function Meta({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="min-h-[70px] bg-[#09090B] p-3">
      <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.1em] text-zinc-600">
        <span className="text-zinc-500">{icon}</span>
        {label}
      </div>
      <div className="mt-2 text-[10px] leading-4 text-zinc-300">{value}</div>
    </div>
  );
}
