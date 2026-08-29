import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rawNext = params.get("next") || "/";
  // Only allow app-internal paths; reject absolute/protocol-relative URLs.
  const next = rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await login(email, password); nav(next); } catch (e) { setErr(e instanceof Error ? e.message : "Login failed"); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-[400px]">
      <div className="card p-8">
        <div className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-[-0.01em]">Log in</h1>
          <p className="mt-1 text-[13px] text-muted">Sign in to queue battles and track Elo.</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-[12px] font-medium">Email</label>
            <input className="input" type="email" value={email} onChange={e=>setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-[12px] font-medium">Password</label>
            <input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)} required />
          </div>
          {err && <div className="rounded-md border border-danger bg-danger/10 px-3 py-2 text-[12px] text-danger break-all">{err}</div>}
          <button disabled={busy} className="btn btn-primary h-11 w-full text-[13px]">{busy ? "Signing in…" : "Log in →"}</button>
        </form>
        <p className="mt-6 text-center text-[13px] text-muted">
          No account? <Link to="/signup" className="link">Sign up</Link>
        </p>
      </div>
    </div>
  );
}
