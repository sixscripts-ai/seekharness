import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type FormatOut, type StatsOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import FormatCard from "@/components/FormatCard";

const FALLBACK_HOST_FREE = "nemotron-3-ultra:free • r1:free • llama-3.3-70b";

export default function Home() {
  const { user } = useAuth();
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [engine, setEngine] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsOut | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        // public — fetch immediately, don't wait for auth/jwt
        const data = await api.formats(null);
        if (!cancelled) setFormats(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) setFormats([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.stats();
        if (!cancelled) setStats(s);
      } catch {
        // stats are cosmetic — fall back to placeholders
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const hostFreeModels = useMemo(() => {
    if (!stats || !stats.top_models.length) return null;
    const hosts = stats.top_models.filter((m) =>
      m.model_id.startsWith("host:"),
    );
    if (!hosts.length) return null;
    return hosts
      .slice(0, 3)
      .map((m) => m.model_id.replace("host:", ""))
      .join(" • ");
  }, [stats]);

  const avgLabel = useMemo(() => {
    if (!stats || stats.median_duration_s == null) return "—";
    const s = Math.round(stats.median_duration_s);
    return s < 60
      ? `${s}s`
      : `${Math.floor(s / 60)}m${s % 60 ? `${s % 60}s` : ""}`;
  }, [stats]);

  const engines = useMemo(() => {
    const s = new Set(formats.map((f) => f.engine).filter(Boolean));
    return ["all", ...Array.from(s).sort()];
  }, [formats]);

  const filtered =
    engine === "all" ? formats : formats.filter((f) => f.engine === engine);

  return (
    <div className="space-y-12 md:space-y-16">
      <section className="grid grid-cols-12 gap-8 border-b border-border pb-12">
        <div className="col-span-12 lg:col-span-7 space-y-6">
          <div className="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-[11px] font-medium text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            LIVE • {stats ? stats.battles_running : "—"} battle
            {stats && stats.battles_running === 1 ? "" : "s"} running • Host
            free default
          </div>
          <h1 className="text-[34px] md:text-[56px] font-semibold leading-[1.05] tracking-[-0.03em]">
            Models fight.
            <br />
            You watch code.
          </h1>
          <p className="max-w-[52ch] text-[15px] leading-6 text-muted">
            Not a fake log feed. Two models streaming real code side-by-side,
            token-by-token. Judge scores on rubric, redacted reasoning. BYOK or
            use host free (DeepSeek, OpenRouter, Groq).
          </p>
          <div className="flex gap-3 pt-1">
            <Link
              to={user ? "/battles/new" : "/signup"}
              className="btn btn-primary h-11 px-6 text-[13px]"
            >
              Start battle →
            </Link>
            <Link
              to={user ? "/battles/custom" : "/signup"}
              className="btn btn-ghost h-11 px-6 text-[13px]"
            >
              Custom prompt
            </Link>
            <Link
              to="/leaderboard"
              className="btn btn-ghost h-11 px-6 text-[13px]"
            >
              Leaderboard
            </Link>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-5 grid grid-cols-2 gap-3">
          <div className="card p-5">
            <div className="text-[11px] font-medium text-muted">Formats</div>
            <div className="mt-2 text-[32px] font-semibold tracking-[-0.02em]">
              {loading ? "—" : formats.length}
            </div>
            <div className="mt-1 text-[12px] text-muted">
              {engines.length - 1} engines
            </div>
          </div>
          <div className="card p-5">
            <div className="text-[11px] font-medium text-muted">Avg battle</div>
            <div className="mt-2 text-[32px] font-semibold tracking-[-0.02em]">
              {avgLabel}
            </div>
            <div className="mt-1 text-[12px] text-muted">median</div>
          </div>
          <div className="col-span-2 card p-5 flex items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-medium text-muted">
                Host free models
              </div>
              <div className="mt-1 text-[13px] font-medium">
                {hostFreeModels || FALLBACK_HOST_FREE}
              </div>
            </div>
            <span className="tag shrink-0">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              FREE
            </span>
          </div>
          <div className="col-span-2 rounded-lg bg-soft border border-border px-4 py-3 font-mono text-[11px] leading-5 text-muted">
            Backend:{" "}
            {import.meta.env.VITE_MODAL_URL?.slice(0, 32) || "modal.run"}... •
            Dual code streaming: line numbers + tok/s + win condition • No fake
            logs
          </div>
        </div>
      </section>

      <section className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[16px] font-semibold tracking-[-0.01em]">
            Format library{" "}
            <span className="ml-1 text-muted font-normal">
              {filtered.length}
            </span>
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {engines.map((e) => (
              <button
                key={e}
                onClick={() => setEngine(e)}
                className={`rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors ${
                  engine === e
                    ? "border-accent bg-accent text-accent-fg"
                    : "border-border bg-surface text-muted hover:border-borderStrong hover:text-foreground"
                }`}
              >
                {e}
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <p className="text-[12px] text-muted">Loading formats…</p>
        ) : (
          <div className="grid grid-cols-12 gap-3 auto-rows-[180px]">
            {filtered.map((f, i) => (
              <FormatCard key={f.id} format={f} user={user} large={i < 2} />
            ))}
            {filtered.length === 0 && (
              <div className="col-span-12 rounded-lg border border-dashed border-border p-10 text-center text-[13px] text-muted">
                No formats for {engine}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
