import { Link } from "react-router-dom";

export default function BattleSetupHeader({ step, onStep }: {
  step: 1 | 2 | 3;
  onStep?: (step: 1 | 2 | 3) => void;
}) {
  return <header className="mb-7">
    <div className="mb-6 flex items-baseline justify-between gap-3">
      <h1 className="font-display text-3xl font-semibold tracking-tight text-white">New battle</h1>
      <Link to="/battles" className="text-sm text-slate-400 hover:text-white">Cancel</Link>
    </div>
    <ol aria-label="Battle setup progress" className="flex gap-2 sm:gap-6">
      {(["Challenge", "Models", "Review"] as const).map((label, index) => {
        const value = (index + 1) as 1 | 2 | 3;
        return <li key={label} aria-current={step === value ? "step" : undefined} className="min-w-0 flex-1">
          <button type="button" disabled={!onStep || value >= step} onClick={() => onStep?.(value)}
            className={`flex w-full items-center gap-2 border-b-2 pb-3 text-left text-sm disabled:cursor-default ${step === value ? "border-cyan-300 text-white" : step > value ? "border-cyan-900 text-slate-300" : "border-white/10 text-slate-500"}`}>
            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs ${step === value ? "bg-cyan-300 text-slate-950" : "bg-white/5"}`}>{value}</span>{label}
          </button>
        </li>;
      })}
    </ol>
  </header>;
}
