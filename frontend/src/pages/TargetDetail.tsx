import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileCode2,
  Files,
  Fingerprint,
  GitBranch,
  LockKeyhole,
  Play,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Swords,
} from "lucide-react";
import { api, type TargetDetailOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function titleCase(value: string) {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function difficultyBadgeStyle(difficulty: string) {
  switch (difficulty.toLowerCase()) {
    case "novice":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    case "general":
      return "border-cyan-500/30 bg-cyan-500/10 text-cyan-400";
    case "advanced":
      return "border-pink-500/40 bg-pink-500/10 text-pink-400 shadow-[0_0_12px_rgba(255,0,160,0.2)]";
    case "expert":
      return "border-amber-500/40 bg-amber-500/10 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.2)]";
    default:
      return "border-zinc-700 bg-zinc-800 text-zinc-300";
  }
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

export default function TargetDetail() {
  const { id = "" } = useParams();
  const { jwt } = useAuth();
  const [target, setTarget] = useState<TargetDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeRoleTab, setActiveRoleTab] = useState<"builder" | "breaker" | "all">("builder");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .target(id, jwt)
      .then((row) => {
        if (!cancelled) setTarget(row);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Target challenge not found");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, jwt]);

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-56px)] flex-col items-center justify-center space-y-4 bg-[#0A0A0A] text-foreground">
        <RefreshCw className="h-8 w-8 animate-spin text-accent" />
        <div className="mono text-xs uppercase tracking-widest text-zinc-400">
          Loading Challenge Briefing…
        </div>
      </div>
    );
  }

  if (error || !target) {
    return (
      <div className="flex min-h-[calc(100vh-56px)] items-center justify-center bg-[#0A0A0A] px-6 text-foreground">
        <div className="max-w-md rounded-2xl border border-red-500/30 bg-[#09090E] p-8 text-center shadow-2xl">
          <ShieldAlert className="mx-auto h-10 w-10 text-red-400" />
          <h3 className="mono mt-3 text-sm font-bold uppercase tracking-wider text-red-400">
            Challenge Unavailable
          </h3>
          <p className="mt-2 text-xs text-zinc-400">{error || "The requested target is not installed in the registry."}</p>
          <Link
            to="/targets"
            className="mono btn btn-primary mt-6 inline-flex h-9 items-center gap-2 px-5 text-xs font-bold"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Target Library
          </Link>
        </div>
      </div>
    );
  }

  const isBuilderBreaker = target.format === "builder_breaker";
  const evaluatorGated =
    target.starter_files === null ||
    target.visible_tests === null ||
    target.protected_paths === null ||
    target.handoff_allowlist === null ||
    target.limits === null ||
    target.safety === null;

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] text-foreground">
      {/* Hero Briefing Section */}
      <section className="relative overflow-hidden border-b border-[#1F1F22] bg-[#09090E] px-4 py-8 sm:px-6 lg:py-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.18)_0%,transparent_70%)]" />

        <div className="relative z-10 mx-auto max-w-[1560px]">
          {/* Breadcrumb */}
          <Link
            to="/targets"
            className="mono inline-flex items-center gap-2 text-xs font-semibold text-zinc-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Target Library</span>
            <span className="text-zinc-600">/</span>
            <span className="text-accent">{target.name}</span>
          </Link>

          <div className="mt-6 flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-4xl space-y-4">
              {/* Badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`mono inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${difficultyBadgeStyle(
                    target.difficulty,
                  )}`}
                >
                  {target.difficulty}
                </span>

                <span className="mono inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-[#050508] px-3 py-1 text-[11px] font-semibold text-zinc-300">
                  <ShieldCheck className="h-3.5 w-3.5 text-accent" />
                  <span>{titleCase(target.category)}</span>
                </span>

                <span className="mono inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-[#050508] px-3 py-1 text-[11px] font-semibold text-zinc-300">
                  {isBuilderBreaker ? <Swords className="h-3.5 w-3.5 text-pink-400" /> : <Play className="h-3.5 w-3.5 text-emerald-400" />}
                  <span>{formatTypeLabel(target.format)}</span>
                </span>

                <span className="mono rounded-full border border-white/10 bg-[#050508] px-3 py-1 text-[11px] font-semibold text-zinc-400">
                  v{target.version}
                </span>
              </div>

              {/* Title & Description */}
              <h1 className="text-3xl font-extrabold tracking-[-0.035em] text-white sm:text-4xl lg:text-5xl">
                {target.name}
              </h1>

              <p className="max-w-3xl text-sm leading-relaxed text-zinc-300">
                {target.description}
              </p>

              {/* Tags */}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {target.tags.map((tag) => (
                  <span
                    key={tag}
                    className="mono rounded border border-[#1F1F22] bg-[#050508] px-2.5 py-0.5 text-[10px] text-zinc-400"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            </div>

            {/* Launch CTA Box */}
            <div className="flex flex-col gap-3 sm:min-w-[320px]">
              <Link
                to={`/battles/new?target=${encodeURIComponent(target.id)}`}
                className="btn btn-primary flex h-12 items-center justify-center gap-2 px-8 text-sm font-extrabold shadow-[0_0_25px_rgba(255,0,160,0.45)] hover:shadow-[0_0_35px_rgba(255,0,160,0.6)] transition-all"
              >
                <Play className="h-4 w-4 fill-current" />
                <span>Run Target Challenge</span>
                <ArrowRight className="h-4 w-4" />
              </Link>

              <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-3 text-center mono text-[10px] text-zinc-500">
                <span>Deterministic Benchmark</span> · <span>Ranked Eligible</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Briefing Body */}
      <main className="mx-auto max-w-[1560px] px-4 py-8 sm:px-6">
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_380px]">
          {/* Left Column: Challenge Architecture & Workspaces */}
          <div className="space-y-8">
            {/* 1. Challenge Objectives */}
            <section className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl space-y-5">
              <div className="flex items-center justify-between border-b border-[#1F1F22] pb-4">
                <div className="flex items-center gap-2">
                  <div className="grid h-7 w-7 place-items-center rounded-lg border border-accent/30 bg-accent/10 text-accent">
                    <CheckCircle2 className="h-4 w-4" />
                  </div>
                  <h2 className="text-base font-bold text-white">Mission Objectives</h2>
                </div>

                {isBuilderBreaker && target.role_objectives && (
                  <div className="flex items-center gap-1 rounded-xl border border-[#1F1F22] bg-[#050508] p-1 mono text-[10px]">
                    <button
                      type="button"
                      onClick={() => setActiveRoleTab("builder")}
                      className={`rounded-lg px-3 py-1 font-bold transition-all ${
                        activeRoleTab === "builder" ? "bg-accent text-white shadow-sm" : "text-zinc-400 hover:text-white"
                      }`}
                    >
                      Builder Phase
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveRoleTab("breaker")}
                      className={`rounded-lg px-3 py-1 font-bold transition-all ${
                        activeRoleTab === "breaker" ? "bg-pink-600 text-white shadow-sm" : "text-zinc-400 hover:text-white"
                      }`}
                    >
                      Breaker Phase
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveRoleTab("all")}
                      className={`rounded-lg px-3 py-1 font-bold transition-all ${
                        activeRoleTab === "all" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
                      }`}
                    >
                      All
                    </button>
                  </div>
                )}
              </div>

              {/* Objectives List */}
              {isBuilderBreaker && target.role_objectives && activeRoleTab !== "all" ? (
                <div className="space-y-3">
                  <div className="mono text-xs font-semibold text-accent uppercase tracking-wider flex items-center gap-1.5">
                    {activeRoleTab === "builder" ? (
                      <>
                        <Shield className="h-3.5 w-3.5" />
                        <span>Builder Mission (Phase 1: Harden & Deliver)</span>
                      </>
                    ) : (
                      <>
                        <Swords className="h-3.5 w-3.5" />
                        <span>Breaker Mission (Phase 2: Exploit & Bypass)</span>
                      </>
                    )}
                  </div>

                  <div className="space-y-2">
                    {(target.role_objectives[activeRoleTab] || target.objectives).map((obj, i) => (
                      <div
                        key={`${activeRoleTab}-${i}`}
                        className="flex items-start gap-3 rounded-xl border border-[#1F1F22] bg-[#050508] p-3.5"
                      >
                        <span className="mono text-xs font-bold text-accent">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <p className="text-xs leading-relaxed text-zinc-300">{obj}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {target.objectives.map((obj, i) => (
                    <div
                      key={`obj-${i}`}
                      className="flex items-start gap-3 rounded-xl border border-[#1F1F22] bg-[#050508] p-3.5"
                    >
                      <span className="mono text-xs font-bold text-accent">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <p className="text-xs leading-relaxed text-zinc-300">{obj}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* 2. Workspace & Verification Breakdown */}
            {evaluatorGated ? (
              <div className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl">
                <div className="flex items-start gap-3 rounded-xl border border-[#1F1F22] bg-[#050508] p-4 text-xs leading-relaxed text-zinc-400">
                  <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <div>
                    <span>
                      Starter workspace files, visible test files, protected security paths, and resource limits are
                      disclosed to authenticated sessions.
                    </span>
                    <Link
                      to={`/login?next=${encodeURIComponent(`/targets/${encodeURIComponent(target.id)}`)}`}
                      className="mono ml-2 font-bold uppercase tracking-wider text-accent hover:text-accent-hover"
                    >
                      Sign In to Inspect →
                    </Link>
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid gap-6 md:grid-cols-2">
                {/* Starter Workspace */}
                <FileSection
                  title="Starter Workspace"
                  icon={<Files className="h-4 w-4 text-cyan-400" />}
                  files={target.starter_files || []}
                  empty="No starter files declared"
                  description="Files mounted into the fresh agent container at session start."
                />

                {/* Visible Verification */}
                <FileSection
                  title="Visible Test Harness"
                  icon={<FileCode2 className="h-4 w-4 text-emerald-400" />}
                  files={target.visible_tests || []}
                  empty="No visible test files declared"
                  description="Public test suite executable by the fighter via the 'TOOL test' command."
                />

                {/* Protected Paths */}
                <FileSection
                  title="Protected Security Paths"
                  icon={<LockKeyhole className="h-4 w-4 text-amber-400" />}
                  files={target.protected_paths || []}
                  empty="No protected paths"
                  description="System files locked by the verifier. Changes to these paths are reverted."
                />

                {/* Handoff Allowlist */}
                <FileSection
                  title="Handoff Deliverables"
                  icon={<GitBranch className="h-4 w-4 text-pink-400" />}
                  files={target.handoff_allowlist || []}
                  empty="No cross-phase handoff"
                  description={
                    isBuilderBreaker
                      ? "Artifacts transferred from Builder to Breaker in the sealed microVM."
                      : "Deliverables passed between execution phases."
                  }
                />
              </div>
            )}
          </div>

          {/* Right Column: Execution Contract & Technical Specs */}
          <aside className="space-y-6">
            {/* Verification Protocol */}
            <section className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl space-y-4">
              <div className="flex items-center gap-2 border-b border-[#1F1F22] pb-3">
                <ShieldCheck className="h-4 w-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">Verification Protocol</h3>
              </div>

              <div className="space-y-2 mono text-xs">
                <SpecRow label="Format" value={formatTypeLabel(target.format)} />
                <SpecRow label="Runtime" value={target.runtime} />
                <SpecRow label="Verification Type" value={titleCase(target.verification_type)} />
                <SpecRow label="Visible Tests" value={`${target.visible_test_count} suites`} />
                <SpecRow
                  label="Hidden Evaluator Tests"
                  value={`${target.hidden_test_count} server-side checks`}
                  highlight
                />
                <SpecRow
                  label="Handoff Isolation"
                  value={target.handoff_required ? "Sealed Transfer" : "Independent"}
                />
              </div>

              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-[11px] leading-relaxed text-emerald-300/90">
                <div className="font-bold flex items-center gap-1.5 mb-1">
                  <Shield className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Authoritative Scoring</span>
                </div>
                The verifier executes in an isolated environment against both visible tests and secret evaluator suites.
                Zero private test code or solutions are exposed to the agent.
              </div>
            </section>

            {/* Execution Constraints */}
            <section className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl space-y-4">
              <div className="flex items-center gap-2 border-b border-[#1F1F22] pb-3">
                <Clock3 className="h-4 w-4 text-accent" />
                <h3 className="text-sm font-bold text-white">Execution Constraints</h3>
              </div>

              <div className="space-y-2 mono text-xs">
                <SpecRow
                  label="Max Tool Steps"
                  value={target.limits ? `${target.limits.max_tool_steps} steps` : "Sign in to view"}
                />
                <SpecRow
                  label="Execution Timeout"
                  value={target.limits ? `${target.limits.exec_timeout_seconds} seconds` : "Sign in to view"}
                />
                <SpecRow
                  label="Network Policy"
                  value={target.network ? "Network Allowed" : "Sealed (Offline)"}
                />
                <SpecRow
                  label="Sandbox Isolation"
                  value="Modal MicroVM (Rootless)"
                />
              </div>
            </section>

            {/* Technical Metadata & Hash Pinning */}
            <section className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-xl space-y-3 mono text-xs">
              <div className="flex items-center gap-2 border-b border-[#1F1F22] pb-3 text-zinc-400">
                <Fingerprint className="h-4 w-4 text-accent" />
                <h3 className="font-bold text-white uppercase text-[11px] tracking-wider">
                  Target Identity & Hash
                </h3>
              </div>

              <div className="space-y-2 text-[10.5px]">
                <div>
                  <div className="text-zinc-500 uppercase text-[9px]">Target ID</div>
                  <div className="text-white font-bold">{target.id}</div>
                </div>

                <div>
                  <div className="text-zinc-500 uppercase text-[9px]">Manifest SHA-256</div>
                  <div className="break-all text-accent font-semibold">{target.manifest_hash}</div>
                </div>
              </div>
            </section>

            {/* Launch Action */}
            <Link
              to={`/battles/new?target=${encodeURIComponent(target.id)}`}
              className="btn btn-primary flex h-11 w-full items-center justify-center gap-2 text-xs font-bold shadow-[0_0_20px_rgba(255,0,160,0.35)]"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Configure Target Battle</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </aside>
        </div>
      </main>
    </div>
  );
}

function SpecRow({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-[#1F1F22] bg-[#050508] px-3 py-2">
      <span className="text-zinc-500 uppercase text-[9.5px]">{label}</span>
      <span className={`font-semibold ${highlight ? "text-accent" : "text-zinc-200"}`}>{value}</span>
    </div>
  );
}

function FileSection({
  title,
  icon,
  files,
  empty,
  description,
}: {
  title: string;
  icon: React.ReactNode;
  files: string[];
  empty: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-[#1F1F22] bg-[#09090E] p-5 shadow-lg space-y-3">
      <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
        <div className="flex items-center gap-2">
          {icon}
          <h4 className="text-xs font-bold text-white uppercase tracking-wider">{title}</h4>
        </div>
        <span className="mono text-[10px] text-zinc-500">{files.length} paths</span>
      </div>

      <p className="text-[11px] leading-relaxed text-zinc-400">{description}</p>

      <div className="max-h-48 overflow-y-auto rounded-xl border border-[#1F1F22] bg-[#050508] p-2 mono text-[10.5px]">
        {files.length > 0 ? (
          files.map((file, idx) => (
            <div
              key={file}
              className="flex items-center gap-2 px-2 py-1.5 text-zinc-300 hover:bg-[#121216] rounded transition-colors"
            >
              <span className="text-zinc-600 select-none text-[9px] w-5">
                {String(idx + 1).padStart(2, "0")}
              </span>
              <span className="break-all">{file}</span>
            </div>
          ))
        ) : (
          <div className="py-4 text-center text-zinc-600 text-xs">{empty}</div>
        )}
      </div>
    </div>
  );
}
