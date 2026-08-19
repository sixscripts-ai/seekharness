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
    try {
      const token = await createJwt();
      if (token) {
        set({ jwt: token });
        safeSet("arena_jwt", token);
        return token;
      }
      const existing = safeGet("arena_jwt");
      if (existing) { set({ jwt: existing }); return existing; }
      return null;
    } catch {
      const existing = safeGet("arena_jwt");
      if (existing) return existing;
      return null;
    }
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
