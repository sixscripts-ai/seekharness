/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileCode2, GitCompare, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";

export type BattleStreamItem = {
  phase: string;
  model_id: string;
  artifact: string;
  t: number;
  kind: string;
};

type Props = {
  modelId: string;
  displayName: string;
  role: string;
  status: "waiting" | "starting" | "running" | "complete" | "failed";
  phase: string;
  events: BattleStreamItem[];
  artifacts: BattleStreamItem[];
  previewUrl?: string;
  win?: boolean;
};

type Tab = "terminal" | "files" | "diff" | "preview";

type ParsedAction = {
  action: string;
  command: string;
  state: string;
  result: string;
  durationMs?: number;
  turnId?: number;
  toolStep?: number;
  toolCallId?: string;
};

function parseJson(value: string): any | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function displayCommand(raw: any): string {
  if (typeof raw?.command === "string" && raw.command.trim()) return raw.command.trim();
  const action = String(raw?.action || raw?.tool || "event").toLowerCase();
  const target = String(raw?.target || raw?.path || raw?.name || raw?.url || "").trim();
  if (!target) return action;
  if (action === "read") return `cat ${target}`;
  if (action === "write") return `write ${target}`;
  if (action === "run") return `python ${target}`;
  if (action === "test") return target ? `pytest ${target}` : "pytest -q";
  if (action === "ls") return `ls ${target}`;
  if (action === "tree") return `tree ${target}`;
  if (action === "grep") return `grep ${target}`;
  if (action === "fetch") return `fetch ${target}`;
  return `${action} ${target}`.trim();
}

function parseAction(item: BattleStreamItem): ParsedAction | null {
  if (item.kind !== "action_log") return null;
  const raw = parseJson(item.artifact);
  if (!raw || typeof raw !== "object") return null;
  return {
    action: String(raw.action || raw.tool || "event").toUpperCase(),
    command: displayCommand(raw),
    state: String(raw.state || raw.status || "done").toLowerCase(),
    result: String(raw.result || raw.output || raw.stdout || raw.message || ""),
    durationMs: typeof raw.duration_ms === "number" ? raw.duration_ms : undefined,
    turnId: typeof raw.turn_id === "number" ? raw.turn_id : undefined,
    toolStep: typeof raw.tool_step === "number" ? raw.tool_step : undefined,
    toolCallId: typeof raw.tool_call_id === "string" ? raw.tool_call_id : undefined,
  };
}

function timeLabel(t: number) {
  return new Date(t).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function artifactFiles(artifact: string): Record<string, string> | null {
  const parsed = parseJson(artifact);
  if (!parsed || typeof parsed !== "object") return null;
  if (parsed.files && typeof parsed.files === "object") return parsed.files as Record<string, string>;
  return null;
}

function lineDiff(previous: string, current: string) {
  const before = previous.split("\n");
  const after = current.split("\n");
  const max = Math.max(before.length, after.length);
  const rows: { type: "same" | "add" | "remove"; text: string }[] = [];
  for (let i = 0; i < max; i += 1) {
    const a = before[i];
    const b = after[i];
    if (a === b && a !== undefined) rows.push({ type: "same", text: a });
    else {
      if (a !== undefined) rows.push({ type: "remove", text: a });
      if (b !== undefined) rows.push({ type: "add", text: b });
    }
  }
  return rows.slice(0, 500);
}

export default function LiveExecutionPane({
  modelId,
  displayName,
  role,
  status,
  phase,
  events,
  artifacts,
  previewUrl,
  win,
}: Props) {
  const [tab, setTab] = useState<Tab>("terminal");
  const terminalRef = useRef<HTMLDivElement | null>(null);

  const actions = useMemo(
    () => events.map((item) => ({ item, parsed: parseAction(item) })).filter((x) => x.parsed),
    [events],
  );

  const latestArtifact = artifacts[artifacts.length - 1]?.artifact || "";
  const previousArtifact = artifacts[artifacts.length - 2]?.artifact || "";
  const files = artifactFiles(latestArtifact);
  const fileEntries = files ? Object.entries(files) : [];
  const diffRows = useMemo(
    () => lineDiff(previousArtifact, latestArtifact),
    [previousArtifact, latestArtifact],
  );

  useEffect(() => {
    if (tab === "terminal" && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [actions, tab]);

  const prompt = `${role || "agent"}@arena:$`;
  const stateColor =
    status === "failed"
      ? "text-red-400"
      : status === "running"
        ? "text-emerald-400"
        : status === "complete"
          ? "text-emerald-400"
          : "text-zinc-500";

  return (
    <section
      className={cn(
        "flex min-h-[560px] flex-col overflow-hidden border bg-[#030305]",
        win ? "border-pink-500" : "border-white/10",
      )}
      aria-label={`${displayName} execution console`}
    >
      <header className="border-b border-white/10 bg-[#08080A] px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-pink-400">
              {role || "fighter"}
            </div>
            <div className="mt-1 truncate text-[16px] font-semibold tracking-[-0.02em] text-white">
              {displayName}
            </div>
            <div className="mt-1 truncate font-mono text-[9px] text-zinc-600">
              {modelId}
            </div>
          </div>

          <div className="text-right font-mono">
            <div className={cn("text-[9px] font-bold uppercase tracking-[0.13em]", stateColor)}>
              {status === "running" ? "● executing" : status}
            </div>
            <div className="mt-2 text-[9px] uppercase tracking-[0.1em] text-zinc-600">
              phase://{phase || "pending"}
            </div>
          </div>
        </div>
      </header>

      <div className="flex border-b border-white/10 bg-[#060607] font-mono">
        {([
          ["terminal", Terminal, "Terminal"],
          ["files", FileCode2, "Files"],
          ["diff", GitCompare, "Diff"],
          ["preview", ExternalLink, "Preview"],
        ] as const).map(([value, Icon, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={cn(
              "flex h-10 items-center gap-2 border-r border-white/10 px-4 text-[9px] font-bold uppercase tracking-[0.12em] transition-colors",
              tab === value
                ? "bg-pink-500/10 text-pink-400 shadow-[inset_0_-1px_0_#ff00a0]"
                : "text-zinc-500 hover:text-white",
            )}
          >
            <Icon className="h-3 w-3" />
            {label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 bg-[#020203]">
        {tab === "terminal" && (
          <div
            ref={terminalRef}
            className="h-[468px] overflow-y-auto px-5 py-4 font-mono text-[11px] leading-6 text-zinc-300"
          >
            {actions.length === 0 ? (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
                    {status === "waiting" ? "Waiting for handoff" : "Waiting for execution"}
                  </div>
                  <div className="mt-3 text-[11px] text-zinc-500">
                    No runtime tool events have been emitted for this fighter yet.
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {actions.map(({ item, parsed }, index) => {
                  if (!parsed) return null;
                  const failed = parsed.state === "failed" || parsed.state === "error";
                  const running = parsed.state === "running" || parsed.state === "starting";
                  return (
                    <div
                      key={`${parsed.toolCallId || item.t}-${index}`}
                      className={cn(
                        "border-l pl-3",
                        failed
                          ? "border-red-500/70"
                          : running
                            ? "border-pink-500/70"
                            : "border-white/10",
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="text-zinc-700">{timeLabel(item.t)}</span>
                        <span className="text-pink-400">{prompt}</span>
                        <span className="font-semibold text-zinc-100">{parsed.command}</span>
                      </div>

                      {parsed.result && (
                        <pre
                          className={cn(
                            "mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] leading-5",
                            failed ? "text-red-300" : "text-zinc-400",
                          )}
                        >
                          {parsed.result}
                        </pre>
                      )}

                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[9px] uppercase tracking-[0.08em]">
                        <span
                          className={cn(
                            failed
                              ? "text-red-400"
                              : running
                                ? "text-amber-300"
                                : "text-emerald-400",
                          )}
                        >
                          {running ? "● running" : failed ? "× failed" : "✓ done"}
                        </span>
                        {parsed.turnId ? <span className="text-zinc-700">turn {parsed.turnId}</span> : null}
                        {parsed.toolStep ? <span className="text-zinc-700">step {parsed.toolStep}</span> : null}
                        {parsed.durationMs !== undefined && parsed.durationMs > 0 ? (
                          <span className="text-zinc-700">{parsed.durationMs}ms</span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {tab === "files" && (
          <div className="h-[468px] overflow-y-auto p-4 font-mono text-[10px]">
            {fileEntries.length ? (
              <div className="space-y-2">
                {fileEntries.map(([name, content]) => (
                  <details key={name} className="border border-white/10 bg-[#070708]">
                    <summary className="cursor-pointer px-3 py-2 text-zinc-200">
                      {name}
                      <span className="ml-2 text-zinc-600">{content.length} bytes</span>
                    </summary>
                    <pre className="overflow-x-auto border-t border-white/10 p-3 text-zinc-400">
                      {content}
                    </pre>
                  </details>
                ))}
              </div>
            ) : latestArtifact ? (
              <pre className="whitespace-pre-wrap break-words text-zinc-400">{latestArtifact}</pre>
            ) : (
              <div className="grid h-full place-items-center text-zinc-600">No artifact snapshot emitted.</div>
            )}
          </div>
        )}

        {tab === "diff" && (
          <div className="h-[468px] overflow-auto p-4 font-mono text-[10px] leading-5">
            {artifacts.length < 2 ? (
              <div className="grid h-full place-items-center text-zinc-600">
                Diff appears after at least two artifact snapshots.
              </div>
            ) : (
              diffRows.map((row, i) => (
                <div
                  key={`${i}-${row.text}`}
                  className={cn(
                    "whitespace-pre-wrap break-words px-2",
                    row.type === "add"
                      ? "bg-emerald-500/5 text-emerald-300"
                      : row.type === "remove"
                        ? "bg-red-500/5 text-red-300"
                        : "text-zinc-600",
                  )}
                >
                  <span className="mr-2 select-none text-zinc-700">
                    {row.type === "add" ? "+" : row.type === "remove" ? "-" : " "}
                  </span>
                  {row.text}
                </div>
              ))
            )}
          </div>
        )}

        {tab === "preview" && (
          <div className="h-[468px] bg-[#050506]">
            {previewUrl ? (
              <iframe
                title={`${displayName} preview`}
                src={previewUrl}
                className="h-full w-full border-0 bg-white"
              />
            ) : (
              <div className="grid h-full place-items-center px-8 text-center font-mono">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
                    Preview unavailable
                  </div>
                  <div className="mt-3 max-w-[42ch] text-[10px] leading-5 text-zinc-500">
                    A preview is shown only when the runtime emits a valid preview URL for this fighter.
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
