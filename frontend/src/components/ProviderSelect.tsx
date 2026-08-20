import type { ProviderOut } from "@/lib/api";

export default function ProviderSelect({
  value,
  onChange,
  host,
  yours,
}: {
  value: string;
  onChange: (id: string) => void;
  host: ProviderOut[];
  yours: ProviderOut[];
}) {
  return (
    <select className="select h-11 font-mono text-[12px]" value={value} onChange={(e) => onChange(e.target.value)}>
      <optgroup label="Host — always available">
        {host.map((p) => (
          <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>
        ))}
      </optgroup>
      <optgroup label="Your keys">
        {yours.map((p) => (
          <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>
        ))}
      </optgroup>
    </select>
  );
}

