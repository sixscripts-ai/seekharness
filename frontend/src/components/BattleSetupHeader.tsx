import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

export default function BattleSetupHeader({ step, onStep }: {
  step: 1 | 2 | 3;
  onStep?: (step: 1 | 2 | 3) => void;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const label = ["Challenge", "Models", "Review"][step - 1];
    const originalTitle = document.title;
    document.title = `${label} · New battle · SeekHarness`;
    titleRef.current?.focus();
    return () => { document.title = originalTitle; };
  }, [step]);
  return <header className="mb-7">
    <div className="mb-6 flex items-baseline justify-between gap-3">
      <h1 ref={titleRef} tabIndex={-1} className="font-display text-3xl font-semibold tracking-tight text-white focus:outline-none">New battle <span className="sr-only">Step {step} of 3: {(["Challenge", "Models", "Review"] as const)[step - 1]}</span></h1>
      <Link to="/battles" className="text-sm text-slate-400 hover:text-white">Cancel</Link>
    </div>
    <ol aria-label="Battle setup progress" className="flex gap-2 sm:gap-6">
      {(["Challenge", "Models", "Review"] as const).map((label, index) => {
        const value = (index + 1) as 1 | 2 | 3;
        return <li key={label} aria-current={step === value ? "step" : undefined} className="min-w-0 flex-1">
          <button type="button" disabled={!onStep || value >= step} onClick={() => onStep?.(value)}
            aria-label={`${label}, step ${value} of 3${step === value ? ", current" : step > value ? ", completed; go back" : ", upcoming"}`}
            className={`flex w-full min-h-11 items-center gap-2 border-b-2 pb-3 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-300 disabled:cursor-default ${step === value ? "border-cyan-300 text-white" : step > value ? "border-cyan-900 text-slate-300" : "border-white/10 text-slate-500"}`}>
            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs ${step === value ? "bg-cyan-300 text-slate-950" : "bg-white/5"}`}>{value}</span>{label}
          </button>
        </li>;
      })}
    </ol>
  </header>;
}
