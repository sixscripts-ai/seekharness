/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Braces,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  FileCode2,
  GitCompare,
  Layers3,
  Lock,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Trophy,
  Wrench,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type PaneArtifact = {
  phase: string;
  artifact: string;
  t: number;
  kind?: "artifact" | "transcript" | "action_log" | string;
};

type Props = {
  modelId: string;
  label: string;
  role?: string;
  code: string;
  status: string;
  tok?: string;
  color?: "accent" | "accent2" | "rival" | "neutral" | "success" | "danger";
  artifactMeta: string;
  history?: PaneArtifact[];
  events?: PaneArtifact[];
  previewUrl?: string;
  win?: boolean;
  winText?: string;
  className?: string;
  protectedFiles?: string[];
};

type Tab = "terminal" | "artifact" | "diff" | "tools" | "versions" | "preview";

type Parsed = {
  files?: Record<string, string>;
  chosen_skills?: string[];
  theory?: string;
  outcome?: string;
  steps?: number;
};

type DiffRow = {
  type: "same" | "add" | "remove";
  text: string;
  oldNo?: number;
  newNo?: number;
};

type EventView = {
  action: string;
  target: string;
  state: string;
  duration: string;
  detail: string;
};

function tryParse(code: string): Parsed | null {
  try {
    const j = JSON.parse(code);
    if (j && typeof j === "object" && (j.files || j.chosen_skills || j.theory))
      return j as Parsed;
    if (typeof j === "string") {
      const inner = JSON.parse(j);
      if (inner && typeof inner === "object" && inner.files)
        return inner as Parsed;
    }
  } catch {}
  return null;
}

function stringifyCompact(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value ?? "");
  }
}

function parseExecutionEvent(item: PaneArtifact): EventView {
  let raw: any = null;
  try {
    raw = JSON.parse(item.artifact);
  } catch {}

  if (raw && typeof raw === "object") {
    const action = String(
      raw.action || raw.tool || raw.type || raw.event || item.kind || "event",
    ).toUpperCase();
    const target = String(
      raw.target ||
        raw.path ||
        raw.command ||
        raw.file ||
        raw.name ||
        raw.phase ||
        item.phase ||
        "runtime",
    );
    const rawState = raw.status || raw.state || raw.outcome || raw.ok;
    const state =
      rawState === true
        ? "ok"
        : rawState === false
          ? "failed"
          : String(rawState || "done");
    const durationValue =
      raw.duration_ms ?? raw.latency_ms ?? raw.elapsed_ms ?? raw.duration;
    const duration =
      durationValue === undefined
        ? ""
        : typeof durationValue === "number"
          ? `${Math.round(durationValue)}ms`
          : String(durationValue);
    const detail = stringifyCompact(
      raw.result ??
        raw.output ??
        raw.message ??
        raw.detail ??
        raw.summary ??
        "",
    );
    return { action, target, state, duration, detail };
  }

  const trimmed = item.artifact.trim();
  const firstLine = trimmed.split("\n", 1)[0] || "runtime event";
  const [head, ...rest] = firstLine.split(/\s+/);
  return {
    action: (head || item.kind || "event").toUpperCase(),
    target: rest.join(" ") || item.phase || "runtime",
    state: "done",
    duration: "",
    detail: trimmed === firstLine ? "" : trimmed.slice(firstLine.length).trim(),
  };
}

function lineDiff(previous: string, current: string): DiffRow[] {
  if (!previous && !current) return [];
  if (!previous)
    return current
      .split("\n")
      .map((text, i) => ({ type: "add", text, newNo: i + 1 }));
  if (!current)
    return previous
      .split("\n")
      .map((text, i) => ({ type: "remove", text, oldNo: i + 1 }));

  const a = previous.split("\n").slice(0, 220);
  const b = current.split("\n").slice(0, 220);
  const width = b.length + 1;
  const dp = new Uint16Array((a.length + 1) * width);

  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      const idx = i * width + j;
      dp[idx] =
        a[i] === b[j]
          ? dp[(i + 1) * width + j + 1] + 1
          : Math.max(dp[(i + 1) * width + j], dp[i * width + j + 1]);
    }
  }

  const out: DiffRow[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i], oldNo: i + 1, newNo: j + 1 });
      i += 1;
      j += 1;
    } else if (dp[(i + 1) * width + j] >= dp[i * width + j + 1]) {
      out.push({ type: "remove", text: a[i], oldNo: i + 1 });
      i += 1;
    } else {
      out.push({ type: "add", text: b[j], newNo: j + 1 });
      j += 1;
    }
  }
  while (i < a.length) {
    out.push({ type: "remove", text: a[i], oldNo: i + 1 });
    i += 1;
  }
  while (j < b.length) {
    out.push({ type: "add", text: b[j], newNo: j + 1 });
    j += 1;
  }
  return out;
}

function timeLabel(t: number): string {
  if (!t) return "—";
  return new Date(t).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatFighterName(id: string): string {
  if (!id) return "Agent";
  const lower = id.toLowerCase();
  if (lower.includes("claude") || lower.includes("laguna") || lower.includes("sonnet")) return "Claude 3.7 Sonnet";
  if (lower.includes("deepseek") || lower.includes("6a85") || lower.includes("r1")) return "DeepSeek R1";
  if (lower.includes("o3") || lower.includes("gpt") || lower.includes("openai")) return "OpenAI o3-mini";
  if (lower.includes("kimi") || lower.includes("moonshot")) return "Moonshot Kimi-K3";
  if (lower.includes("gemini") || lower.includes("flash")) return "Gemini 2.5 Pro";
  if (id.startsWith("host:")) {
    const clean = id.replace("host:", "").replace(/[-_]/g, " ");
    return clean
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }
  if (id.length > 16) return `Agent ${id.slice(0, 8)}`;
  return id;
}

export default function CodePane({
  modelId,
  label,
  role,
  code,
  status,
  tok,
  artifactMeta,
  history = [],
  events = [],
  previewUrl,
  win,
  winText = "winner",
  className,
  protectedFiles = [],
}: Props) {
  const [tab, setTab] = useState<Tab>("terminal");
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [followTail, setFollowTail] = useState(true);
  const termScrollRef = useRef<HTMLDivElement | null>(null);

  const versions = useMemo(() => {
    const artifactEvents = history.filter(
      (item) => !item.kind || item.kind === "artifact",
    );
    if (artifactEvents.length) return artifactEvents;
    if (code)
      return [
        {
          phase: "current",
          artifact: code,
          t: 0,
          kind: "artifact",
        } satisfies PaneArtifact,
      ];
    return [];
  }, [history, code]);

  const activeVersionIndex =
    selectedVersion !== null && versions[selectedVersion]
      ? selectedVersion
      : Math.max(versions.length - 1, 0);
  const activeVersion = versions[activeVersionIndex];
  const activeArtifact = activeVersion?.artifact || code || "";
  const previousArtifact =
    activeVersionIndex > 0
      ? versions[activeVersionIndex - 1]?.artifact || ""
      : "";
  const parsed = useMemo(() => tryParse(activeArtifact), [activeArtifact]);
  const files = parsed?.files || null;
  const fileList = useMemo(
    () => (files ? Object.keys(files).sort() : []),
    [files],
  );
  const activeFile =
    selectedFile && files?.[selectedFile] !== undefined
      ? selectedFile
      : fileList[0] || null;
  const displayCode = activeFile && files ? files[activeFile] : activeArtifact;
  const lines = displayCode ? displayCode.split("\n") : [];
  const diffRows = useMemo(
    () => lineDiff(previousArtifact, activeArtifact),
    [previousArtifact, activeArtifact],
  );

  const toolEvents = useMemo(
    () => events.filter((item) => item.kind === "action_log"),
    [events],
  );

  const terminalLogs = useMemo(() => {
    return events.filter(
      (item) =>
        item.kind === "transcript" ||
        item.kind === "action_log" ||
        item.kind === "artifact",
    );
  }, [events]);

  // Auto-scroll terminal when followTail is enabled
  useEffect(() => {
    if (followTail && termScrollRef.current) {
      termScrollRef.current.scrollTop = termScrollRef.current.scrollHeight;
    }
  }, [terminalLogs, followTail]);

  async function copyTerminalOutput() {
    const text = terminalLogs.map((e) => `[${timeLabel(e.t)}] ${e.artifact}`).join("\n");
    if (!text && !activeArtifact) return;
    await navigator.clipboard.writeText(text || activeArtifact);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  function downloadCurrentArtifact() {
    if (!displayCode) return;
    const filename = activeFile || `${modelId.replace(/[^a-zA-Z0-9_-]/g, "_")}_artifact.py`;
    const blob = new Blob([displayCode], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  const isProtectedFile = (filename: string | null) => {
    if (!filename) return false;
    if (protectedFiles && protectedFiles.includes(filename)) return true;
    if (role === "breaker" && (filename === "auth.py" || filename.includes("auth"))) return true;
    if (filename.startsWith("test_") || filename.includes("harness")) return true;
    return false;
  };
  const activeIsProtected = isProtectedFile(activeFile);

  const fighterDisplayName = formatFighterName(label || modelId);
  const isWinner = Boolean(win);
  const promptUser = role === "breaker" ? "breaker" : "builder";

  return (
    <section
      className={cn(
        "flex h-[580px] min-h-0 flex-col overflow-hidden rounded-xl border bg-[#030206] shadow-2xl transition-all",
        isWinner
          ? "border-pink-500 shadow-[0_0_35px_rgba(255,0,160,0.25)]"
          : "border-pink-500/25",
        className,
      )}
      aria-label={`${fighterDisplayName} execution console`}
    >
      {/* TERMINAL HEADER TITLEBAR */}
      <header className="flex min-h-[50px] items-center justify-between gap-3 border-b border-pink-500/20 bg-[#0C0914] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          {/* Terminal Window Dots */}
          <div className="flex items-center gap-1.5">
            <div className="h-2.5 w-2.5 rounded-full bg-pink-500" />
            <div className="h-2.5 w-2.5 rounded-full bg-pink-500/40" />
            <div className="h-2.5 w-2.5 rounded-full bg-pink-500/20" />
          </div>

          <div className="flex min-w-0 items-center gap-2">
            {role && (
              <span
                className={cn(
                  "rounded px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider",
                  role === "builder"
                    ? "border border-pink-500 bg-pink-500/15 text-pink-400"
                    : "border border-white/30 bg-white/10 text-white",
                )}
              >
                {role}
              </span>
            )}
            <span className="truncate text-[13px] font-bold tracking-tight text-white">
              {fighterDisplayName}
            </span>
            <span className="hidden truncate font-mono text-[9px] text-zinc-500 sm:inline">
              ({modelId})
            </span>
          </div>

          {isWinner && (
            <span className="inline-flex items-center gap-1 rounded border border-pink-500 bg-pink-500/20 px-2 py-0.5 font-mono text-[9px] font-black uppercase tracking-wider text-pink-400">
              <Trophy className="h-3 w-3" />
              {winText}
            </span>
          )}
        </div>

        {/* VIEW TABS & QUICK ACTIONS */}
        <div className="flex shrink-0 items-center gap-1.5">
          <div className="flex items-center rounded-lg bg-[#07040B] p-0.5 border border-white/10">
            <button
              type="button"
              onClick={() => setTab("terminal")}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded px-2.5 font-mono text-[10px] font-bold uppercase tracking-wider transition-colors",
                tab === "terminal"
                  ? "bg-pink-500 text-black"
                  : "text-zinc-400 hover:text-white",
              )}
            >
              <Terminal className="h-3 w-3" />
              Terminal
            </button>
            <button
              type="button"
              onClick={() => setTab("artifact")}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded px-2.5 font-mono text-[10px] font-bold uppercase tracking-wider transition-colors",
                tab === "artifact"
                  ? "bg-pink-500 text-black"
                  : "text-zinc-400 hover:text-white",
              )}
            >
              <FileCode2 className="h-3 w-3" />
              Files{fileList.length ? ` (${fileList.length})` : ""}
            </button>
            <button
              type="button"
              onClick={() => setTab("diff")}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded px-2.5 font-mono text-[10px] font-bold uppercase tracking-wider transition-colors",
                tab === "diff"
                  ? "bg-pink-500 text-black"
                  : "text-zinc-400 hover:text-white",
              )}
            >
              <GitCompare className="h-3 w-3" />
              Diff
            </button>
          </div>

          <button
            type="button"
            onClick={copyTerminalOutput}
            className="grid h-7 w-7 place-items-center rounded border border-white/15 bg-white/5 text-zinc-400 transition-colors hover:border-pink-500 hover:text-pink-400"
            title="Copy Logs"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-pink-400" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            type="button"
            onClick={downloadCurrentArtifact}
            disabled={!displayCode}
            className="grid h-7 w-7 place-items-center rounded border border-white/15 bg-white/5 text-zinc-400 transition-colors hover:border-pink-500 hover:text-pink-400 disabled:opacity-30"
            title="Download Artifact"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* BODY CONTENT AREA */}
      <div className="relative min-h-0 flex-1 overflow-hidden bg-[#020104]">
        {/* ================================================================= */}
        {/* TAB: TERMINAL (HERO LIVE STREAMING REPL) */}
        {/* ================================================================= */}
        {tab === "terminal" && (
          <div
            ref={termScrollRef}
            className="h-full overflow-y-auto p-4 font-mono text-[11.5px] leading-relaxed text-zinc-300"
          >
            <div className="text-zinc-500">
              [modal-sandbox] Container booted: Python 3.11 (Ubuntu 22.04 LTS)
            </div>
            <div className="text-zinc-500">
              [modal-sandbox] Mounted workspace: /workspace/duel-root
            </div>

            {terminalLogs.length === 0 ? (
              <div className="mt-4">
                <div>
                  <span className="font-bold text-pink-500">
                    {promptUser}@seek-arena:~$
                  </span>{" "}
                  <span className="text-zinc-400">
                    {status === "running"
                      ? "Awaiting first execution step…"
                      : "No terminal logs recorded for this contestant."}
                  </span>
                  {status === "running" && (
                    <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse bg-pink-500 align-middle" />
                  )}
                </div>
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                {terminalLogs.map((item, idx) => {
                  let parsedJson: any = null;
                  try {
                    parsedJson = JSON.parse(item.artifact);
                  } catch {}

                  const isTool = item.kind === "action_log";
                  const isArtifact = item.kind === "artifact";

                  if (parsedJson && typeof parsedJson === "object") {
                    const cmd =
                      parsedJson.command ||
                      parsedJson.action ||
                      parsedJson.tool ||
                      "step";
                    const stdout =
                      parsedJson.output ||
                      parsedJson.result ||
                      parsedJson.stdout ||
                      "";
                    const hasError =
                      parsedJson.status === "failed" ||
                      /fail|error/i.test(parsedJson.status || "");

                    return (
                      <div key={`${item.t}-${idx}`} className="space-y-1">
                        <div>
                          <span className="font-bold text-pink-500">
                            {promptUser}@seek-arena:~$
                          </span>{" "}
                          <span className="font-semibold text-white">
                            {cmd}
                          </span>
                        </div>
                        {stdout && (
                          <div
                            className={cn(
                              "whitespace-pre-wrap rounded bg-[#07050C] p-2 pl-3 border-l-2 font-mono text-[11px]",
                              hasError
                                ? "border-red-500 text-red-300"
                                : "border-pink-500/40 text-zinc-300",
                            )}
                          >
                            {stdout}
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (isArtifact) {
                    return (
                      <div key={`${item.t}-${idx}`} className="space-y-1">
                        <div>
                          <span className="font-bold text-pink-500">
                            {promptUser}@seek-arena:~$
                          </span>{" "}
                          <span className="font-semibold text-white">
                            commit_artifact
                          </span>
                        </div>
                        <div className="rounded border-l-2 border-emerald-500 bg-[#07050C] p-2 pl-3 text-emerald-400">
                          ✔ Committed artifact snapshot ({item.artifact.length} bytes)
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div key={`${item.t}-${idx}`} className="space-y-1">
                      <div>
                        <span className="font-bold text-pink-500">
                          {promptUser}@seek-arena:~$
                        </span>{" "}
                        <span className="text-zinc-200">{item.artifact}</span>
                      </div>
                    </div>
                  );
                })}

                {status === "running" && (
                  <div className="pt-2">
                    <span className="font-bold text-pink-500">
                      {promptUser}@seek-arena:~$
                    </span>
                    <span className="ml-1 inline-block h-3.5 w-1.5 animate-pulse bg-pink-500 align-middle" />
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ================================================================= */}
        {/* TAB: ARTIFACT / FILES EXPLORER */}
        {/* ================================================================= */}
        {tab === "artifact" && (
          <div className="flex h-full min-h-0 flex-col">
            {activeIsProtected && (
              <div className="flex items-center gap-2 border-b border-pink-500/30 bg-pink-500/10 px-3 py-1.5 font-mono text-[10px] text-pink-400">
                <Lock className="h-3 w-3 shrink-0" />
                <span className="font-bold">PROTECTED HARNESS FILE (READ-ONLY)</span>
                <span className="hidden text-zinc-400 sm:inline">
                  — Auto-restored from frozen snapshot if modified
                </span>
              </div>
            )}
            <div className="flex h-full min-h-0 flex-1">
              {files && fileList.length > 0 && (
                <aside className="w-[170px] shrink-0 overflow-y-auto border-r border-pink-500/20 bg-[#06040A] p-2.5">
                  <div className="mb-2 flex items-center justify-between font-mono text-[8px] uppercase tracking-wider text-zinc-500">
                    <span>WORK/</span>
                    <span className="font-bold text-pink-400">FS ROOT</span>
                  </div>
                  <div className="space-y-0.5">
                    {fileList.map((file) => {
                      const locked = isProtectedFile(file);
                      return (
                        <button
                          key={file}
                          type="button"
                          onClick={() => setSelectedFile(file)}
                          className={cn(
                            "flex w-full items-center justify-between gap-1.5 rounded px-2 py-1.5 text-left font-mono text-[10px] transition-colors",
                            activeFile === file
                              ? "bg-pink-500/15 text-pink-300 font-bold"
                              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200",
                          )}
                        >
                          <div className="flex items-center gap-1.5 truncate">
                            <FileCode2 className="h-3 w-3 shrink-0" />
                            <span className="truncate">{file}</span>
                          </div>
                          {locked && (
                            <span title="Protected file">
                              <Lock className="h-2.5 w-2.5 shrink-0 text-pink-400" />
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </aside>
              )}
              <div className="flex min-w-0 flex-1">
                <div className="w-10 shrink-0 select-none overflow-hidden border-r border-white/5 py-3 pr-2 text-right">
                  {lines.map((_, i) => (
                    <div
                      key={i}
                      className="font-mono text-[9px] leading-5 text-zinc-600"
                    >
                      {i + 1}
                    </div>
                  ))}
                </div>
                <pre className="h-full min-w-0 flex-1 overflow-auto p-3 font-mono text-[11px] leading-5 text-zinc-200 whitespace-pre-wrap break-words">
                  <code>{displayCode || "// No artifact payload received yet."}</code>
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* TAB: DIFF VIEWER */}
        {/* ================================================================= */}
        {tab === "diff" && (
          <div className="h-full overflow-auto p-2 font-mono text-[10px] leading-5">
            {diffRows.length === 0 ? (
              <div className="grid h-full place-items-center text-center text-zinc-500">
                <div>
                  <GitCompare className="mx-auto h-6 w-6 text-zinc-600" />
                  <div className="mt-2 font-mono text-[10px] uppercase tracking-wider">
                    No version diff available
                  </div>
                </div>
              </div>
            ) : (
              <div className="min-w-[500px]">
                {diffRows.map((row, index) => (
                  <div
                    key={`${index}-${row.type}`}
                    className={cn(
                      "grid grid-cols-[40px_40px_20px_1fr] border-b border-white/[0.03] px-2 py-0.5",
                      row.type === "add" && "bg-emerald-500/10 text-emerald-300",
                      row.type === "remove" && "bg-red-500/10 text-red-300",
                    )}
                  >
                    <span className="text-right text-zinc-600">{row.oldNo || ""}</span>
                    <span className="text-right text-zinc-600">{row.newNo || ""}</span>
                    <span className="text-center font-bold">
                      {row.type === "add" ? "+" : row.type === "remove" ? "−" : " "}
                    </span>
                    <span className="whitespace-pre-wrap break-words px-2 text-zinc-200">
                      {row.text || " "}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* CONTAINER TELEMETRY & FOOTER HUD */}
      <footer className="flex min-h-[36px] items-center justify-between border-t border-pink-500/20 bg-[#08060D] px-4 py-1.5 font-mono text-[10px] text-zinc-400">
        <div className="flex items-center gap-3">
          <span>MEM: 512MB / 2048MB</span>
          <span className="text-zinc-600">•</span>
          <span>{toolEvents.length} Tool Calls</span>
          <span className="text-zinc-600">•</span>
          <span className="font-bold text-emerald-400">{tok || "68 tok/s"}</span>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setFollowTail(!followTail)}
            className={cn(
              "flex items-center gap-1 rounded px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider transition-colors",
              followTail
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/40"
                : "bg-white/5 text-zinc-500 border border-white/10 hover:text-zinc-300",
            )}
          >
            <span>⬇</span> Follow Tail
          </button>
          <span
            className={cn(
              "font-bold uppercase tracking-wider",
              isWinner ? "text-pink-400" : "text-zinc-400",
            )}
          >
            {isWinner ? `🏆 1.0 (${winText})` : artifactMeta || "ARTIFACT COMPLETED"}
          </span>
        </div>
      </footer>
    </section>
  );
}
