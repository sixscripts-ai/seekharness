import type { ProviderOut } from "@/lib/api";
import { useHiddenProviders } from "@/lib/hiddenProviders";

function formatOptionLabel(p: ProviderOut): string {
  if (!p.model_name) return p.name;
  if (!p.name) return p.model_name;
  if (p.name.toLowerCase().includes(p.model_name.toLowerCase())) return p.name;
  return `${p.name} · ${p.model_name}`;
}

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
  const { isHidden } = useHiddenProviders();

  const visibleHost = host.filter((p) => !isHidden(p.id) || p.id === value);
  const visibleYours = yours.filter((p) => !isHidden(p.id) || p.id === value);

  return (
    <select className="select h-11 font-mono text-[12px]" value={value} onChange={(e) => onChange(e.target.value)}>
      {visibleHost.length > 0 && (
        <optgroup label="Host — always available">
          {visibleHost.map((p) => (
            <option key={p.id} value={p.id}>{formatOptionLabel(p)}</option>
          ))}
        </optgroup>
      )}
      {visibleYours.length > 0 && (
        <optgroup label="Your keys">
          {visibleYours.map((p) => (
            <option key={p.id} value={p.id}>{formatOptionLabel(p)}</option>
          ))}
        </optgroup>
      )}
    </select>
  );
}

