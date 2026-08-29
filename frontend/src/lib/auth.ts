import { create } from "zustand";
import { createJwt, getSessionUser, login as awLogin, logout as awLogout, signup as awSignup } from "./appwrite";

type User = { $id: string; name?: string; email?: string };

type AuthState = {
  user: User | null;
  jwt: string | null;
  loading: boolean;
  init: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshJwt: () => Promise<string | null>;
};

function safeGet(key: string): string | null {
  // sessionStorage only: the JWT is short-lived and re-fetched on init, so
  // there is no need to persist it across browser sessions. A single storage
  // backing, cleared on tab close, shrinks the XSS exfiltration surface.
  try { return sessionStorage.getItem(key); } catch { return null; }
}
function safeSet(key: string, val: string | null) {
  try {
    if (val) sessionStorage.setItem(key, val);
    else sessionStorage.removeItem(key);
  } catch {}
}

function jwtExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    );
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  jwt: safeGet("arena_jwt"),
  loading: true,
  init: async () => {
    try {
      const u = await getSessionUser();
      if (u) {
        set({ user: u as User });
        const cached = safeGet("arena_jwt");
        if (cached) set({ jwt: cached });
        const token = await get().refreshJwt();
        if (!token && !cached) set({ user: null, jwt: null });
        // refresh every 10min
        setInterval(() => { get().refreshJwt(); }, 10 * 60 * 1000);
      }
    } catch {
      set({ user: null, jwt: null });
      safeSet("arena_jwt", null);
    } finally {
      set({ loading: false });
    }
  },
  refreshJwt: async () => {
    const existing = safeGet("arena_jwt");
    try {
      const token = await createJwt();
      if (token) {
        set({ jwt: token });
        safeSet("arena_jwt", token);
        return token;
      }
    } catch {
      // fall through to the cached-token check below
    }
    // Refresh failed: tolerate the failure only while the cached token is
    // still valid (transient outage). An expired or unparseable token can
    // never recover on its own, so clear it and force a fresh login instead
    // of serving a permanently-401 token for the rest of the tab's life.
    if (existing) {
      const exp = jwtExpiry(existing);
      if (exp === null || exp > Date.now() + 30_000) {
        set({ jwt: existing });
        return existing;
      }
    }
    set({ jwt: null, user: null });
    safeSet("arena_jwt", null);
    return null;
  },
  login: async (email, password) => {
    const u = await awLogin(email, password);
    set({ user: u as User });
    await get().refreshJwt();
  },
  signup: async (email, password, name) => {
    const u = await awSignup(email, password, name);
    set({ user: u as User });
    await get().refreshJwt();
  },
  logout: async () => {
    await awLogout();
    set({ user: null, jwt: null });
    safeSet("arena_jwt", null);
  },
}));

if (typeof window !== "undefined") {
  (window as any).useAuth = useAuth;
}

