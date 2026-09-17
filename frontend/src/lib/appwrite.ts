declare const __DEFAULT_MODAL_URL__: string;

const BASE = (
  import.meta.env.VITE_MODAL_URL ||
  (typeof __DEFAULT_MODAL_URL__ !== "undefined" ? __DEFAULT_MODAL_URL__ : "")
).replace(/\/$/, "");

export interface AuthUser {
  id: string;
  $id: string;
  email: string;
  name: string;
}

interface AuthResponse {
  user: AuthUser;
  token: string;
}

function getStoredToken(): string | null {
  try {
    return localStorage.getItem("arena_jwt") || sessionStorage.getItem("arena_jwt");
  } catch {
    return null;
  }
}

function setStoredToken(token: string | null) {
  try {
    if (token) {
      localStorage.setItem("arena_jwt", token);
      sessionStorage.setItem("arena_jwt", token);
    } else {
      localStorage.removeItem("arena_jwt");
      sessionStorage.removeItem("arena_jwt");
    }
  } catch {}
}

export async function signup(email: string, password: string, name: string): Promise<AuthUser> {
  const res = await fetch(`${BASE}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Signup failed" }));
    throw new Error(err.detail || `Signup failed (${res.status})`);
  }
  const data: AuthResponse = await res.json();
  setStoredToken(data.token);
  return data.user;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Invalid email or password" }));
    throw new Error(err.detail || `Login failed (${res.status})`);
  }
  const data: AuthResponse = await res.json();
  setStoredToken(data.token);
  return data.user;
}

export async function logout(): Promise<void> {
  const token = getStoredToken();
  setStoredToken(null);
  if (token) {
    try {
      await fetch(`${BASE}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {}
  }
}

export async function getSessionUser(): Promise<AuthUser | null> {
  const token = getStoredToken();
  if (!token) return null;
  try {
    const res = await fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setStoredToken(null);
      return null;
    }
    return await res.json();
  } catch {
    return null;
  }
}

export async function createJwt(): Promise<string | null> {
  return getStoredToken();
}

