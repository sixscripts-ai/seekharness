import { playableRoleCount, type FormatOut } from "@/lib/api";
import { SectionHeader } from "./BattleModeSelector";

function formatDescription(format: FormatOut) {
  if (format.description) return format.description;
  if (format.engine === "agent_tool_race") {
    return "Agents execute with the full arena toolbelt.";
  }
  return "Run this arena format with predefined roles and execution rules.";
}

export default function FormatSelector({
  formats,
  formatId,
  onSelectFormat,
  selectedFormat,
  need,
}: {
  formats: FormatOut[];
  formatId: string;
  onSelectFormat: (id: string) => void;
  selectedFormat?: FormatOut;
  need: number;
}) {
  return (
    <div className="space-y-4">
      <SectionHeader
        index="2"
        title="Execution format"
        description="Select the arena format and role sequence."
        trailing={
          selectedFormat
            ? `${need} fighter${need === 1 ? "" : "s"}`
            : undefined
        }
      />

      <div className="flex gap-4 overflow-x-auto pb-2">
        {formats.map((item) => {
          const active = item.id === formatId;
          const count = playableRoleCount(item);
          const itemRoles =
            item.roles?.filter((role) => role !== "judge") || [];

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectFormat(item.id)}
              className={`relative min-h-[150px] min-w-[260px] flex-1 rounded-xl p-4 text-left transition-all border ${
                active
                  ? "border-accent bg-accent/10 shadow-[0_0_15px_rgba(255,0,160,0.2)]"
                  : "border-[#1F1F22] bg-[#050508] hover:border-zinc-700 hover:bg-[#0D0D0F]"
              }`}
            >
              {active && (
                <span className="absolute inset-x-0 top-0 h-0.5 rounded-t-xl bg-accent" />
              )}

              <div className="flex items-start justify-between gap-3">
                <span
                  className={`mono text-[9px] font-bold uppercase tracking-[0.14em] ${
                    active ? "text-accent" : "text-zinc-500"
                  }`}
                >
                  {item.engine}
                </span>

                <span className="mono text-[9px] uppercase tracking-[0.12em] text-zinc-500">
                  {count} slots
                </span>
              </div>

              <div className="mt-4 text-[14px] font-bold text-white tracking-[-0.02em]">
                {item.name}
              </div>

              <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-zinc-400">
                {formatDescription(item)}
              </p>

              <div className="mt-4 mono text-[9px] font-bold uppercase tracking-[0.1em] text-zinc-500">
                {itemRoles.length ? itemRoles.join(" → ") : "arena format"}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
