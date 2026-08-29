import { useNavigate } from "react-router-dom";

export function SectionHeader({
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
    <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-accent">
          <span>{index}</span>
          <span>/</span>
          <span>{title}</span>
        </div>
        <div className="mt-1 text-[13px] text-zinc-400">{description}</div>
      </div>
      {trailing && (
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-zinc-400">
          {trailing}
        </span>
      )}
    </div>
  );
}

export function ModeCard({
  eyebrow,
  title,
  description,
  footer,
  active,
  onClick,
}: {
  eyebrow: string;
  title: string;
  description: string;
  footer: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative min-h-[160px] p-5 text-left transition-all ${
        active
          ? "bg-accent/10 border border-accent/40 shadow-[0_0_15px_rgba(255,0,160,0.15)]"
          : "bg-[#050508] border border-[#1F1F22] hover:border-zinc-700 hover:bg-[#0D0D0F]"
      }`}
    >
      {active && <span className="absolute inset-x-0 top-0 h-0.5 bg-accent" />}
      <div className="flex items-start justify-between gap-3">
        <span
          className={`mono text-[9.5px] font-bold uppercase tracking-[0.14em] ${
            active ? "text-accent" : "text-zinc-500"
          }`}
        >
          {eyebrow}
        </span>
        <span className="mono text-[9px] uppercase tracking-[0.12em] text-zinc-500">
          {footer}
        </span>
      </div>

      <div className="mt-4 text-[15px] font-bold text-white tracking-[-0.02em]">
        {title}
      </div>

      <p className="mt-2 text-[11.5px] leading-relaxed text-zinc-400">
        {description}
      </p>
    </button>
  );
}

export default function BattleModeSelector() {
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      <SectionHeader
        index="1"
        title="Battle mode"
        description="Choose how you want to define this battle."
      />

      <div className="grid gap-4 md:grid-cols-3">
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
          onClick={() => navigate("/battles/custom?mode=quick")}
        />

        <ModeCard
          eyebrow="Verified custom"
          title="Executable challenge"
          description="Create a custom challenge with a frozen specification and executable acceptance tests."
          footer="Tests + judge"
          onClick={() => navigate("/battles/custom?mode=verified")}
        />
      </div>
    </div>
  );
}
