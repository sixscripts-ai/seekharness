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

function titleCase(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function providerLabel(
  id: string,
  providers: ProviderOut[],
) {
  if (!id) return "Not selected";

  const provider = providers.find(
    (item) => item.id === id,
  );

  if (!provider) {
    return id
      .replace(/^host:/, "")
      .replace(/-/g, " ");
  }

  return (
    provider.model_name ||
    provider.name ||
    id
  );
}

function formatDescription(
  format: FormatOut,
) {
  if (format.description) {
    return format.description;
  }

  if (format.engine === "agent_tool_race") {
    return "Agents execute with the full arena toolbelt.";
  }

  return "Run this arena format with predefined roles and execution rules.";
}

export default function NewBattle() {
  const { user, jwt, refreshJwt } =
    useAuth();

  const nav = useNavigate();
  const [params] = useSearchParams();

  const requestedFormat =
    params.get("format") || "";

  const requestedModels = [
    params.get("modelA"),
    params.get("modelB"),
  ].filter(Boolean) as string[];

  const [formats, setFormats] = useState<
    FormatOut[]
  >([]);

  const [providers, setProviders] =
    useState<ProviderOut[]>([]);

  const [formatId, setFormatId] =
    useState(requestedFormat);

  const [selected, setSelected] =
    useState<string[]>(requestedModels);

  const [judgeId, setJudgeId] =
    useState("");

  const [timeoutSec, setTimeoutSec] =
    useState(600);

  const [visibility, setVisibility] =
    useState<Visibility>("isolated");

  const [difficulty, setDifficulty] =
    useState<Difficulty>("general");

  const [save, setSave] = useState(false);

  const [err, setErr] = useState<
    string | null
  >(null);

  const [busy, setBusy] =
    useState(false);

  const { host, yours } = useMemo(
    () => splitProviders(providers),
    [providers],
  );

  useEffect(() => {
    if (!jwt) return;

    (async () => {
      try {
        const token =
          (await refreshJwt()) || jwt;

        const [
          formatRows,
          providerRows,
        ] = await Promise.all([
          api.formats(token),
          api.providers(token),
        ]);

        const launchable =
          formatRows.filter(
            (item) =>
              !isCustomFormat(item),
          );

        setFormats(launchable);
        setProviders(providerRows);

        const requestedIsValid =
          launchable.some(
            (item) =>
              item.id ===
              requestedFormat,
          );

        if (
          !requestedIsValid &&
          launchable[0]
        ) {
          setFormatId(
            launchable[0].id,
          );
        }

        const hostIds =
          providerRows
            .filter((item) =>
              isHostProviderId(
                item.id,
              ),
            )
            .map(
              (item) => item.id,
            );

        const fallback =
          hostIds[0] ||
          providerRows[0]?.id ||
          "host:openrouter-free";

        const alternate =
          hostIds[1] ||
          hostIds[0] ||
          fallback;

        const allowed = new Set(
          providerRows.map(
            (item) => item.id,
          ),
        );

        setSelected(
          (previous) => {
            const source =
              previous.length
                ? previous
                : requestedModels;

            if (!source.length) {
              return [
                fallback,
                alternate,
              ];
            }

            return source.map(
              (id, index) => {
                if (
                  allowed.has(id) ||
                  isHostProviderId(
                    id,
                  )
                ) {
                  return id;
                }

                return index === 1
                  ? alternate
                  : fallback;
              },
            );
          },
        );
      } catch (error) {
        setErr(
          error instanceof Error
            ? error.message
            : "Could not load arena configuration",
        );
      }
    })();
  }, [jwt]);

  const format = formats.find(
    (item) =>
      item.id === formatId,
  );

  const need = format
    ? playableRoleCount(format)
    : 2;

  const roles = useMemo(() => {
    if (!format) {
      return [
        "builder",
        "breaker",
      ];
    }

    if (
      Array.isArray(format.roles) &&
      format.roles.length
    ) {
      return format.roles.filter(
        (role) =>
          role !== "judge",
      );
    }

    return [
      "fighter a",
      "fighter b",
    ];
  }, [format]);

  useEffect(() => {
    setSelected(
      (previous) => {
        const next =
          previous.slice(0, need);

        const fallback =
          host[0]?.id ||
          providers[0]?.id ||
          "host:openrouter-free";

        const alternate =
          host[1]?.id ||
          host[0]?.id ||
          fallback;

        const allowed = new Set(
          providers.map(
            (provider) =>
              provider.id,
          ),
        );

        while (
          next.length < need
        ) {
          next.push(
            next.length === 1
              ? alternate
              : fallback,
          );
        }

        return next.map(
          (id, index) => {
            if (
              allowed.has(id) ||
              isHostProviderId(id)
            ) {
              return id;
            }

            return index === 1
              ? alternate
              : fallback;
          },
        );
      },
    );
  }, [need, providers, host]);

  async function onSubmit(
    event: React.FormEvent,
  ) {
    event.preventDefault();

    const token =
      (await refreshJwt()) ||
      jwt;

    if (!token) return;

    const allowed = new Set(
      providers.map(
        (provider) =>
          provider.id,
      ),
    );

    const invalid =
      selected.some(
        (id) =>
          !allowed.has(id) &&
          !isHostProviderId(id),
      );

    if (invalid) {
      setErr(
        "Invalid provider. Choose a platform model or one of your configured providers.",
      );
      return;
    }

    if (
      selected.length !== need ||
      selected.some(
        (id) => !id,
      )
    ) {
      setErr(
        `Assign all ${need} fighter slots before deployment.`,
      );
      return;
    }

    if (
      new Set(selected).size !==
      selected.length
    ) {
      setErr(
        "Each fighter slot must use a unique model.",
      );
      return;
    }

    setBusy(true);
    setErr(null);

    try {
      const battle =
        await api.createBattle(
          token,
          {
            format_id:
              formatId,

            model_ids:
              selected,

            arena_size:
              selected.length,

            timeout_seconds:
              timeoutSec,

            round_visibility:
              visibility,

            difficulty,
            save,

            judge_provider_id:
              judgeId || null,
          },
        );

      try {
        const key =
          "arena_battle_ids";

        const previous =
          JSON.parse(
            localStorage.getItem(
              key,
            ) || "[]",
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
        // Local battle history
        // is optional.
      }

      nav(
        `/battles/${battle.id}`,
      );
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
            Log in to configure
            fighters and deploy an
            arena battle.
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

  const assigned =
    selected.filter(
      Boolean,
    ).length;

  const uniqueFighters =
    new Set(
      selected.filter(Boolean),
    ).size ===
    selected.filter(Boolean)
      .length;

  const ready =
    Boolean(formatId) &&
    assigned === need &&
    uniqueFighters &&
    !busy;

  const timeoutMinutes =
    timeoutSec >= 60
      ? `${Math.round(
          timeoutSec / 60,
        )} min`
      : `${timeoutSec} sec`;

  const dual = need === 2;

  return (
    <form
      onSubmit={onSubmit}
      className="min-h-[calc(100vh-56px)] bg-background text-foreground"
    >
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-4 px-6 py-6 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
              New battle
            </div>

            <h1 className="mt-2 font-display text-[38px] font-semibold leading-none tracking-[-0.04em] md:text-[52px]">
              Battle Control Room
            </h1>

            <p className="mt-3 max-w-[62ch] text-[13px] leading-5 text-muted">
              Define the arena,
              assign the fighters,
              set the execution
              contract, and deploy.
            </p>
          </div>

          <div className="border border-border bg-surface px-4 py-3">
            <div className="font-mono text-[8px] uppercase tracking-[0.16em] text-muted">
              Launch readiness
            </div>

            <div className="mt-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
              <span
                className={`h-1.5 w-1.5 ${
                  ready
                    ? "bg-[var(--success)]"
                    : "bg-[var(--warn)]"
                }`}
              />

              <span
                className={
                  ready
                    ? "text-[var(--success)]"
                    : "text-muted"
                }
              >
                {ready
                  ? "Ready to deploy"
                  : "Configuration required"}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* 1. BATTLE MODE */}
      <div className="mx-auto max-w-[1360px] px-6 py-6">
        <SectionHeader
          index="1"
          title="Battle mode"
          description="Choose how you want to define this battle."
        />

        <div className="mt-4 grid gap-px bg-border md:grid-cols-3">
          <ModeCard
            active
            eyebrow="Preset"
            title="Preset battle"
            description="Use a tested arena format with predefined roles and execution rules."
            footer="Recommended"
          />

          <ModeCard
            eyebrow="Quick custom"
            title="Judge-defined challenge"
            description="Describe your own challenge, freeze the brief, and evaluate it with a host judge."
            footer="Judge evaluation"
            onClick={() =>
              nav(
                "/battles/custom?mode=quick",
              )
            }
          />

          <ModeCard
            eyebrow="Verified custom"
            title="Executable challenge"
            description="Create a custom challenge with a frozen specification and executable acceptance tests."
            footer="Tests + judge"
            onClick={() =>
              nav(
                "/battles/custom?mode=verified",
              )
            }
          />
        </div>
      </div>

      {/* 2. EXECUTION FORMAT */}
      <div className="border-y border-border">
        <div className="mx-auto max-w-[1360px] px-6 py-6">
          <SectionHeader
            index="2"
            title="Execution format"
            description="Select the arena format and role sequence."
            trailing={
              format
                ? `${need} fighter${
                    need === 1
                      ? ""
                      : "s"
                  }`
                : undefined
            }
          />

          <div className="mt-4 flex gap-px overflow-x-auto bg-border pb-px">
            {formats.map(
              (item) => {
                const active =
                  item.id ===
                  formatId;

                const count =
                  playableRoleCount(
                    item,
                  );

                const itemRoles =
                  item.roles?.filter(
                    (role) =>
                      role !==
                      "judge",
                  ) || [];

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() =>
                      setFormatId(
                        item.id,
                      )
                    }
                    className={`relative min-h-[146px] min-w-[240px] flex-1 p-4 text-left transition-colors ${
                      active
                        ? "bg-[var(--accent-soft)]"
                        : "bg-surface hover:bg-surface2"
                    }`}
                  >
                    {active && (
                      <span className="absolute inset-x-0 top-0 h-px bg-accent" />
                    )}

                    <div className="flex items-start justify-between gap-3">
                      <span
                        className={`font-mono text-[9px] uppercase tracking-[0.14em] ${
                          active
                            ? "text-accent"
                            : "text-muted"
                        }`}
                      >
                        {
                          item.engine
                        }
                      </span>

                      <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                        {count} slots
                      </span>
                    </div>

                    <div className="mt-6 text-[14px] font-semibold tracking-[-0.02em]">
                      {item.name}
                    </div>

                    <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-muted">
                      {formatDescription(
                        item,
                      )}
                    </p>

                    <div className="mt-4 font-mono text-[9px] uppercase tracking-[0.1em] text-muted">
                      {itemRoles.length
                        ? itemRoles.join(
                            " → ",
                          )
                        : "arena format"}
                    </div>
                  </button>
                );
              },
            )}
          </div>
        </div>
      </div>

      {/* 3. ASSIGN FIGHTERS */}
      <div className="mx-auto max-w-[1360px] px-6 py-6">
        <SectionHeader
          index="3"
          title="Assign fighters"
          description="Select one model for each role in the frozen format."
        />

        <div
          className={`mt-4 grid border border-border ${
            dual
              ? "grid-cols-1 md:grid-cols-[1fr_90px_1fr]"
              : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
          }`}
        >
          {selected.map(
            (
              modelId,
              index,
            ) => {
              const role =
                roles[index] ||
                `fighter ${
                  index + 1
                }`;

              return (
                <div
                  key={`${role}-${index}`}
                  className={`min-h-[190px] bg-surface p-5 ${
                    dual &&
                    index === 0
                      ? "md:order-1"
                      : dual &&
                          index ===
                            1
                        ? "md:order-3"
                        : ""
                  } ${
                    dual
                      ? ""
                      : "border-b border-border md:border-b-0 md:border-r md:last:border-r-0"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-accent">
                      {titleCase(
                        role,
                      )}
                    </span>

                    <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
                      Fighter{" "}
                      {index + 1}
                    </span>
                  </div>

                  <div className="mt-6 min-h-[34px] text-[22px] font-semibold tracking-[-0.035em]">
                    {providerLabel(
                      modelId,
                      providers,
                    )}
                  </div>

                  <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-muted">
                    role://
                    {role
                      .toLowerCase()
                      .replace(/ /g, "-")}
                  </div>

                  <div className="mt-5">
                    <ProviderSelect
                      value={
                        modelId
                      }
                      host={host}
                      yours={yours}
                      onChange={(
                        id,
                      ) => {
                        setSelected(
                          (
                            previous,
                          ) =>
                            previous.map(
                              (
                                value,
                                slot,
                              ) =>
                                slot ===
                                index
                                  ? id
                                  : value,
                            ),
                        );
                      }}
                    />
                  </div>
                </div>
              );
            },
          )}

          {dual && (
            <div className="hidden items-center justify-center border-x border-border bg-background md:order-2 md:flex">
              <div className="text-center">
                <div className="font-display text-[30px] font-semibold tracking-[-0.06em] text-accent">
                  VS
                </div>

                <div className="mx-auto mt-3 h-8 w-px bg-border" />
              </div>
            </div>
          )}
        </div>

        {/* EXECUTION PATH */}
        {format && (
          <div className="border-x border-b border-border bg-background px-5 py-4">
            <div className="font-mono text-[8px] uppercase tracking-[0.16em] text-muted">
              Execution path
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-[9px] uppercase tracking-[0.1em]">
              {roles.map(
                (
                  role,
                  index,
                ) => (
                  <div
                    key={`${role}-${index}`}
                    className="flex items-center gap-2"
                  >
                    <span className="border border-borderStrong px-3 py-2 text-foreground">
                      {titleCase(
                        role,
                      )}
                    </span>

                    {index <
                      roles.length -
                        1 && (
                      <>
                        <span className="text-muted">
                          →
                        </span>

                        <span className="border border-border px-3 py-2 text-muted">
                          handoff
                        </span>

                        <span className="text-muted">
                          →
                        </span>
                      </>
                    )}
                  </div>
                ),
              )}

              <span className="text-muted">
                →
              </span>

              <span className="border border-accent px-3 py-2 text-accent">
                evidence
              </span>

              <span className="text-muted">
                →
              </span>

              <span className="border border-borderStrong px-3 py-2 text-foreground">
                judge
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 4. EXECUTION CONTRACT */}
      <div className="border-y border-border">
        <div className="mx-auto max-w-[1360px] px-6 py-6">
          <SectionHeader
            index="4"
            title="Execution contract"
            description="Set the runtime rules that govern the battle."
          />

          <div className="mt-4 grid gap-px bg-border md:grid-cols-2 xl:grid-cols-4">
            {/* JUDGE */}
            <ControlCell label="Judge">
              <select
                className="select mt-3 font-mono text-[11px]"
                value={judgeId}
                onChange={(event) =>
                  setJudgeId(
                    event.target
                      .value,
                  )
                }
              >
                <option value="">
                  Kimi-K3 · default
                  host judge
                </option>

                {host.map(
                  (provider) => (
                    <option
                      key={
                        provider.id
                      }
                      value={
                        provider.id
                      }
                    >
                      {
                        provider.name
                      }{" "}
                      ·{" "}
                      {
                        provider.model_name
                      }
                    </option>
                  ),
                )}

                {yours.map(
                  (provider) => (
                    <option
                      key={
                        provider.id
                      }
                      value={
                        provider.id
                      }
                    >
                      {
                        provider.name
                      }{" "}
                      ·{" "}
                      {
                        provider.model_name
                      }
                    </option>
                  ),
                )}
              </select>

              <p className="mt-2 font-mono text-[9px] text-muted">
                Host judge is used
                when no override is
                selected.
              </p>
            </ControlCell>

            {/* TIMEOUT */}
            <ControlCell
              label="Timeout"
              value={timeoutMinutes}
            >
              <input
                type="range"
                min={60}
                max={3600}
                step={60}
                value={timeoutSec}
                onChange={(event) =>
                  setTimeoutSec(
                    Number(
                      event.target
                        .value,
                    ),
                  )
                }
                className="mt-5 w-full accent-accent"
              />

              <div className="mt-2 flex justify-between font-mono text-[8px] uppercase tracking-[0.08em] text-muted">
                <span>1 min</span>
                <span>60 min</span>
              </div>
            </ControlCell>

            {/* DIFFICULTY */}
            <ControlCell
              label="Difficulty"
              value={titleCase(
                difficulty,
              )}
            >
              <div className="mt-3 grid grid-cols-2 border border-border">
                {DIFFICULTIES.map(
                  (level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() =>
                        setDifficulty(
                          level,
                        )
                      }
                      className={`border-r border-b border-border px-2 py-2.5 font-mono text-[8px] uppercase tracking-[0.08em] odd:border-r last:border-b-0 [\&:nth-child(3)]:border-b-0 ${
                        difficulty ===
                        level
                          ? "bg-accent text-white"
                          : "bg-background text-muted hover:text-foreground"
                      }`}
                    >
                      {level}
                    </button>
                  ),
                )}
              </div>
            </ControlCell>

            {/* WORKSPACE ACCESS */}
            <ControlCell
              label="Workspace access"
              value={
                visibility ===
                "isolated"
                  ? "Isolated"
                  : "Open arena"
              }
            >
              <div className="mt-3 grid grid-cols-2 border border-border">
                <button
                  type="button"
                  onClick={() =>
                    setVisibility(
                      "isolated",
                    )
                  }
                  className={`border-r border-border px-3 py-3 text-left ${
                    visibility ===
                    "isolated"
                      ? "bg-[var(--accent-soft)] text-accent"
                      : "bg-background text-foreground"
                  }`}
                >
                  <div className="font-mono text-[8px] uppercase tracking-[0.1em]">
                    Isolated
                  </div>

                  <div className="mt-1 text-[9px] leading-4 text-muted">
                    Separate
                    workspaces
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() =>
                    setVisibility(
                      "open",
                    )
                  }
                  className={`px-3 py-3 text-left ${
                    visibility ===
                    "open"
                      ? "bg-[var(--accent-soft)] text-accent"
                      : "bg-background text-foreground"
                  }`}
                >
                  <div className="font-mono text-[8px] uppercase tracking-[0.1em]">
                    Open
                  </div>

                  <div className="mt-1 text-[9px] leading-4 text-muted">
                    Shared
                    visibility
                  </div>
                </button>
              </div>
            </ControlCell>
          </div>

          {/* ARTIFACTS + SUMMARY */}
          <div className="mt-px grid gap-px bg-border md:grid-cols-[1fr_1.4fr]">
            <button
              type="button"
              onClick={() =>
                setSave(
                  (value) =>
                    !value,
                )
              }
              className="flex items-center justify-between bg-surface p-5 text-left hover:bg-surface2"
            >
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-foreground">
                  Preserve battle
                  artifacts
                </div>

                <p className="mt-1 text-[10px] leading-4 text-muted">
                  Keep generated
                  outputs and battle
                  artifacts after
                  execution.
                </p>
              </div>

              <span
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
              </span>
            </button>

            <div className="bg-surface p-5">
              <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
                Contract summary
              </div>

              <div className="mt-3 grid gap-2 font-mono text-[9px] text-foreground sm:grid-cols-2">
                <SummaryPill
                  ok
                  text={
                    visibility ===
                    "isolated"
                      ? "Isolated workspaces"
                      : "Open arena visibility"
                  }
                />

                <SummaryPill
                  ok
                  text={
                    judgeId
                      ? providerLabel(
                          judgeId,
                          providers,
                        )
                      : "Kimi-K3 judge"
                  }
                />

                <SummaryPill
                  ok
                  text={`${timeoutMinutes} maximum runtime`}
                />

                <SummaryPill
                  ok
                  text={
                    save
                      ? "Artifacts preserved"
                      : "Artifacts ephemeral"
                  }
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ERROR */}
      {err && (
        <div className="border-b border-danger">
          <div className="mx-auto max-w-[1360px] px-6 py-3 font-mono text-[11px] text-danger">
            {err}
          </div>
        </div>
      )}

      {/* STICKY DEPLOY BAR */}
      <div className="sticky bottom-0 z-20 border-t border-border bg-background/95 backdrop-blur">
        <div className="mx-auto grid max-w-[1360px] gap-4 px-6 py-4 lg:grid-cols-[1fr_420px] lg:items-center">
          <div className="grid gap-3 sm:grid-cols-4">
            <ReadinessItem
              ok={Boolean(
                formatId,
              )}
              label="Format"
              value={
                format?.name ||
                "Select"
              }
            />

            <ReadinessItem
              ok={
                assigned ===
                  need &&
                uniqueFighters
              }
              label="Fighters"
              value={`${assigned}/${need} ready`}
            />

            <ReadinessItem
              ok={
                visibility ===
                "isolated"
              }
              warning={
                visibility ===
                "open"
              }
              label="Access"
              value={visibility}
            />

            <ReadinessItem
              ok
              label="Runtime"
              value={
                timeoutMinutes
              }
            />
          </div>

          <button
            type="submit"
            disabled={!ready}
            className="btn btn-primary h-12 w-full px-8 text-[12px]"
          >
            {busy
              ? "Deploying…"
              : "Deploy battle →"}
          </button>
        </div>
      </div>
    </form>
  );
}

function SectionHeader({
  index,
  title,
  description,
  trailing,
}: {
  index: string;
  title: string;
  description: string;
  trailing?: string;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="grid h-5 w-5 shrink-0 place-items-center bg-accent font-mono text-[9px] font-bold text-white">
          {index}
        </span>

        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-foreground">
            {title}
          </div>

          <p className="mt-1 text-[11px] text-muted">
            {description}
          </p>
        </div>
      </div>

      {trailing && (
        <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-accent">
          {trailing}
        </div>
      )}
    </div>
  );
}

function ModeCard({
  active = false,
  eyebrow,
  title,
  description,
  footer,
  onClick,
}: {
  active?: boolean;
  eyebrow: string;
  title: string;
  description: string;
  footer: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative min-h-[170px] p-5 text-left transition-colors ${
        active
          ? "bg-[var(--accent-soft)]"
          : "bg-surface hover:bg-surface2"
      }`}
    >
      {active && (
        <span className="absolute inset-x-0 top-0 h-px bg-accent" />
      )}

      <div
        className={`font-mono text-[9px] uppercase tracking-[0.15em] ${
          active
            ? "text-accent"
            : "text-muted"
        }`}
      >
        {eyebrow}
      </div>

      <div className="mt-6 text-[16px] font-semibold tracking-[-0.02em]">
        {title}
      </div>

      <p className="mt-2 max-w-[42ch] text-[11px] leading-5 text-muted">
        {description}
      </p>

      <div
        className={`mt-4 font-mono text-[9px] uppercase tracking-[0.1em] ${
          active
            ? "text-accent"
            : "text-muted"
        }`}
      >
        {footer}{" "}
        {onClick ? "→" : ""}
      </div>
    </button>
  );
}

function ControlCell({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-[154px] bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-muted">
          {label}
        </div>

        {value && (
          <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-accent">
            {value}
          </div>
        )}
      </div>

      {children}
    </div>
  );
}

function SummaryPill({
  ok,
  text,
}: {
  ok: boolean;
  text: string;
}) {
  return (
    <div className="flex items-center gap-2 border border-border bg-background px-3 py-2">
      <span
        className={`h-1.5 w-1.5 ${
          ok
            ? "bg-[var(--success)]"
            : "bg-muted"
        }`}
      />

      <span className="truncate">
        {text}
      </span>
    </div>
  );
}

function ReadinessItem({
  ok,
  warning = false,
  label,
  value,
}: {
  ok: boolean;
  warning?: boolean;
  label: string;
  value: string;
}) {
  const dot = warning
    ? "bg-[var(--warn)]"
    : ok
      ? "bg-[var(--success)]"
      : "bg-muted";

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.12em] text-muted">
        <span
          className={`h-1.5 w-1.5 ${dot}`}
        />

        {label}
      </div>

      <div className="mt-1 truncate font-mono text-[9px] text-foreground">
        {value}
      </div>
    </div>
  );
}
