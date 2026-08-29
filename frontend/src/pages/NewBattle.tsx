import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  isCustomFormat,
  isHostProviderId,
  playableRoleCount,
  splitProviders,
  type FormatOut,
  type ProviderOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ProviderSelect from "@/components/ProviderSelect";

type Difficulty = "novice" | "general" | "advanced" | "expert";
type Visibility = "isolated" | "open";

const DIFFICULTIES: Difficulty[] = [
  "novice",
  "general",
  "advanced",
  "expert",
];

function formatProviderName(
  id: string,
  providers: ProviderOut[],
): string {
  if (!id) return "Not selected";

  const provider = providers.find((item) => item.id === id);

  if (!provider) {
    return id
      .replace("host:", "")
      .replace(/-/g, " ");
  }

  return provider.model_name || provider.name || id;
}

function titleCase(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function NewBattle() {
  const { user, jwt, refreshJwt } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();

  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [providers, setProviders] = useState<ProviderOut[]>([]);

  const [formatId, setFormatId] = useState(params.get("format") || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [judgeId, setJudgeId] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(600);

  const [visibility, setVisibility] =
    useState<Visibility>("isolated");

  const [difficulty, setDifficulty] =
    useState<Difficulty>("general");

  const [save, setSave] = useState(false);

  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const host = useMemo(
    () => splitProviders(providers).host,
    [providers],
  );

  const yours = useMemo(
    () => splitProviders(providers).yours,
    [providers],
  );

  useEffect(() => {
    if (!jwt) return;

    (async () => {
      const token = (await refreshJwt()) || jwt;

      const [f, p] = await Promise.all([
        api.formats(token),
        api.providers(token),
      ]);

      const launchable = f.filter(
        (fmt) => !isCustomFormat(fmt),
      );

      setFormats(launchable);
      setProviders(p);

      if (!formatId && launchable[0]) {
        setFormatId(launchable[0].id);
      }

      const hostIds = p
        .filter((item) => isHostProviderId(item.id))
        .map((item) => item.id);

      const fallback =
        hostIds[0] ||
        p[0]?.id ||
        "host:openrouter-free";

      const alternate =
        hostIds[1] ||
        hostIds[0] ||
        fallback;

      if (selected.length === 0) {
        setSelected([fallback, alternate]);
      }
    })();
  }, [jwt]);

  const format = formats.find(
    (item) => item.id === formatId,
  );

  const need = format
    ? playableRoleCount(format)
    : 2;

  const roles = useMemo(() => {
    if (!format) {
      return ["builder", "breaker"];
    }

    const formatRoles = (
      format as { roles?: string[] }
    ).roles;

    if (Array.isArray(formatRoles)) {
      return formatRoles.filter(
        (role) => role !== "judge",
      );
    }

    return ["a", "b"];
  }, [format]);

  useEffect(() => {
    setSelected((previous) => {
      const next = previous.slice(0, need);

      const fallback =
        host[0]?.id ||
        providers[0]?.id ||
        "host:openrouter-free";

      const alternate =
        host[1]?.id ||
        host[0]?.id ||
        fallback;

      while (next.length < need) {
        next.push(
          next.length === 1
            ? alternate
            : fallback,
        );
      }

      const allowed = new Set(
        providers.map((provider) => provider.id),
      );

      return next.map((id) =>
        allowed.has(id) || isHostProviderId(id)
          ? id
          : fallback,
      );
    });
  }, [need, providers, host]);

  async function onSubmit(
    event: React.FormEvent,
  ) {
    event.preventDefault();

    const token =
      (await refreshJwt()) || jwt;

    if (!token) return;

    const allowed = new Set(
      providers.map((provider) => provider.id),
    );

    const invalid = selected.some(
      (id) =>
        !allowed.has(id) &&
        !isHostProviderId(id),
    );

    if (invalid) {
      setErr(
        "Invalid provider — choose any host model or one of your configured providers.",
      );
      return;
    }

    setBusy(true);
    setErr(null);

    try {
      const battle = await api.createBattle(
        token,
        {
          format_id: formatId,
          model_ids: selected,
          arena_size: selected.length,
          timeout_seconds: timeoutSec,
          round_visibility: visibility,
          difficulty,
          save,
          judge_provider_id:
            judgeId || null,
        },
      );

      try {
        const key = "arena_battle_ids";

        const previous = JSON.parse(
          localStorage.getItem(key) || "[]",
        ) as string[];

        localStorage.setItem(
          key,
          JSON.stringify(
            [
              battle.id,
              ...previous,
            ].slice(0, 50),
          ),
        );
      } catch {
        // Local history is optional.
      }

      nav(`/battles/${battle.id}`);
    } catch (error) {
      setErr(
        error instanceof Error
          ? error.message
          : "Create failed",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[36ch] space-y-3 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            Battle control room
          </div>

          <p className="text-[14px] text-muted">
            Log in to configure fighters and
            deploy an arena battle.
          </p>

          <Link
            to="/login"
            className="btn btn-primary mx-auto h-10 px-6"
          >
            Log in
          </Link>
        </div>
      </div>
    );
  }

  const dual = need === 2;

  const timeoutMinutes =
    timeoutSec >= 60
      ? `${Math.round(timeoutSec / 60)} min`
      : `${timeoutSec} sec`;

  const readyFighters = selected.filter(Boolean).length;

  const ready =
    Boolean(formatId) &&
    readyFighters === need &&
    !busy;

  return (
    <form
      onSubmit={onSubmit}
      className="min-h-[calc(100vh-56px)] bg-background text-foreground"
    >
      {/* HEADER */}
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-4 px-6 py-6 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
              Battle control room
            </div>

            <h1 className="mt-2 font-display text-[38px] font-semibold leading-none tracking-[-0.04em] md:text-[52px]">
              Deploy a battle
            </h1>

            <p className="mt-3 max-w-[60ch] text-[13px] leading-5 text-muted">
              Select the execution format,
              assign fighters, define the
              sandbox contract, and launch.
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            <span
              className={`h-1.5 w-1.5 ${
                ready
                  ? "bg-[var(--success)]"
                  : "bg-[var(--warn)]"
              }`}
            />

            {ready
              ? "Ready to deploy"
              : "Configuration required"}
          </div>
        </div>
      </header>

      {/* BATTLE MODE */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1360px] px-6 py-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
              Battle mode
            </div>

            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
              Choose how the arena is defined
            </div>
          </div>

          <div className="grid gap-px bg-border md:grid-cols-3">
            {/* PRESET */}
            <button
              type="button"
              className="group relative min-h-[154px] bg-surface p-5 text-left transition-colors hover:bg-surface2"
            >
              <div className="absolute inset-x-0 top-0 h-px bg-accent" />

              <div className="flex items-start justify-between">
                <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-accent">
                  01 / Preset
                </div>

                <span className="border border-accent px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-accent">
                  Active
                </span>
              </div>

              <h2 className="mt-6 text-[17px] font-semibold tracking-[-0.02em]">
                Preset battle
              </h2>

              <p className="mt-2 max-w-[38ch] text-[12px] leading-5 text-muted">
                Launch a tested arena format
                with predefined roles and
                execution rules.
              </p>
            </button>

            {/* QUICK CUSTOM */}
            <button
              type="button"
              onClick={() =>
                nav("/battles/custom?mode=quick")
              }
              className="group relative min-h-[154px] bg-surface p-5 text-left transition-colors hover:bg-surface2"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted">
                02 / Quick
              </div>

              <h2 className="mt-6 text-[17px] font-semibold tracking-[-0.02em] group-hover:text-accent">
                Quick custom
              </h2>

              <p className="mt-2 max-w-[38ch] text-[12px] leading-5 text-muted">
                Define your own brief and
                evaluate the result with a
                host judge.
              </p>

              <div className="mt-4 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                Judge evaluation →
              </div>
            </button>

            {/* VERIFIED CUSTOM */}
            <button
              type="button"
              onClick={() =>
                nav(
                  "/battles/custom?mode=verified",
                )
              }
              className="group relative min-h-[154px] bg-surface p-5 text-left transition-colors hover:bg-surface2"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted">
                03 / Verified
              </div>

              <h2 className="mt-6 text-[17px] font-semibold tracking-[-0.02em] group-hover:text-accent">
                Verified custom
              </h2>

              <p className="mt-2 max-w-[38ch] text-[12px] leading-5 text-muted">
                Define a custom challenge with
                executable Python acceptance
                tests.
              </p>

              <div className="mt-4 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                Tests + judge →
              </div>
            </button>
          </div>
        </div>
      </section>

      {/* MAIN COMMAND CENTER */}
      <div className="mx-auto grid max-w-[1360px] grid-cols-12">
        <main className="col-span-12 border-border lg:col-span-8 lg:border-r">
          {/* FORMAT */}
          <section className="border-b border-border px-6 py-6">
            <div className="flex flex-col justify-between gap-2 md:flex-row md:items-end">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                  01 / Select arena format
                </div>

                <h2 className="mt-2 text-[20px] font-semibold tracking-[-0.025em]">
                  Execution format
                </h2>
              </div>

              {format && (
                <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                  {format.engine} · {need} fighter
                  {need !== 1 ? "s" : ""}
                </div>
              )}
            </div>

            <div className="mt-5 grid gap-px bg-border md:grid-cols-2 xl:grid-cols-3">
              {formats.map((item) => {
                const active =
                  item.id === formatId;

                const fighterCount =
                  playableRoleCount(item);

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() =>
                      setFormatId(item.id)
                    }
                    className={`relative min-h-[128px] p-4 text-left transition-colors ${
                      active
                        ? "bg-[var(--accent-soft)]"
                        : "bg-surface hover:bg-surface2"
                    }`}
                  >
                    {active && (
                      <div className="absolute inset-x-0 top-0 h-px bg-accent" />
                    )}

                    <div className="flex items-start justify-between gap-4">
                      <span
                        className={`font-mono text-[9px] uppercase tracking-[0.12em] ${
                          active
                            ? "text-accent"
                            : "text-muted"
                        }`}
                      >
                        {item.engine}
                      </span>

                      <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                        {fighterCount} slots
                      </span>
                    </div>

                    <div className="mt-5 text-[14px] font-medium">
                      {item.name}
                    </div>

                    {item.description && (
                      <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-muted">
                        {item.description}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </section>

          {/* FIGHTERS */}
          <section className="border-b border-border">
            <div className="px-6 pt-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                02 / Assign fighters
              </div>

              <h2 className="mt-2 text-[20px] font-semibold tracking-[-0.025em]">
                Arena lineup
              </h2>
            </div>

            <div
              className={`mt-5 grid border-t border-border ${
                dual
                  ? "grid-cols-1 md:grid-cols-[1fr_92px_1fr]"
                  : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
              }`}
            >
              {selected.map((modelId, index) => {
                const role =
                  roles[index] ||
                  `fighter ${index + 1}`;

                return (
                  <div
                    key={index}
                    className={[
                      "relative min-h-[210px] border-border px-6 py-6",
                      dual && index === 0
                        ? "md:order-1"
                        : "",
                      dual && index === 1
                        ? "md:order-3"
                        : "",
                      !dual
                        ? "border-b md:border-r"
                        : "border-b md:border-b-0",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
                        Fighter {index + 1}
                      </div>

                      <div className="font-mono text-[9px] uppercase tracking-[0.13em] text-muted">
                        {titleCase(role)}
                      </div>
                    </div>

                    <div className="mt-6 text-[24px] font-semibold tracking-[-0.035em]">
                      {formatProviderName(
                        modelId,
                        providers,
                      )}
                    </div>

                    <div className="mt-2 font-mono text-[10px] text-muted">
                      role://
                      {role.toLowerCase()}
                    </div>

                    <div className="mt-6">
                      <ProviderSelect
                        value={modelId}
                        host={host}
                        yours={yours}
                        onChange={(id) => {
                          const next = [
                            ...selected,
                          ];

                          next[index] = id;

                          setSelected(next);
                        }}
                      />
                    </div>
                  </div>
                );
              })}

              {dual && (
                <div className="hidden items-center justify-center border-x border-border bg-background md:order-2 md:flex">
                  <div>
                    <div className="font-display text-[28px] font-semibold tracking-[-0.05em] text-accent">
                      VS
                    </div>

                    <div className="mt-2 h-8 w-px bg-border mx-auto" />
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* PIPELINE */}
          <section className="border-b border-border px-6 py-6">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
              Execution path
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em]">
              {roles.map((role, index) => (
                <div
                  key={role}
                  className="flex items-center gap-2"
                >
                  <span className="border border-borderStrong px-3 py-2 text-foreground">
                    {titleCase(role)}
                  </span>

                  {index <
                    roles.length - 1 && (
                    <>
                      <span className="text-muted">
                        →
                      </span>

                      <span className="border border-border px-3 py-2 text-muted">
                        Handoff
                      </span>

                      <span className="text-muted">
                        →
                      </span>
                    </>
                  )}
                </div>
              ))}

              <span className="text-muted">
                →
              </span>

              <span className="border border-accent px-3 py-2 text-accent">
                Evidence
              </span>

              <span className="text-muted">
                →
              </span>

              <span className="border border-borderStrong px-3 py-2">
                Judge
              </span>
            </div>
          </section>

          {/* EXECUTION CONTRACT */}
          <section className="px-6 py-6">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
              03 / Execution contract
            </div>

            <h2 className="mt-2 text-[20px] font-semibold tracking-[-0.025em]">
              Runtime controls
            </h2>

            <div className="mt-5 grid gap-px bg-border md:grid-cols-2">
              {/* JUDGE */}
              <div className="bg-surface p-5">
                <label className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
                  Judge
                </label>

                <select
                  className="select mt-3 font-mono text-[11px]"
                  value={judgeId}
                  onChange={(event) =>
                    setJudgeId(
                      event.target.value,
                    )
                  }
                >
                  <option value="">
                    Default host judge (Kimi-K3)
                  </option>

                  {host.map((provider) => (
                    <option
                      key={provider.id}
                      value={provider.id}
                    >
                      {provider.name} ·{" "}
                      {provider.model_name}
                    </option>
                  ))}

                  {yours.map((provider) => (
                    <option
                      key={provider.id}
                      value={provider.id}
                    >
                      {provider.name} ·{" "}
                      {provider.model_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* TIMEOUT */}
              <div className="bg-surface p-5">
                <div className="flex items-center justify-between">
                  <label className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
                    Maximum runtime
                  </label>

                  <span className="font-mono text-[10px] text-accent">
                    {timeoutMinutes}
                  </span>
                </div>

                <input
                  type="range"
                  min={60}
                  max={3600}
                  step={60}
                  value={timeoutSec}
                  onChange={(event) =>
                    setTimeoutSec(
                      Number(
                        event.target.value,
                      ),
                    )
                  }
                  className="mt-6 w-full accent-accent"
                />

                <div className="mt-2 flex justify-between font-mono text-[9px] text-muted">
                  <span>1 min</span>
                  <span>60 min</span>
                </div>
              </div>

              {/* DIFFICULTY */}
              <div className="bg-surface p-5">
                <label className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
                  Difficulty
                </label>

                <div className="mt-3 grid grid-cols-4 border border-border">
                  {DIFFICULTIES.map(
                    (level) => (
                      <button
                        key={level}
                        type="button"
                        onClick={() =>
                          setDifficulty(level)
                        }
                        className={`border-r border-border px-2 py-3 font-mono text-[9px] uppercase tracking-[0.08em] last:border-r-0 ${
                          difficulty === level
                            ? "bg-accent text-white"
                            : "bg-background text-muted hover:text-foreground"
                        }`}
                      >
                        {level}
                      </button>
                    ),
                  )}
                </div>
              </div>

              {/* ACCESS */}
              <div className="bg-surface p-5">
                <div className="flex items-center justify-between">
                  <label className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
                    Workspace access
                  </label>

                  {visibility ===
                    "isolated" && (
                    <span className="font-mono text-[8px] uppercase tracking-[0.12em] text-[var(--success)]">
                      Recommended
                    </span>
                  )}
                </div>

                <div className="mt-3 grid grid-cols-2 border border-border">
                  <button
                    type="button"
                    onClick={() =>
                      setVisibility(
                        "isolated",
                      )
                    }
                    className={`px-3 py-3 text-left ${
                      visibility ===
                      "isolated"
                        ? "bg-[var(--accent-soft)]"
                        : "bg-background"
                    }`}
                  >
                    <div
                      className={`font-mono text-[9px] uppercase tracking-[0.12em] ${
                        visibility ===
                        "isolated"
                          ? "text-accent"
                          : "text-foreground"
                      }`}
                    >
                      Isolated
                    </div>

                    <div className="mt-1 text-[10px] leading-4 text-muted">
                      Separate agent
                      workspaces.
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      setVisibility("open")
                    }
                    className={`border-l border-border px-3 py-3 text-left ${
                      visibility === "open"
                        ? "bg-[var(--accent-soft)]"
                        : "bg-background"
                    }`}
                  >
                    <div
                      className={`font-mono text-[9px] uppercase tracking-[0.12em] ${
                        visibility ===
                        "open"
                          ? "text-accent"
                          : "text-foreground"
                      }`}
                    >
                      Open arena
                    </div>

                    <div className="mt-1 text-[10px] leading-4 text-muted">
                      Shared visibility.
                    </div>
                  </button>
                </div>
              </div>
            </div>

            {/* ARTIFACT SAVE */}
            <button
              type="button"
              onClick={() => setSave(!save)}
              className="mt-px flex w-full items-center justify-between border border-border bg-surface p-5 text-left hover:bg-surface2"
            >
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-foreground">
                  Preserve battle artifacts
                </div>

                <p className="mt-1 text-[11px] text-muted">
                  Retain battle output and
                  generated artifacts after
                  execution.
                </p>
              </div>

              <div
                className={`relative h-5 w-9 border ${
                  save
                    ? "border-accent bg-accent"
                    : "border-borderStrong bg-background"
                }`}
              >
                <span
                  className={`absolute top-[3px] h-3 w-3 bg-white transition-all ${
                    save
                      ? "left-[19px]"
                      : "left-[3px]"
                  }`}
                />
              </div>
            </button>
          </section>
        </main>

        {/* RIGHT RAIL: OPTION 1 ELEVATED FROST DOSSIER */}
        <aside className="col-span-12 lg:col-span-4">
          <div className="lg:sticky lg:top-[72px] m-4 rounded-xl border border-pink-500/35 bg-[#0D0914] p-6 shadow-[0_12px_40px_rgba(0,0,0,0.85)]">
            <div className="flex items-center justify-between border-b border-pink-500/20 pb-4">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-pink-400 font-bold">
                  BATTLE DOSSIER
                </div>
                <div className="mt-1 font-display text-[22px] font-extrabold tracking-tight text-white">
                  Launch Readiness
                </div>
              </div>

              <div className="text-right">
                <div className="font-display text-[32px] font-black leading-none text-pink-400">
                  {readyFighters}/{need}
                </div>
                <div className="font-mono text-[8px] uppercase tracking-wider text-zinc-400">
                  READY
                </div>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-black/60 border border-white/5">
              <div
                className="h-full bg-pink-500 transition-all duration-300 shadow-[0_0_10px_#FF00A0]"
                style={{
                  width: `${
                    need
                      ? Math.min(
                          100,
                          (readyFighters / need) * 100,
                        )
                      : 0
                  }%`,
                }}
              />
            </div>

            {/* CONTRACT SPEC TABLE */}
            <div className="mt-5 rounded-lg border border-pink-500/20 bg-black/40 p-3.5 font-mono text-[10px]">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">FORMAT</span>
                  <span className="font-bold text-white truncate max-w-[160px]">{format?.name || "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">CONTESTANTS</span>
                  <span className="font-bold text-white">{need} microVM Nodes</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">WORKSPACE</span>
                  <span className="font-bold text-pink-400">{visibility === "isolated" ? "Isolated Rootfs" : "Open Access"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">MAX RUNTIME</span>
                  <span className="font-bold text-white">{timeoutMinutes}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">JUDGE</span>
                  <span className="font-bold text-white">{judgeId ? formatProviderName(judgeId, providers) : "Host Kimi-K3"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-400 uppercase tracking-wider text-[9px]">ARTIFACTS</span>
                  <span className="font-bold text-pink-400">{save ? "Preserved" : "Ephemeral"}</span>
                </div>
              </div>
            </div>

            {/* PREFLIGHT CHECKLIST */}
            <div className="mt-5 space-y-2 font-mono text-[9px]">
              <div className="flex items-center gap-2 text-zinc-300">
                <span className={formatId ? "text-pink-400" : "text-zinc-600"}>✔</span>
                <span className={formatId ? "text-zinc-200" : "text-zinc-500"}>Format verified & fixtures loaded</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-300">
                <span className={readyFighters === need ? "text-pink-400" : "text-zinc-600"}>✔</span>
                <span className={readyFighters === need ? "text-zinc-200" : "text-zinc-500"}>Contestant slots assigned ({readyFighters}/{need})</span>
              </div>
              <div className="flex items-center gap-2 text-zinc-300">
                <span className="text-pink-400">✔</span>
                <span className="text-zinc-200">Modal sandbox endpoints warm</span>
              </div>
            </div>

            {/* INTEGRATED DEPLOY BUTTON */}
            <button
              type="submit"
              disabled={!ready || Boolean(busy)}
              className="mt-6 flex h-12 w-full items-center justify-center rounded-lg bg-pink-500 font-mono text-[12px] font-black uppercase tracking-wider text-black shadow-[0_0_20px_rgba(255,0,160,0.4)] transition-all hover:bg-pink-400 disabled:opacity-30 disabled:shadow-none"
            >
              {busy ? "INITIALIZING DUEL…" : "DEPLOY BATTLE →"}
            </button>
          </div>
        </aside>
      </div>

      {err && (
        <div className="border-y border-danger">
          <div className="mx-auto max-w-[1360px] px-6 py-3 font-mono text-[11px] text-danger">
            {err}
          </div>
        </div>
      )}

      {/* DEPLOY BAR (MOBILE ONLY) */}
      <footer className="sticky bottom-0 z-20 border-t border-border bg-background/95 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-4 px-6 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
              Ready configuration
            </div>

            <div className="mt-1 text-[12px] text-foreground">
              {format?.name ||
                "Select a format"}{" "}
              <span className="text-muted">
                · {need} fighters ·{" "}
                {timeoutMinutes}
              </span>
            </div>
          </div>

          <button
            type="submit"
            disabled={!ready}
            className="btn btn-primary h-12 min-w-[260px] px-8 text-[12px]"
          >
            {busy
              ? "Deploying…"
              : "Deploy battle →"}
          </button>
        </div>
      </footer>
    </form>
  );
}

function SummaryRow({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-3 last:border-b-0">
      <span className="text-muted">
        {label}
      </span>

      <span
        className={`max-w-[60%] truncate text-right ${
          accent
            ? "text-accent"
            : "text-foreground"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function PreflightRow({
  ok,
  text,
  warning = false,
}: {
  ok: boolean;
  text: string;
  warning?: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        className={`h-1.5 w-1.5 ${
          warning
            ? "bg-[var(--warn)]"
            : ok
              ? "bg-[var(--success)]"
              : "bg-muted"
        }`}
      />

      <span
        className={
          warning
            ? "text-[var(--warn)]"
            : ok
              ? "text-foreground"
              : "text-muted"
        }
      >
        {text}
      </span>
    </div>
  );
}
