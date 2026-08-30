import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileCode2, GitCompare, TerminalSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BattleStreamItem, SkillActivity } from "./types";
import {
  artifactFiles,
  humanSkillLabel,
  lineDiff,
  parseAction,
  timeLabel,
} from "./utils";

type FighterState = "waiting" | "starting" | "running" | "complete" | "failed";
type Tab = "terminal" | "files" | "diff" | "preview";

type Props = {
  modelId: string;
  displayName: string;
  role: string;
  state: FighterState;
  phase: string;
  events: BattleStreamItem[];
  artifacts: BattleStreamItem[];
  skillActivity: SkillActivity[];
  previewUrl?: string;
  focused?: boolean;
  onFocus?: () => void;
};

function statusLabel(state: FighterState): string {
  if (state === "running") return "Executing";
  if (state === "complete") return "Complete";
  if (state === "failed") return "Failed";
  if (state === "starting") return "Starting";
  return "Waiting";
}

export default function ExecutionSurface({
  modelId,
  displayName,
  role,
  state,
  phase,
  events,
  artifacts,
  skillActivity,
  previewUrl,
  focused = false,
  onFocus,
}: Props) {
  const [tab, setTab] = useState<Tab>("terminal");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const terminalRef = useRef<HTMLDivElement | null>(null);

  const actions = useMemo(
    () => events.map((item) => ({ item, action: parseAction(item) })).filter((row) => row.action),
    [events],
  );

  const latestArtifact = artifacts[artifacts.length - 1]?.artifact || "";
  const previousArtifact = artifacts[artifacts.length - 2]?.artifact || "";
  const files = useMemo(() => artifactFiles(latestArtifact) || {}, [latestArtifact]);
  const fileNames = useMemo(() => Object.keys(files).sort(), [files]);
  const diffRows = useMemo(() => lineDiff(previousArtifact, latestArtifact), [previousArtifact, latestArtifact]);

  useEffect(() => {
    if (!selectedFile && fileNames.length) setSelectedFile(fileNames[0]);
    if (selectedFile && !files[selectedFile]) setSelectedFile(fileNames[0] || null);
  }, [fileNames, files, selectedFile]);

  useEffect(() => {
    if (tab === "terminal" && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [actions.length, tab]);

  const loadedSkills = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const activity of skillActivity) {
      if (activity.kind !== "skill_load" || !activity.success || !activity.skillId) continue;
      if (seen.has(activity.skillId)) continue;
      seen.add(activity.skillId);
      out.push(activity.skillId);
    }
    return out;
  }, [skillActivity]);

  const availableTabs = useMemo(() => {
    const tabs: { id: Tab; label: string; icon: typeof TerminalSquare }[] = [
      { id: "terminal", label: "Terminal", icon: TerminalSquare },
    ];
    if (fileNames.length) tabs.push({ id: "files", label: `Files ${fileNames.length}`, icon: FileCode2 });
    if (artifacts.length >= 2) tabs.push({ id: "diff", label: "Diff", icon: GitCompare });
    if (previewUrl) tabs.push({ id: "preview", label: "Preview", icon: ExternalLink });
    return tabs;
  }, [artifacts.length, fileNames.length, previewUrl]);

  useEffect(() => {
    if (!availableTabs.some((item) => item.id === tab)) setTab("terminal");
  }, [availableTabs, tab]);

  return (
    <section
      className={cn(
        "arena-surface min-w-0",
        focused && "arena-surface-focused",
      )}
      onMouseDown={onFocus}
      aria-label={`${displayName} execution workspace`}
    >
      <header className="arena-surface-header">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                state === "running" && "bg-fuchsia-400 shadow-[0_0_10px_rgba(232,121,249,.65)]",
                state === "complete" && "bg-emerald-400",
                state === "failed" && "bg-rose-400",
                (state === "waiting" || state === "starting") && "bg-zinc-600",
              )}
            />
            <h2 className="truncate text-[14px] font-semibold tracking-[-0.02em] text-zinc-100">
              {displayName}
            </h2>
            <span className="hidden font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600 sm:inline">
              {role}
            </span>
          </div>
          <div className="mt-1.5 flex min-w-0 items-center gap-2 font-mono text-[9px] text-zinc-600">
            <span className="truncate">{modelId}</span>
            <span>·</span>
            <span className="shrink-0">{phase || "runtime"}</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {loadedSkills.length ? (
            <div className="hidden max-w-[210px] items-center gap-1.5 lg:flex">
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-600">Expertise</span>
              <span className="max-w-[128px] truncate text-[10px] text-zinc-300">
                {humanSkillLabel(loadedSkills[loadedSkills.length - 1])}
              </span>
              {loadedSkills.length > 1 ? (
                <span className="font-mono text-[9px] text-fuchsia-300">+{loadedSkills.length - 1}</span>
              ) : null}
            </div>
          ) : null}
          <span
            className={cn(
              "font-mono text-[9px] font-semibold uppercase tracking-[0.12em]",
              state === "running" && "text-fuchsia-300",
              state === "complete" && "text-emerald-300",
              state === "failed" && "text-rose-300",
              (state === "waiting" || state === "starting") && "text-zinc-500",
            )}
          >
            {statusLabel(state)}
          </span>
        </div>
      </header>

      <nav className="arena-surface-tabs" aria-label={`${displayName} workspace views`}>
        {availableTabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn("arena-tab", tab === id && "arena-tab-active")}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#08090b]">
        {tab === "terminal" ? (
          <div ref={terminalRef} className="arena-terminal">
            {actions.length ? (
              <div className="space-y-0">
                {actions.map(({ item, action }, index) => {
                  if (!action) return null;
                  const failed = action.state === "failed" || action.state === "error";
                  const running = action.state === "running" || action.state === "starting";
                  return (
                    <div key={`${action.tool_call_id || action.event_sequence || item.t}-${index}`} className="arena-command-group">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="w-[58px] shrink-0 pt-[1px] font-mono text-[9px] text-zinc-700">
                          {timeLabel(item.t)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex min-w-0 items-start gap-2 font-mono text-[12px] leading-5">
                            <span className={cn("select-none", failed ? "text-rose-400" : running ? "text-fuchsia-300" : "text-zinc-600")}>
                              {failed ? "×" : running ? "›" : "$"}
                            </span>
                            <span className="break-words text-zinc-200">{action.command}</span>
                          </div>
                          {action.result ? (
                            <pre className={cn("mt-2 whitespace-pre-wrap break-words font-mono text-[11.5px] leading-[1.6]", failed ? "text-rose-300/90" : "text-zinc-500")}>
                              {action.result}
                            </pre>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center px-8 text-center">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
                    {state === "waiting" ? "Waiting for execution" : "No tool activity yet"}
                  </div>
                  <p className="mt-2 max-w-[36ch] text-[12px] leading-5 text-zinc-700">
                    This surface only renders runtime events emitted by the battle.
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {tab === "files" ? (
          <div className="grid h-full min-h-0 grid-cols-[180px_minmax(0,1fr)]">
            <aside className="overflow-y-auto border-r border-white/[0.06] bg-[#0a0b0d] py-2">
              {fileNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setSelectedFile(name)}
                  className={cn(
                    "block w-full truncate px-4 py-2 text-left font-mono text-[10px]",
                    selectedFile === name ? "bg-white/[0.05] text-zinc-100" : "text-zinc-500 hover:bg-white/[0.025] hover:text-zinc-300",
                  )}
                >
                  {name}
                </button>
              ))}
            </aside>
            <pre className="overflow-auto p-5 font-mono text-[11.5px] leading-[1.65] text-zinc-300">
              {selectedFile ? files[selectedFile] : ""}
            </pre>
          </div>
        ) : null}

        {tab === "diff" ? (
          <div className="h-full min-h-0 overflow-auto p-5 font-mono text-[11px] leading-[1.65]">
            {diffRows.map((row, index) => (
              <div
                key={`${index}-${row.text}`}
                className={cn(
                  "grid grid-cols-[24px_minmax(0,1fr)] px-2",
                  row.type === "add" && "bg-emerald-400/[0.07] text-emerald-300",
                  row.type === "remove" && "bg-rose-400/[0.07] text-rose-300",
                  row.type === "same" && "text-zinc-600",
                )}
              >
                <span className="select-none text-zinc-700">{row.type === "add" ? "+" : row.type === "remove" ? "−" : " "}</span>
                <span className="whitespace-pre-wrap break-words">{row.text || " "}</span>
              </div>
            ))}
          </div>
        ) : null}

        {tab === "preview" && previewUrl ? (
          <div className="flex h-full min-h-0 flex-col bg-white">
            <div className="flex h-9 items-center justify-between border-b border-zinc-200 bg-zinc-100 px-3 font-mono text-[9px] text-zinc-500">
              <span className="truncate">{previewUrl}</span>
              <a href={previewUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-zinc-700 hover:text-black">
                Open <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            <iframe title={`${displayName} preview`} src={previewUrl} className="min-h-0 flex-1 bg-white" />
          </div>
        ) : null}
      </div>
    </section>
  );
}
