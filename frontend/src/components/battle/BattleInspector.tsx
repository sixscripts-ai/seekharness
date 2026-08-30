import { useMemo } from "react";
import { Activity, BrainCircuit, FileText, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BattleOut } from "@/lib/api";
import type { TargetResultView } from "@/lib/targetResult";
import type { BattleStreamItem, SkillActivity } from "./types";
import { humanSkillLabel, parseAction, timeLabel, titleCase } from "./utils";

type InspectorTab = "activity" | "expertise" | "evidence" | "result";

type Props = {
  tab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  battle: BattleOut;
  status: string;
  modelIds: string[];
  modelName: (id: string) => string;
  events: BattleStreamItem[];
  skillActivity: SkillActivity[];
  selectedModelId: string;
  resultView: TargetResultView;
};

function activityLabel(skill: SkillActivity): { verb: string; value: string } {
  if (skill.kind === "skill_search") return { verb: "searched expertise", value: skill.query || "Skill Graph" };
  if (skill.kind === "skill_index_browse") return { verb: "browsed expertise", value: skill.index || "Skill Graph" };
  if (skill.kind === "skill_card_view") return { verb: "inspected expertise", value: skill.skillId ? humanSkillLabel(skill.skillId) : "Skill card" };
  return { verb: skill.success ? "loaded expertise" : "expertise load failed", value: skill.skillId ? humanSkillLabel(skill.skillId) : "Skill" };
}

export default function BattleInspector({
  tab,
  onTabChange,
  battle,
  status,
  modelIds,
  modelName,
  events,
  skillActivity,
  selectedModelId,
  resultView,
}: Props) {
  const selectedSkills = useMemo(
    () => skillActivity.filter((item) => item.modelId === selectedModelId),
    [skillActivity, selectedModelId],
  );

  const activityRows = useMemo(() => {
    const rows: Array<{
      key: string;
      t: number;
      modelId: string;
      type: "tool" | "skill" | "phase";
      title: string;
      detail: string;
      failed?: boolean;
    }> = [];

    for (const item of events) {
      if (item.kind === "action_log") {
        const action = parseAction(item);
        if (!action) continue;
        rows.push({
          key: `tool:${item.model_id}:${action.tool_call_id || action.event_sequence || item.t}`,
          t: item.t,
          modelId: item.model_id,
          type: "tool",
          title: action.action || "tool",
          detail: action.command,
          failed: action.state === "failed" || action.state === "error",
        });
      } else if (item.kind === "phase_start") {
        rows.push({
          key: `phase:${item.phase}:${item.t}`,
          t: item.t,
          modelId: item.model_id,
          type: "phase",
          title: "phase",
          detail: titleCase(item.phase),
        });
      }
    }

    for (const skill of skillActivity) {
      const label = activityLabel(skill);
      rows.push({
        key: `skill:${skill.modelId}:${skill.eventSequence || skill.t}:${skill.kind}`,
        t: skill.t,
        modelId: skill.modelId,
        type: "skill",
        title: label.verb,
        detail: label.value,
        failed: !skill.success,
      });
    }

    return rows.sort((a, b) => a.t - b.t).slice(-160).reverse();
  }, [events, skillActivity]);

  const loaded = useMemo(() => {
    const seen = new Set<string>();
    return selectedSkills.filter((item) => {
      if (item.kind !== "skill_load" || !item.success || !item.skillId || seen.has(item.skillId)) return false;
      seen.add(item.skillId);
      return true;
    });
  }, [selectedSkills]);

  const inspected = useMemo(() => {
    const seen = new Set<string>();
    return selectedSkills.filter((item) => {
      if (item.kind !== "skill_card_view" || !item.skillId || seen.has(item.skillId)) return false;
      seen.add(item.skillId);
      return true;
    });
  }, [selectedSkills]);

  const searches = selectedSkills.filter((item) => item.kind === "skill_search" || item.kind === "skill_index_browse");
  const actionCount = events.filter((item) => item.kind === "action_log").length;
  const artifactCount = events.filter((item) => item.kind === "artifact").length;
  const failedActionCount = events.filter((item) => {
    const action = parseAction(item);
    return action?.state === "failed" || action?.state === "error";
  }).length;

  const tabs: Array<{ id: InspectorTab; label: string; icon: typeof Activity }> = [
    { id: "activity", label: "Activity", icon: Activity },
    { id: "expertise", label: "Expertise", icon: BrainCircuit },
    { id: "evidence", label: "Evidence", icon: FileText },
    { id: "result", label: "Result", icon: ShieldCheck },
  ];

  return (
    <aside className="battle-inspector">
      <div className="battle-inspector-tabs" role="tablist" aria-label="Battle inspector">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => onTabChange(id)}
            className={cn("battle-inspector-tab", tab === id && "battle-inspector-tab-active")}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{label}</span>
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "activity" ? (
          <div className="py-2">
            {activityRows.length ? activityRows.map((row) => (
              <div key={row.key} className="border-b border-white/[0.045] px-4 py-3 last:border-b-0">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-[10px] font-medium text-zinc-400">{modelName(row.modelId)}</span>
                  <span className="shrink-0 font-mono text-[8px] text-zinc-700">{timeLabel(row.t)}</span>
                </div>
                <div className="mt-1.5 flex items-start gap-2">
                  <span
                    className={cn(
                      "mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full",
                      row.failed ? "bg-rose-400" : row.type === "skill" ? "bg-fuchsia-400" : row.type === "phase" ? "bg-amber-300" : "bg-zinc-600",
                    )}
                  />
                  <div className="min-w-0">
                    <div className={cn("font-mono text-[9px] uppercase tracking-[0.09em]", row.failed ? "text-rose-300" : row.type === "skill" ? "text-fuchsia-300" : "text-zinc-600")}>
                      {row.title}
                    </div>
                    <div className="mt-1 break-words font-mono text-[10px] leading-4 text-zinc-300">{row.detail}</div>
                  </div>
                </div>
              </div>
            )) : (
              <InspectorEmpty title="No recorded activity" detail="Runtime and expertise events will appear here when the battle emits them." />
            )}
          </div>
        ) : null}

        {tab === "expertise" ? (
          <div className="p-4">
            <div className="mb-4">
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-600">Selected fighter</div>
              <div className="mt-1 text-[13px] font-semibold text-zinc-100">{modelName(selectedModelId)}</div>
            </div>

            {!selectedSkills.length ? (
              <InspectorEmpty title="No expertise activity recorded" detail="Using zero skills is valid. This panel never infers expertise from terminal text." />
            ) : (
              <div className="space-y-5">
                <Metric label="Exploration" value={`${searches.length} ${searches.length === 1 ? "interaction" : "interactions"}`} />
                <div>
                  <SectionLabel>Inspected</SectionLabel>
                  {inspected.length ? (
                    <div className="mt-2 space-y-1.5">
                      {inspected.map((item) => <ExpertiseRow key={`${item.skillId}-${item.t}`} label={humanSkillLabel(item.skillId || "")} />)}
                    </div>
                  ) : <MutedNone />}
                </div>
                <div>
                  <SectionLabel>Loaded</SectionLabel>
                  {loaded.length ? (
                    <div className="mt-2 space-y-1.5">
                      {loaded.map((item) => <ExpertiseRow key={`${item.skillId}-${item.t}`} label={humanSkillLabel(item.skillId || "")} active />)}
                    </div>
                  ) : <MutedNone />}
                </div>
                <div>
                  <SectionLabel>Observed path</SectionLabel>
                  <div className="mt-2 space-y-0">
                    {selectedSkills.slice(-12).map((item, index) => {
                      const label = activityLabel(item);
                      return (
                        <div key={`${item.kind}-${item.t}-${index}`} className="grid grid-cols-[14px_minmax(0,1fr)] gap-2 pb-3 last:pb-0">
                          <div className="relative flex justify-center">
                            <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-fuchsia-400" />
                            {index < Math.min(11, selectedSkills.length - 1) ? <span className="absolute top-3 h-[calc(100%-6px)] w-px bg-white/[0.08]" /> : null}
                          </div>
                          <div>
                            <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-zinc-600">{label.verb}</div>
                            <div className="mt-0.5 text-[10px] leading-4 text-zinc-300">{label.value}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {tab === "evidence" ? (
          <div className="p-4">
            <div className="grid grid-cols-3 border-y border-white/[0.06]">
              <EvidenceMetric label="Tool events" value={String(actionCount)} />
              <EvidenceMetric label="Artifacts" value={String(artifactCount)} />
              <EvidenceMetric label="Failures" value={String(failedActionCount)} />
            </div>
            <div className="mt-5 space-y-4">
              <EvidenceLine label="Battle" value={battle.id} mono />
              <EvidenceLine label="Visibility" value={battle.round_visibility || "isolated"} />
              {battle.target_id ? <EvidenceLine label="Target" value={battle.target_id} /> : null}
              {battle.target_version ? <EvidenceLine label="Version" value={battle.target_version} /> : null}
              {battle.spec_hash ? <EvidenceLine label="Spec hash" value={battle.spec_hash} mono /> : null}
              <EvidenceLine label="Recorded fighters" value={String(modelIds.length)} />
            </div>
          </div>
        ) : null}

        {tab === "result" ? (
          <div className="p-4">
            <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-zinc-600">Authoritative result</div>
            <div className="mt-2 text-[18px] font-semibold tracking-[-0.02em] text-zinc-100">{resultView.statusLabel}</div>
            <div className="mt-5 space-y-4">
              <EvidenceLine label="Battle state" value={titleCase(status)} />
              {resultView.verificationLabel ? <EvidenceLine label="Verification" value={resultView.verificationLabel} /> : null}
              {resultView.terminalOutcome ? <EvidenceLine label="Termination" value={titleCase(resultView.terminalOutcome)} /> : null}
              {resultView.showCompetitiveWinner && resultView.winnerId ? <EvidenceLine label="Winner" value={modelName(resultView.winnerId)} /> : null}
            </div>

            {resultView.scores ? (
              <div className="mt-6">
                <SectionLabel>Scores</SectionLabel>
                <div className="mt-2 divide-y divide-white/[0.05] border-y border-white/[0.06]">
                  {Object.entries(resultView.scores).map(([modelId, score]) => (
                    <div key={modelId} className="flex items-center justify-between gap-3 py-2.5 text-[10px]">
                      <span className="truncate text-zinc-400">{modelName(modelId)}</span>
                      <span className="font-mono font-semibold text-zinc-100">{score}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function InspectorEmpty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="px-4 py-12 text-center">
      <div className="text-[11px] font-medium text-zinc-400">{title}</div>
      <p className="mx-auto mt-2 max-w-[30ch] text-[10px] leading-4 text-zinc-700">{detail}</p>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.13em] text-zinc-600">{children}</div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
      <span className="text-[10px] text-zinc-500">{label}</span>
      <span className="font-mono text-[10px] text-zinc-200">{value}</span>
    </div>
  );
}

function ExpertiseRow({ label, active = false }: { label: string; active?: boolean }) {
  return (
    <div className="flex items-center gap-2 text-[10px] text-zinc-300">
      <span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-fuchsia-400" : "bg-zinc-600")} />
      <span>{label}</span>
    </div>
  );
}

function MutedNone() {
  return <div className="mt-2 text-[10px] text-zinc-700">None recorded</div>;
}

function EvidenceMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-3 text-center first:text-left last:text-right">
      <div className="font-mono text-[14px] font-semibold text-zinc-200">{value}</div>
      <div className="mt-1 text-[8px] uppercase tracking-[0.1em] text-zinc-700">{label}</div>
    </div>
  );
}

function EvidenceLine({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[9px] text-zinc-600">{label}</div>
      <div className={cn("mt-1 break-all text-[10px] leading-4 text-zinc-300", mono && "font-mono")}>{value}</div>
    </div>
  );
}
