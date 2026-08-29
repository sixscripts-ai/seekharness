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
  Network,
  ShieldCheck,
} from "lucide-react";
import { api, type TargetDetailOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function titleCase(value: string) {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function TargetDetail() {
  const { id = "" } = useParams();
  const { jwt } = useAuth();
  const [target, setTarget] = useState<TargetDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // The backend gates evaluator-internal detail fields behind optional
    // auth: anonymous callers get the public brief (objectives only), while
    // authenticated callers receive the full safe representation.
    api
      .target(id, jwt)
      .then((row) => {
        if (!cancelled) setTarget(row);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Target not found");
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
      <div className="grid min-h-[calc(100vh-56px)] place-items-center bg-[#070707] text-zinc-500">
        <div className="font-mono text-xs uppercase tracking-[0.12em]">Loading target contract…</div>
      </div>
    );
  }

  if (error || !target) {
    return (
      <div className="grid min-h-[calc(100vh-56px)] place-items-center bg-[#070707] px-6 text-white">
        <div className="max-w-xl border border-[#2A2A2E] bg-[#0A0A0D] p-8 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-red-400">Target unavailable</div>
          <p className="mt-3 text-sm text-zinc-400">{error || "The requested target is not installed."}</p>
          <Link to="/targets" className="mt-5 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-accent">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to library
          </Link>
        </div>
      </div>
    );
  }

  const evaluatorGated =
    target.starter_files === null ||
    target.visible_tests === null ||
    target.protected_paths === null ||
    target.handoff_allowlist === null ||
    target.limits === null ||
    target.safety === null;

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#070707] text-white">
      <section className="border-b border-[#232326] bg-[#09090E]">
        <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:py-10">
          <Link to="/targets" className="inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-500 hover:text-white">
            <ArrowLeft className="h-3.5 w-3.5" /> Target Library
          </Link>

          <div className="mt-7 grid gap-8 xl:grid-cols-[1fr_360px] xl:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em]">
                <span className="border border-accent/40 bg-accent/10 px-2 py-1 text-accent">{target.category}</span>
                <span className="border border-[#2A2A2E] px-2 py-1 text-zinc-400">{target.difficulty}</span>
                <span className="border border-[#2A2A2E] px-2 py-1 text-zinc-400">v{target.version}</span>
              </div>
              <h1 className="mt-4 text-3xl font-bold tracking-[-0.045em] sm:text-4xl lg:text-5xl">{target.name}</h1>
              <p className="mt-4 max-w-4xl text-sm leading-6 text-zinc-400">{target.description}</p>
              <div className="mt-5 font-mono text-[9px] text-zinc-600">target://{target.id}</div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row xl:flex-col">
              <Link
                to={`/battles/new?target=${encodeURIComponent(target.id)}`}
                className="flex h-11 items-center justify-center gap-2 bg-accent px-5 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-white hover:bg-accent-hover"
              >
                Configure target battle <ArrowRight className="h-4 w-4" />
              </Link>
              <div className="border border-[#2A2A2E] bg-[#08080A] px-4 py-3 font-mono text-[8px] leading-4 text-zinc-600">
                manifest sha256<br />
                <span className="break-all text-zinc-400">{target.manifest_hash}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <main className="mx-auto grid max-w-[1440px] gap-6 px-4 py-8 sm:px-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <Panel title="Mission objectives" icon={<CheckCircle2 className="h-4 w-4" />}>
            <ol className="divide-y divide-[#1F1F22] border border-[#1F1F22]">
              {target.objectives.map((objective, index) => (
                <li key={`${index}-${objective}`} className="grid grid-cols-[42px_1fr] bg-[#0A0A0D]">
                  <div className="grid place-items-center border-r border-[#1F1F22] font-mono text-[9px] text-accent">{String(index + 1).padStart(2, "0")}</div>
                  <div className="p-4 text-[12px] leading-5 text-zinc-300">{objective}</div>
                </li>
              ))}
            </ol>
          </Panel>

          {evaluatorGated ? (
            <Panel title="Evaluator contract" icon={<LockKeyhole className="h-4 w-4" />}>
              <div className="flex items-start gap-3 border border-[#1F1F22] bg-[#0A0A0D] p-4 text-[11px] leading-5 text-zinc-400">
                <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span>
                  Starter files, visible verification, protected paths, handoff
                  allowlists, and resource limits are disclosed to authenticated
                  accounts only.
                  <Link
                    to={`/login?next=${encodeURIComponent(`/targets/${encodeURIComponent(target.id)}`)}`}
                    className="ml-1 font-mono text-[10px] uppercase tracking-[0.1em] text-accent hover:text-accent-hover"
                  >
                    Log in to inspect
                  </Link>
                </span>
              </div>
            </Panel>
          ) : (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <FilePanel title="Starter workspace" icon={<Files className="h-4 w-4" />} files={target.starter_files || []} empty="No starter files" />
                <FilePanel title="Visible verification" icon={<FileCode2 className="h-4 w-4" />} files={target.visible_tests || []} empty="No visible test files" />
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <FilePanel title="Protected paths" icon={<LockKeyhole className="h-4 w-4" />} files={target.protected_paths || []} empty="No protected paths declared" />
                <FilePanel title="Handoff allowlist" icon={<GitBranch className="h-4 w-4" />} files={target.handoff_allowlist || []} empty="No cross-phase handoff" />
              </div>
            </>
          )}
        </div>

        <aside className="space-y-4">
          <Panel title="Execution contract" icon={<ShieldCheck className="h-4 w-4" />}>
            <div className="divide-y divide-[#1F1F22] border border-[#1F1F22]">
              <Fact label="Format" value={titleCase(target.format)} />
              <Fact label="Runtime" value={target.runtime} />
              <Fact label="Verification" value={titleCase(target.verification_type)} />
              <Fact label="Visible tests" value={String(target.visible_test_count)} />
              <Fact label="Evaluator tests" value={String(target.hidden_test_count)} />
              <Fact label="Handoff" value={target.handoff_required ? "Required" : "None"} />
            </div>
          </Panel>

          <Panel title="Resource limits" icon={<Clock3 className="h-4 w-4" />}>
            {target.limits ? (
              <div className="divide-y divide-[#1F1F22] border border-[#1F1F22]">
                <Fact label="Max tool steps" value={String(target.limits.max_tool_steps)} />
                <Fact label="Exec timeout" value={`${target.limits.exec_timeout_seconds}s`} />
              </div>
            ) : (
              <div className="border border-[#1F1F22] bg-[#070709] px-3 py-4 font-mono text-[9px] text-zinc-600">
                Sign in to view resource limits.
              </div>
            )}
          </Panel>

          <Panel title="Safety boundary" icon={<Fingerprint className="h-4 w-4" />}>
            <div className="divide-y divide-[#1F1F22] border border-[#1F1F22]">
              {target.safety && <Fact label="Scope" value={String(target.safety.scope || "local-synthetic")} />}
              {target.safety && (
                <Fact label="Real targets" value={target.safety.real_targets ? "Allowed" : "Disallowed"} />
              )}
              <Fact label="Network" value={target.network ? "Enabled" : "Sealed"} />
              {target.safety && (
                <Fact label="Network required" value={target.safety.network_required ? "Yes" : "No"} />
              )}
            </div>
            <div className="mt-3 flex items-start gap-2 border border-emerald-500/20 bg-emerald-500/5 p-3 text-[10px] leading-4 text-emerald-300/90">
              {target.network ? <Network className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
              The frontend receives public contract metadata only. Hidden tests, reference solutions, and host paths are not exposed by this route.
            </div>
          </Panel>
        </aside>
      </main>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="border border-[#232326] bg-[#09090B]">
      <div className="flex items-center gap-2 border-b border-[#232326] px-4 py-3 font-mono text-[9px] uppercase tracking-[0.13em] text-zinc-400">
        <span className="text-accent">{icon}</span>
        {title}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function FilePanel({ title, icon, files, empty }: { title: string; icon: React.ReactNode; files: string[]; empty: string }) {
  return (
    <Panel title={title} icon={icon}>
      <div className="border border-[#1F1F22] bg-[#070709] font-mono text-[9px]">
        {files.length ? (
          files.map((file, index) => (
            <div key={file} className={`flex items-center gap-3 px-3 py-2.5 text-zinc-400 ${index ? "border-t border-[#1F1F22]" : ""}`}>
              <span className="text-zinc-700">{String(index + 1).padStart(2, "0")}</span>
              <span className="break-all">{file}</span>
            </div>
          ))
        ) : (
          <div className="px-3 py-4 text-zinc-600">{empty}</div>
        )}
      </div>
    </Panel>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 bg-[#0A0A0D] px-3 py-2.5">
      <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-zinc-600">{label}</span>
      <span className="max-w-[62%] text-right text-[10px] text-zinc-300">{value}</span>
    </div>
  );
}
