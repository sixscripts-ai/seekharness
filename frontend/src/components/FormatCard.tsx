import { Link } from "react-router-dom";
import { Wrench } from "lucide-react";
import { isToolUsingFormat, type FormatOut } from "@/lib/api";

const ENGINE_COLORS: Record<string, string> = {
  build_and_break: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  script_vs_defense: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  same_target_race: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  direct_duel: "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300",
  high_complexity: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  agent_vs_agent: "bg-cyan-100 text-cyan-800 dark:bg-cyan-500/15 dark:text-cyan-300",
  agent_tool_race: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
};

export default function FormatCard({ format, user, large }: { format: FormatOut; user: any; large?: boolean }) {
  const color = ENGINE_COLORS[format.engine] || "bg-surface2 text-foreground";
  const roles = Array.isArray(format.roles) ? format.roles.filter(r => r !== "judge") : [];
  const toolUsing = isToolUsingFormat(format);
  return (
    <div className={`${large ? "col-span-12 md:col-span-7" : "col-span-12 sm:col-span-6 lg:col-span-4"} card flex flex-col justify-between p-5 transition-colors hover:border-borderStrong`}>
      <div className="flex items-start justify-between">
        <div className={`grid h-8 w-8 place-items-center rounded-lg border border-borderStrong text-[12px] font-bold ${color}`}>
          {format.engine?.[0]?.toUpperCase() || "A"}
        </div>
        <div className="flex items-center gap-1.5">
          {toolUsing && (
            <span
              className="tag inline-flex items-center gap-1 border-accent text-accent"
              title="Runs the in-sandbox toolbelt: agents read files, run tests, and use skills. Streams live tool activity."
            >
              <Wrench className="h-3 w-3" />
              Tools
            </span>
          )}
          <span className="tag">{format.engine}</span>
        </div>
      </div>
      <div className="mt-4">
        <h3 className="text-[15px] font-semibold leading-tight tracking-[-0.01em]">{format.name}</h3>
        <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-muted">
          {format.description || "Arena format — builder vs breaker, real code execution"}
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {roles.slice(0, 3).map(r => <span key={r} className="tag">{r}</span>)}
        </div>
      </div>
      <Link
        to={user ? `/battles/new?format=${format.id}` : "/login"}
        className="btn btn-ghost mt-4 w-full hover:border-accent hover:text-accent"
      >
        {user ? "Fight →" : "Log in to fight →"}
      </Link>
    </div>
  );
}
