import type { ProviderOut } from "@/lib/api";
import { useHiddenProviders } from "@/lib/hiddenProviders";

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
            <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>
          ))}
        </optgroup>
      )}
      {visibleYours.length > 0 && (
        <optgroup label="Your keys">
          {visibleYours.map((p) => (
            <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>
          ))}
        </optgroup>
      )}
    </select>
  );
}

