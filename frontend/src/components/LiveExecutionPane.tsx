/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { Download, ExternalLink, FileCode2, GitCompare, Terminal } from "lucide-react";
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

  const prompt = `${role ? role.replace(/[^a-zA-Z0-9_-]/g, "_") : "agent"}@arena:~$`;
  const stateColor =
    status === "failed"
      ? "text-red-400 border-red-500/30 bg-red-500/10"
      : status === "running"
        ? "text-[#FF00A0] border-pink-500/40 bg-pink-500/10 shadow-[0_0_10px_rgba(255,0,160,0.2)]"
        : status === "complete"
          ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
          : "text-zinc-500 border-white/10 bg-white/5";

  function downloadTerminalLogs() {
    const lines = actions
      .map(({ item, parsed }) => {
        if (!parsed) return "";
        const time = timeLabel(item.t);
        return `[${time}] ${prompt} ${parsed.command}\n${parsed.result ? parsed.result + "\n" : ""}[state: ${parsed.state} | duration: ${parsed.durationMs ?? 0}ms]\n`;
      })
      .join("\n");
    const blob = new Blob([lines], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(role || "fighter").replace(/[^a-zA-Z0-9_-]/g, "_")}_${modelId.replace(/[^a-zA-Z0-9_-]/g, "_")}_logs.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadArtifactFile(filename: string, content: string) {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadAllFiles() {
    if (!files) return;
    const payload = JSON.stringify(files, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(role || "fighter").replace(/[^a-zA-Z0-9_-]/g, "_")}_workspace_files.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section
      className={cn(
        "flex min-h-[620px] flex-col overflow-hidden rounded-lg border bg-[#06040A] shadow-2xl transition-all",
        win
          ? "border-pink-500 shadow-[0_0_30px_rgba(255,0,160,0.25)]"
          : "border-pink-500/20 hover:border-pink-500/40",
      )}
      aria-label={`${displayName} execution console`}
    >
      {/* Terminal Header */}
      <header className="border-b border-white/[0.08] bg-[#0A0612] px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-pink-400">
              {role ? `[ ${role} ]` : "[ FIGHTER ]"}
            </div>
            <div className="mt-1 truncate text-[17px] font-bold tracking-[-0.02em] text-white font-sans">
              {displayName}
            </div>
            <div className="mt-1 truncate font-mono text-[10px] text-zinc-500">
              {modelId}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1.5 font-mono">
            <div className={cn("inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em]", stateColor)}>
              {status === "running" ? <span className="h-1.5 w-1.5 rounded-full bg-pink-400 animate-ping" /> : null}
              {status === "running" ? "● Executing" : status}
            </div>
            <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-500">
              phase://{phase || "pending"}
            </div>
          </div>
        </div>
      </header>

      {/* Tab bar & Quick Actions */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#040207] px-2 font-mono">
        <div className="flex items-center">
          {([
            ["terminal", Terminal, "Terminal"],
            ["files", FileCode2, `Files${fileEntries.length ? ` (${fileEntries.length})` : ""}`],
            ["diff", GitCompare, "Diff"],
            ["preview", ExternalLink, "Preview"],
          ] as const).map(([value, Icon, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={cn(
                "flex h-11 items-center gap-2 border-b-2 px-5 text-[10px] font-bold uppercase tracking-[0.14em] transition-all",
                tab === value
                  ? "border-pink-500 bg-pink-500/10 text-pink-400 shadow-[inset_0_-2px_0_#ff00a0]"
                  : "border-transparent text-zinc-400 hover:border-zinc-700 hover:text-white",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        {/* Global Download / Export Quick Actions */}
        <div className="flex items-center gap-2 pr-3">
          {actions.length > 0 && (
            <button
              type="button"
              onClick={downloadTerminalLogs}
              title="Download terminal execution log as TXT"
              className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] text-zinc-300 hover:border-pink-500/50 hover:bg-pink-500/10 hover:text-pink-400 transition-colors"
            >
              <Download className="h-3 w-3" />
              <span>Export Log</span>
            </button>
          )}

          {fileEntries.length > 0 && (
            <button
              type="button"
              onClick={downloadAllFiles}
              title="Download all generated workspace files as JSON"
              className="inline-flex items-center gap-1.5 rounded border border-pink-500/30 bg-pink-500/10 px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.1em] text-pink-400 hover:bg-pink-500/20 transition-colors"
            >
              <Download className="h-3 w-3" />
              <span>Download Files ({fileEntries.length})</span>
            </button>
          )}
        </div>
      </div>

      {/* Viewport Canvas */}
      <div className="min-h-0 flex-1 bg-[#020104]">
        {tab === "terminal" && (
          <div
            ref={terminalRef}
            className="h-[520px] overflow-y-auto p-6 font-mono text-[11.5px] leading-relaxed text-zinc-300 selection:bg-pink-500/30"
          >
            {actions.length === 0 ? (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-500">
                    {status === "waiting" ? "Waiting for handoff" : "Waiting for execution"}
                  </div>
                  <div className="mt-2 text-[12px] text-zinc-600">
                    No runtime tool events have been emitted for this fighter yet.
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                {actions.map(({ item, parsed }, index) => {
                  if (!parsed) return null;
                  const failed = parsed.state === "failed" || parsed.state === "error";
                  const running = parsed.state === "running" || parsed.state === "starting";
                  return (
                    <div
                      key={`${parsed.toolCallId || item.t}-${index}`}
                      className={cn(
                        "rounded-md border-l-2 p-3 transition-colors",
                        failed
                          ? "border-red-500 bg-red-950/20"
                          : running
                            ? "border-pink-500 bg-pink-950/20 shadow-[0_0_15px_rgba(255,0,160,0.1)]"
                            : "border-white/10 bg-[#08050E]",
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                        <span className="text-zinc-500">{timeLabel(item.t)}</span>
                        <span className="font-semibold text-pink-400">{prompt}</span>
                        <span className="font-bold text-white">{parsed.command}</span>
                      </div>

                      {parsed.result && (
                        <pre
                          className={cn(
                            "mt-2 whitespace-pre-wrap break-words rounded bg-black/40 p-3 font-mono text-[11px] leading-relaxed",
                            failed ? "text-red-300" : "text-zinc-300",
                          )}
                        >
                          {parsed.result}
                        </pre>
                      )}

                      <div className="mt-2 flex flex-wrap items-center gap-3 text-[9px] uppercase tracking-[0.1em]">
                        <span
                          className={cn(
                            "font-bold",
                            failed
                              ? "text-red-400"
                              : running
                                ? "text-pink-400 animate-pulse"
                                : "text-emerald-400",
                          )}
                        >
                          {running ? "● executing..." : failed ? "× failed" : "✓ done"}
                        </span>
                        {parsed.turnId ? <span className="text-zinc-500">turn {parsed.turnId}</span> : null}
                        {parsed.toolStep ? <span className="text-zinc-500">step {parsed.toolStep}</span> : null}
                        {parsed.durationMs !== undefined && parsed.durationMs > 0 ? (
                          <span className="text-zinc-500">{parsed.durationMs}ms</span>
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
          <div className="h-[520px] overflow-y-auto p-6 font-mono text-[11px]">
            {fileEntries.length ? (
              <div className="space-y-3">
                {fileEntries.map(([name, content]) => (
                  <details key={name} className="overflow-hidden rounded border border-white/10 bg-[#07050C]">
                    <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-zinc-200 hover:bg-white/[0.02]">
                      <div className="flex items-center gap-2">
                        <FileCode2 className="h-3.5 w-3.5 text-pink-400" />
                        <span className="font-semibold">{name}</span>
                        <span className="text-zinc-500">({content.length} bytes)</span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          downloadArtifactFile(name, content);
                        }}
                        title={`Download ${name}`}
                        className="inline-flex items-center gap-1 rounded border border-white/10 bg-white/5 px-2 py-1 text-[9px] uppercase text-zinc-300 hover:border-pink-500 hover:text-pink-400"
                      >
                        <Download className="h-3 w-3" />
                        <span>Save</span>
                      </button>
                    </summary>
                    <pre className="overflow-x-auto border-t border-white/10 bg-black/50 p-4 text-[10.5px] leading-relaxed text-zinc-300">
                      {content}
                    </pre>
                  </details>
                ))}
              </div>
            ) : latestArtifact ? (
              <pre className="whitespace-pre-wrap break-words rounded border border-white/10 bg-[#07050C] p-4 text-zinc-300">{latestArtifact}</pre>
            ) : (
              <div className="grid h-full place-items-center text-zinc-500">No artifact snapshot emitted yet.</div>
            )}
          </div>
        )}

        {tab === "diff" && (
          <div className="h-[520px] overflow-auto p-6 font-mono text-[11px] leading-relaxed">
            {artifacts.length < 2 ? (
              <div className="grid h-full place-items-center text-zinc-500">
                Diff appears after at least two artifact snapshots are emitted.
              </div>
            ) : (
              diffRows.map((row, i) => (
                <div
                  key={`${i}-${row.text}`}
                  className={cn(
                    "whitespace-pre-wrap break-words px-2.5 py-0.5 rounded-sm",
                    row.type === "add"
                      ? "bg-emerald-500/10 text-emerald-300 font-medium"
                      : row.type === "remove"
                        ? "bg-red-500/10 text-red-300 font-medium"
                        : "text-zinc-500",
                  )}
                >
                  <span className="mr-2 select-none font-bold text-zinc-600">
                    {row.type === "add" ? "+" : row.type === "remove" ? "-" : " "}
                  </span>
                  {row.text}
                </div>
              ))
            )}
          </div>
        )}

        {tab === "preview" && (
          <div className="h-[520px] bg-[#050308]">
            {previewUrl ? (
              <iframe
                title={`${displayName} preview`}
                src={previewUrl}
                className="h-full w-full border-0 bg-white"
              />
            ) : (
              <div className="grid h-full place-items-center px-8 text-center font-mono">
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-zinc-500">
                    Preview unavailable
                  </div>
                  <div className="mt-2 max-w-[42ch] text-[11px] leading-5 text-zinc-600">
                    A preview is shown only when the runtime emits a valid preview URL for this fighter workspace.
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
