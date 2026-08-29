import { useEffect, useState } from "react";

const STORAGE_KEY = "seekharness_hidden_providers";
const CHANGE_EVENT = "seekharness_hidden_providers_change";

export function getHiddenProviderIds(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

export function setHiddenProviderIds(ids: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
    window.dispatchEvent(new Event(CHANGE_EVENT));
  } catch {}
}

export function hideProviderId(id: string): void {
  const current = getHiddenProviderIds();
  current.add(id);
  setHiddenProviderIds(current);
}

export function unhideProviderId(id: string): void {
  const current = getHiddenProviderIds();
  current.delete(id);
  setHiddenProviderIds(current);
}

export function toggleProviderIdHidden(id: string): boolean {
  const current = getHiddenProviderIds();
  const isHidden = current.has(id);
  if (isHidden) {
    current.delete(id);
  } else {
    current.add(id);
  }
  setHiddenProviderIds(current);
  return !isHidden;
}

export function clearHiddenProviderIds(): void {
  setHiddenProviderIds(new Set());
}

export function useHiddenProviders(): {
  hiddenIds: Set<string>;
  hide: (id: string) => void;
  unhide: (id: string) => void;
  toggle: (id: string) => boolean;
  clearAll: () => void;
  isHidden: (id: string) => boolean;
} {
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(getHiddenProviderIds);

  useEffect(() => {
    function handleChange() {
      setHiddenIds(getHiddenProviderIds());
    }
    window.addEventListener(CHANGE_EVENT, handleChange);
    window.addEventListener("storage", handleChange);
    return () => {
      window.removeEventListener(CHANGE_EVENT, handleChange);
      window.removeEventListener("storage", handleChange);
    };
  }, []);

  return {
    hiddenIds,
    hide: hideProviderId,
    unhide: unhideProviderId,
    toggle: toggleProviderIdHidden,
    clearAll: clearHiddenProviderIds,
    isHidden: (id: string) => hiddenIds.has(id),
  };
}
