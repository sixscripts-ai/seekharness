import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, isCustomFormat, isHostProviderId, playableRoleCount, splitProviders, type FormatOut, type ProviderOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ProviderSelect from "@/components/ProviderSelect";

export default function NewBattle() {
  const { user, jwt, refreshJwt } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [formatId, setFormatId] = useState(params.get("format") || "");
  const [selected, setSelected] = useState<string[]>([]);
  const [judgeId, setJudgeId] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [visibility, setVisibility] = useState<"isolated" | "open">("isolated");
  const [difficulty, setDifficulty] = useState<"novice" | "general" | "advanced" | "expert">("general");
  const [save, setSave] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const host = useMemo(() => splitProviders(providers).host, [providers]);
  const yours = useMemo(() => splitProviders(providers).yours, [providers]);

  useEffect(() => {
    if (!jwt) return;
    (async () => {
      const token = (await refreshJwt()) || jwt;
      const [f, p] = await Promise.all([api.formats(token), api.providers(token)]);
      const launchable = f.filter((fmt) => !isCustomFormat(fmt));
      setFormats(launchable);
      setProviders(p);
      if (!formatId && launchable[0]) setFormatId(launchable[0].id);
      const hostIds = p.filter((x) => isHostProviderId(x.id)).map((x) => x.id);
      const fb = hostIds[0] || p[0]?.id || "host:openrouter-free";
      const alt = hostIds[1] || hostIds[0] || fb;
      if (selected.length === 0) setSelected([fb, alt]);
    })();
  }, [jwt]);

  const format = formats.find((f) => f.id === formatId);
  const need = format ? playableRoleCount(format) : 2;
  const roles = useMemo(() => {
    if (!format) return ["builder", "breaker"];
    const r = (format as { roles?: string[] }).roles;
    if (Array.isArray(r)) return r.filter((x) => x !== "judge");
    return ["a", "b"];
  }, [format]);

  useEffect(() => {
    setSelected((prev) => {
      const next = prev.slice(0, need);
      const fb = host[0]?.id || providers[0]?.id || "host:openrouter-free";
      const alt = host[1]?.id || host[0]?.id || fb;
      while (next.length < need) next.push(next.length === 1 ? alt : fb);
      const allowed = new Set(providers.map((p) => p.id));
      return next.map((id) => (allowed.has(id) || isHostProviderId(id) ? id : fb));
    });
  }, [need, providers, host]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const token = (await refreshJwt()) || jwt;
    if (!token) return;
    const allowed = new Set(providers.map((p) => p.id));
    const invalid = selected.some((id) => !allowed.has(id) && !isHostProviderId(id));
    if (invalid) { setErr("Invalid provider — choose any host: or your own"); return; }
    setBusy(true); setErr(null);
    try {
      const battle = await api.createBattle(token, {
        format_id: formatId,
        model_ids: selected,
        arena_size: selected.length,
        timeout_seconds: timeoutSec,
        round_visibility: visibility,
        difficulty,
        save,
        judge_provider_id: judgeId || null,
      });
      try {
        const key = "arena_battle_ids";
        const prev = JSON.parse(localStorage.getItem(key) || "[]") as string[];
        localStorage.setItem(key, JSON.stringify([battle.id, ...prev].slice(0, 50)));
      } catch {}
      nav(`/battles/${battle.id}`);
    } catch (er) {
      setErr(er instanceof Error ? er.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[36ch] space-y-3 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Match locked</div>
          <p className="text-[14px] text-muted">Log in to set fighters and start a bout.</p>
          <Link to="/login" className="btn btn-primary mx-auto h-10 px-6">Log in</Link>
        </div>
      </div>
    );
  }

  const dual = need === 2;

  return (
    <form onSubmit={onSubmit} className="min-h-[calc(100vh-56px)] bg-background text-foreground">
      <div className="border-b border-border px-6 py-5">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">New match</div>
            <h1 className="mt-1 font-display text-[40px] leading-none tracking-[-0.04em] md:text-[56px]">
              {format?.name || "Select format"}
            </h1>
          </div>
          <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            {need} fighters · {visibility} · {difficulty} · {timeoutSec}s
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12 gap-0">
        <section className="col-span-12 border-b border-border px-6 py-5 lg:col-span-8 lg:border-r lg:border-b-0">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Format</label>
          <select className="select mt-2 h-12 font-mono text-[13px]" value={formatId} onChange={(e) => setFormatId(e.target.value)}>
            {formats.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} · {f.engine} · {(f.roles?.filter((r: string) => r !== "judge").length || 2)} slots
              </option>
            ))}
          </select>
          <p className="mt-2 font-mono text-[11px] text-muted">
            roles {roles.join(" / ")} · order maps to slot
          </p>
        </section>
        <aside className="col-span-12 px-6 py-5 lg:col-span-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Bout card</div>
          <div className="mt-3 space-y-1 font-mono text-[11px] leading-5 text-muted">
            {roles.map((r, i) => (
              <div key={r} className="flex justify-between gap-3 border-b border-border py-1.5">
                <span className="text-accent">{r}</span>
                <span className="truncate text-foreground">{selected[i] || "—"}</span>
              </div>
            ))}
            <div className="flex justify-between gap-3 py-1.5">
              <span>judge</span>
              <span className="truncate text-foreground">{judgeId || "host default"}</span>
            </div>
          </div>
        </aside>
      </div>

      <div className={`mx-auto grid max-w-[1360px] border-y border-border ${dual ? "grid-cols-1 md:grid-cols-[1fr_88px_1fr]" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"}`}>
        {selected.map((mid, i) => (
          <div
            key={i}
            className={`relative border-b border-border px-6 py-8 last:border-b-0 md:border-b-0 ${dual ? "" : "md:border-r md:last:border-r-0"} ${dual && i === 0 ? "md:order-1" : dual && i === 1 ? "md:order-3" : ""}`}
          >
            <div className="flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
                Slot {i + 1}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{roles[i] || `model ${i + 1}`}</div>
            </div>
            <div className="mt-3 font-display text-[28px] leading-none tracking-[-0.03em]">
              {roles[i] || `Fighter ${i + 1}`}
            </div>
            <div className="mt-6">
              <ProviderSelect
                value={mid}
                host={host}
                yours={yours}
                onChange={(id) => {
                  const next = [...selected];
                  next[i] = id;
                  setSelected(next);
                }}
              />
            </div>
          </div>
        ))}
        {dual && (
          <div className="hidden items-center justify-center border-x border-border md:order-2 md:flex">
            <div className="font-display text-[28px] tracking-[-0.04em] text-accent">VS</div>
          </div>
        )}
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12 gap-0 border-b border-border">
        <div className="col-span-12 space-y-2 border-b border-border px-6 py-5 md:col-span-3 md:border-b-0 md:border-r">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Judge</label>
          <select className="select font-mono text-[12px]" value={judgeId} onChange={(e) => setJudgeId(e.target.value)}>
            <option value="">Default host judge (Kimi-K3)</option>
            {host.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>)}
            {yours.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>)}
          </select>
        </div>
        <div className="col-span-6 space-y-2 border-r border-border px-6 py-5 md:col-span-2">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Timeout</label>
          <input type="number" min={30} max={3600} value={timeoutSec} onChange={(e) => setTimeoutSec(Number(e.target.value))} className="input font-mono" />
        </div>
        <div className="col-span-6 space-y-2 border-r border-border px-6 py-5 md:col-span-2">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Difficulty</label>
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as typeof difficulty)} className="select font-mono text-[12px]">
            <option value="novice">novice</option>
            <option value="general">general</option>
            <option value="advanced">advanced</option>
            <option value="expert">expert</option>
          </select>
        </div>
        <div className="col-span-6 space-y-2 px-6 py-5 md:col-span-2 md:border-r">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Visibility</label>
          <select value={visibility} onChange={(e) => setVisibility(e.target.value as "isolated" | "open")} className="select font-mono text-[12px]">
            <option value="isolated">isolated</option>
            <option value="open">open arena</option>
          </select>
        </div>
        <label className="col-span-12 flex items-center gap-3 px-6 py-5 md:col-span-3">
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} className="h-4 w-4 border-borderStrong accent-accent" />
          <span className="font-mono text-[11px] uppercase tracking-[0.12em]">Save artifacts</span>
        </label>
      </div>

      {err && (
        <div className="mx-auto max-w-[1360px] border-b border-danger px-6 py-3 font-mono text-[12px] text-danger">{err}</div>
      )}

      <div className="mx-auto max-w-[1360px] px-6 py-6">
        <button type="submit" disabled={busy || !formatId} className="btn btn-primary h-14 w-full text-[13px]">
          {busy ? "Starting…" : "Start match"}
        </button>
      </div>
    </form>
  );
}
