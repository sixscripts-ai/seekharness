import { useMemo, useState } from "react";
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

type Tab = "artifact" | "diff" | "output" | "tools" | "versions" | "preview";
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

const DOT: Record<string, string> = {
  accent: "bg-accent",
  accent2: "bg-accent",
  rival: "bg-accent",
  neutral: "bg-zinc-400",
  success: "bg-success",
  danger: "bg-danger",
};

const TABS: Array<{ key: Tab; label: string; icon: typeof Braces }> = [
  { key: "artifact", label: "Artifact", icon: Braces },
  { key: "diff", label: "Diff", icon: GitCompare },
  { key: "output", label: "Output", icon: Terminal },
  { key: "tools", label: "Tools", icon: Wrench },
  { key: "versions", label: "Versions", icon: Layers3 },
  { key: "preview", label: "Preview", icon: ExternalLink },
];

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

export default function CodePane({
  modelId,
  label,
  role,
  code,
  status,
  tok,
  color = "neutral",
  artifactMeta,
  history = [],
  events = [],
  previewUrl,
  win,
  winText,
  className,
  protectedFiles = [],
}: Props) {
  const [tab, setTab] = useState<Tab>("artifact");
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const dot = DOT[color] || DOT.neutral;

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
  const lines = displayCode.split("\n");
  const diffRows = useMemo(
    () => lineDiff(previousArtifact, activeArtifact),
    [previousArtifact, activeArtifact],
  );

  const toolEvents = useMemo(
    () => events.filter((item) => item.kind === "action_log").slice(-80),
    [events],
  );
  const outputEvents = useMemo(
    () =>
      events
        .filter(
          (item) => item.kind === "transcript" || item.kind === "action_log",
        )
        .slice(-80),
    [events],
  );
  const latestEvent = events[events.length - 1];
  const isLatest =
    !versions.length || activeVersionIndex === versions.length - 1;

  async function copyArtifact() {
    if (!activeArtifact) return;
    await navigator.clipboard.writeText(activeArtifact);
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

  function selectVersion(index: number) {
    setSelectedVersion(index);
    setSelectedFile(null);
    setTab("artifact");
  }

  return (
    <section
      className={cn(
        "card flex h-[560px] min-h-0 flex-col overflow-hidden bg-surface",
        (color === "accent" ||
          color === "accent2" ||
          color === "rival" ||
          color === "success") &&
          "border-l-2 border-l-accent",
        className,
      )}
      aria-label={`${label} execution inspector`}
    >
      <header className="flex min-h-[64px] items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-borderStrong bg-surface2 font-mono text-[11px] font-semibold">
            {modelId[0]?.toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <div className="truncate text-[12px] font-semibold tracking-[-0.01em]">
                {label}
              </div>
              {role && (
                <span className="hidden rounded-full border border-border px-2 py-0.5 font-mono text-[8px] uppercase tracking-[0.09em] text-muted sm:inline">
                  {role}
                </span>
              )}
            </div>
            <div className="mt-0.5 truncate font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
              {modelId}
              {tok ? ` / ${tok}` : ""}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={downloadCurrentArtifact}
            disabled={!displayCode}
            className="grid h-8 w-8 place-items-center rounded-md border border-border bg-surface2 text-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-40"
            aria-label="Download current artifact file"
            title="Download current artifact file"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={copyArtifact}
            disabled={!activeArtifact}
            className="grid h-8 w-8 place-items-center rounded-md border border-border bg-surface2 text-muted transition-colors hover:border-borderStrong hover:text-foreground disabled:opacity-40"
            aria-label="Copy current artifact"
            title="Copy current artifact"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
          <span className="flex items-center gap-1.5 rounded-full border border-border bg-background/70 px-2 py-1">
            <span
              className={`h-1.5 w-1.5 rounded-full ${dot} ${status === "running" ? "animate-pulse" : ""}`}
            />
            <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted">
              {status === "running" ? "live" : status}
            </span>
          </span>
        </div>
      </header>

      <div className="flex min-h-[44px] items-center justify-between gap-2 border-b border-border bg-surface2/35 px-2">
        <div
          className="flex min-w-0 items-center gap-0.5 overflow-x-auto"
          role="tablist"
          aria-label="Inspector views"
        >
          {TABS.map(({ key, label: tabLabel, icon: Icon }) => {
            if (key === "preview" && !previewUrl) return null;
            const active = tab === key;
            const count =
              key === "versions"
                ? versions.length
                : key === "tools"
                  ? toolEvents.length
                  : undefined;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(key)}
                className={`flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 font-mono text-[9px] uppercase tracking-[0.07em] transition-colors ${active ? "bg-background text-foreground shadow-sm" : "text-muted hover:text-foreground"}`}
              >
                <Icon className="h-3.5 w-3.5" />
                {tabLabel}
                {count !== undefined && count > 0 && (
                  <span className="text-[8px] opacity-60">{count}</span>
                )}
              </button>
            );
          })}
        </div>
        {!isLatest && versions.length > 0 && (
          <button
            type="button"
            onClick={() => {
              setSelectedVersion(null);
              setSelectedFile(null);
            }}
            className="shrink-0 px-2 font-mono text-[8px] uppercase tracking-[0.08em] text-accent hover:underline"
          >
            jump to latest
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 bg-code flex flex-col">
        {activeIsProtected && tab === "artifact" && (
          <div className="flex items-center gap-2 border-b border-accent/30 bg-accent/10 px-3 py-1.5 font-mono text-[10px] text-accent">
            <Lock className="h-3 w-3 shrink-0" />
            <span className="font-bold">PROTECTED HARNESS FILE (READ-ONLY)</span>
            <span className="hidden text-muted sm:inline">— Auto-restored from frozen snapshot if modified</span>
          </div>
        )}
        {tab === "artifact" && (
          <div className="flex h-full min-h-0 flex-1">
            {files && fileList.length > 0 && (
              <aside
                className="hidden w-[148px] shrink-0 overflow-auto border-r border-codeBorder bg-code/70 p-2 sm:block"
                aria-label="Artifact files"
              >
                <div className="mb-2 font-mono text-[8px] uppercase tracking-[0.12em] text-lineNo flex items-center justify-between">
                  <span>work/</span>
                  <span className="text-[7px] text-accent">FS ROOT</span>
                </div>
                <div className="space-y-0.5">
                  {fileList.map((file) => {
                    const locked = isProtectedFile(file);
                    return (
                      <button
                        key={file}
                        type="button"
                        onClick={() => setSelectedFile(file)}
                        className={`flex w-full items-center justify-between gap-1 rounded px-1.5 py-1 text-left font-mono text-[9px] ${
                          activeFile === file
                            ? "bg-white/[0.08] text-codeFg"
                            : "text-lineNo hover:bg-white/[0.04] hover:text-codeFg"
                        }`}
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          <FileCode2 className="h-3 w-3 shrink-0" />
                          <span className="truncate">{file}</span>
                        </div>
                        {locked && (
                          <span title="Protected harness file (read-only)">
                            <Lock className="h-2.5 w-2.5 shrink-0 text-accent" />
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </aside>
            )}
            <div className="flex min-w-0 flex-1">
              <div className="w-11 shrink-0 select-none overflow-hidden border-r border-codeBorder py-3 pr-2 text-right">
                {lines.map((_, i) => (
                  <div
                    key={i}
                    className="font-mono text-[9px] leading-5 text-lineNo"
                  >
                    {i + 1}
                  </div>
                ))}
              </div>
              <pre className="h-full min-w-0 flex-1 overflow-auto p-3 font-mono text-[11px] leading-5 text-codeFg whitespace-pre-wrap break-words">
                <code>
                  {displayCode || "// Waiting for the first artifact…"}
                </code>
              </pre>
            </div>
          </div>
        )}

        {tab === "diff" && (
          <div className="h-full overflow-auto">
            {versions.length < 2 ? (
              <EmptyState
                icon={GitCompare}
                title="No previous version"
                detail="A diff appears after this agent submits another artifact."
              />
            ) : (
              <div className="min-w-[560px] py-2 font-mono text-[10px] leading-5">
                <div className="sticky top-0 z-10 flex items-center justify-between border-b border-codeBorder bg-code/95 px-3 py-2 text-[9px] uppercase tracking-[0.08em] text-lineNo backdrop-blur">
                  <span>
                    v{activeVersionIndex || 1} → v{activeVersionIndex + 1}
                  </span>
                  <span>
                    {diffRows.filter((r) => r.type === "add").length} additions
                    / {diffRows.filter((r) => r.type === "remove").length}{" "}
                    removals
                  </span>
                </div>
                {diffRows.map((row, index) => (
                  <div
                    key={`${index}-${row.type}`}
                    className={`grid grid-cols-[42px_42px_20px_1fr] border-b border-codeBorder/30 px-2 ${row.type === "add" ? "bg-emerald-500/[0.09]" : row.type === "remove" ? "bg-red-500/[0.09]" : ""}`}
                  >
                    <span className="select-none text-right text-lineNo">
                      {row.oldNo || ""}
                    </span>
                    <span className="select-none text-right text-lineNo">
                      {row.newNo || ""}
                    </span>
                    <span
                      className={`select-none text-center ${row.type === "add" ? "text-emerald-400" : row.type === "remove" ? "text-red-400" : "text-lineNo"}`}
                    >
                      {row.type === "add"
                        ? "+"
                        : row.type === "remove"
                          ? "−"
                          : " "}
                    </span>
                    <span className="whitespace-pre-wrap break-words px-2 text-codeFg">
                      {row.text || " "}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "output" && (
          <div className="h-full overflow-auto p-3">
            {outputEvents.length ? (
              <div className="space-y-1.5">
                {outputEvents.map((item, index) => (
                  <div
                    key={`${item.t}-${index}`}
                    className="grid grid-cols-[64px_72px_1fr] gap-2 rounded-md border border-codeBorder bg-[#0b0d0f] px-2.5 py-2 font-mono text-[9px] leading-4"
                  >
                    <span className="text-lineNo">{timeLabel(item.t)}</span>
                    <span className="uppercase tracking-[0.08em] text-accent">
                      {item.kind || "output"}
                    </span>
                    <span className="whitespace-pre-wrap break-words text-codeFg/85">
                      {item.artifact}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Terminal}
                title="No runtime output yet"
                detail="Build, test, or transcript output will appear here without growing the page."
              />
            )}
          </div>
        )}

        {tab === "tools" && (
          <div className="h-full overflow-auto p-3">
            {toolEvents.length ? (
              <div className="space-y-1.5">
                {toolEvents.map((item, index) => {
                  const event = parseExecutionEvent(item);
                  const failed = /fail|error|denied/i.test(event.state);
                  return (
                    <div
                      key={`${item.t}-${index}`}
                      className="rounded-md border border-codeBorder bg-[#0b0d0f] px-3 py-2.5"
                    >
                      <div className="grid grid-cols-[64px_74px_minmax(0,1fr)_auto] items-center gap-2 font-mono text-[9px]">
                        <span className="text-lineNo">{timeLabel(item.t)}</span>
                        <span className="uppercase tracking-[0.08em] text-accent">
                          {event.action}
                        </span>
                        <span className="truncate text-codeFg">
                          {event.target}
                        </span>
                        <span
                          className={`flex items-center gap-1 uppercase ${failed ? "text-red-400" : "text-emerald-400"}`}
                        >
                          {failed ? (
                            <XCircle className="h-3 w-3" />
                          ) : (
                            <CheckCircle2 className="h-3 w-3" />
                          )}
                          {event.state}
                          {event.duration ? ` · ${event.duration}` : ""}
                        </span>
                      </div>
                      {event.detail && (
                        <div className="mt-2 border-t border-codeBorder pt-2 font-mono text-[9px] leading-4 text-lineNo break-words">
                          {event.detail.slice(0, 900)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                icon={Wrench}
                title="No tool activity yet"
                detail="Structured sandbox actions will appear here when the executor emits action_log events."
              />
            )}
          </div>
        )}

        {tab === "versions" && (
          <div className="h-full overflow-auto p-3">
            {versions.length ? (
              <div className="space-y-2">
                {[...versions].reverse().map((item, reverseIndex) => {
                  const index = versions.length - 1 - reverseIndex;
                  const latest = index === versions.length - 1;
                  const selected = index === activeVersionIndex;
                  return (
                    <button
                      key={`${item.t}-${index}`}
                      type="button"
                      onClick={() => selectVersion(index)}
                      className={`flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors ${selected ? "border-accent/50 bg-accent/5" : "border-codeBorder bg-[#0b0d0f] hover:border-borderStrong"}`}
                    >
                      <div
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${latest ? "bg-accent" : "bg-lineNo"}`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-mono text-[9px] font-medium uppercase tracking-[0.08em] text-codeFg">
                            v{index + 1} / {item.phase || "artifact"}
                          </span>
                          <span className="flex items-center gap-1 font-mono text-[8px] text-lineNo">
                            <Clock3 className="h-3 w-3" />
                            {timeLabel(item.t)}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 font-mono text-[9px] leading-4 text-lineNo">
                          {item.artifact.replace(/\s+/g, " ").slice(0, 220) ||
                            "empty artifact"}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                icon={Layers3}
                title="No versions yet"
                detail="Each submitted artifact becomes a selectable version in this fixed panel."
              />
            )}
          </div>
        )}

        {tab === "preview" && (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-codeBorder bg-code/70 px-3 py-2">
              <span className="truncate font-mono text-[9px] text-lineNo">
                {previewUrl}
              </span>
              <div className="flex shrink-0 items-center gap-1.5">
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 rounded border border-border bg-surface2 px-2 py-1 font-mono text-[8px] uppercase tracking-[0.08em] text-accent hover:border-borderStrong"
                >
                  <ExternalLink className="h-3 w-3" /> open
                </a>
                <button
                  type="button"
                  onClick={() => setPreviewKey((k) => k + 1)}
                  className="rounded border border-border bg-surface2 px-2 py-1 font-mono text-[8px] uppercase tracking-[0.08em] text-muted hover:border-borderStrong hover:text-foreground"
                >
                  reload
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 bg-[#0b0d0f]">
              <iframe
                key={previewKey}
                src={previewUrl}
                title={`${label} preview`}
                className="h-full w-full border-0"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              />
            </div>
          </div>
        )}
      </div>

      <footer className="flex min-h-[44px] items-center justify-between gap-3 border-t border-border bg-surface px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="truncate font-mono text-[8px] text-muted">
            {artifactMeta}
          </span>
          {versions.length > 0 && (
            <span className="hidden font-mono text-[8px] text-muted sm:inline">
              v{activeVersionIndex + 1}/{versions.length}
            </span>
          )}
          {toolEvents.length > 0 && (
            <span className="hidden font-mono text-[8px] text-muted md:inline">
              {toolEvents.length} tool calls
            </span>
          )}
        </div>
        <span
          className={`flex shrink-0 items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.06em] ${win ? "text-warn" : status === "running" ? "text-accent" : "text-muted"}`}
        >
          {win ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : status === "running" ? (
            <Radio className="h-3.5 w-3.5" />
          ) : null}
          {win
            ? winText || "win condition"
            : latestEvent
              ? `${latestEvent.kind || "event"} · ${latestEvent.phase}`
              : status === "running"
                ? "receiving"
                : "idle"}
        </span>
      </footer>
    </section>
  );
}

function EmptyState({
  icon: Icon,
  title,
  detail,
}: {
  icon: typeof Braces;
  title: string;
  detail: string;
}) {
  return (
    <div className="grid h-full place-items-center p-8">
      <div className="max-w-[280px] text-center">
        <div className="mx-auto grid h-9 w-9 place-items-center rounded-lg border border-codeBorder bg-[#0b0d0f] text-lineNo">
          <Icon className="h-4 w-4" />
        </div>
        <div className="mt-3 text-[11px] font-medium text-codeFg">{title}</div>
        <p className="mt-1 text-[10px] leading-5 text-lineNo">{detail}</p>
      </div>
    </div>
  );
}
