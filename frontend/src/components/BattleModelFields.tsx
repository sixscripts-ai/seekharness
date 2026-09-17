import { Link } from "react-router-dom";
import { splitProviders, type ProviderOut } from "@/lib/api";
import ProviderSelect from "./ProviderSelect";

export default function BattleModelFields({ roles, selected, onChange, providers }: {
  roles: string[]; selected: string[]; onChange: (ids: string[]) => void; providers: ProviderOut[];
}) {
  const { host, yours } = splitProviders(providers);
  return <section>
    <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-xl font-medium text-white">Choose models</h2><Link to="/settings/models" className="text-sm text-slate-400 hover:text-cyan-300">Manage models in Settings</Link></div>
    <div className="grid gap-4 md:grid-cols-2">{roles.map((role, index) => <label key={index} className="block min-w-0 rounded-xl border border-white/10 bg-[#11141E] p-5">
      <span className="mb-1 block font-medium capitalize text-white">{role === "Builder" || role === "Breaker" ? role + " Slot" : role}</span>
      <span className="mb-4 block text-xs leading-5 text-slate-400">{role === "Builder" ? "Defensive coding: build and harden the solution." : role === "Breaker" ? "Adversarial testing: find an exploit in the builder’s output." : "Runs this challenge in an isolated workspace."}</span>
      <ProviderSelect value={selected[index] || ""} onChange={id => onChange(roles.map((_, position) => position === index ? id : selected[position] || ""))} host={host} yours={yours} />
    </label>)}</div>
    {!providers.length && <p className="mt-4 text-sm text-amber-200">No models are available. Check Settings or try loading this page again.</p>}
    {selected.filter(Boolean).length !== new Set(selected.filter(Boolean)).size && <p role="alert" className="mt-4 text-sm text-amber-200">Choose a different model for each slot.</p>}
  </section>;
}
