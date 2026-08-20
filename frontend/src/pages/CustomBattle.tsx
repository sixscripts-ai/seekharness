import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  isHostProviderId,
  splitProviders,
  type BattleDraftOut,
  type BattleSpec,
  type ProviderOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import ProviderSelect from "@/components/ProviderSelect";

type Mode = "quick" | "verified";

function specText(spec: BattleSpec | null | undefined): string {
  if (!spec) return "";
  const files = spec.starter_files
    ? Object.entries(spec.starter_files)
        .map(([path, body]) => `--- ${path}\n${body}`)
        .join("\n\n")
    : "";
  return [
    `title: ${spec.title || ""}`,
    `brief: ${spec.brief || ""}`,
    `deliverables:\n${(spec.deliverables || []).map((d) => `- ${d}`).join("\n")}`,
    `constraints:\n${(spec.constraints || []).map((d) => `- ${d}`).join("\n")}`,
    `required_artifacts: ${(spec.required_artifacts || []).join(", ")}`,
    `judge_rubric: ${spec.judge_rubric || ""}`,
    files ? `starter_files:\n${files}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
}

export default function CustomBattle() {
  const { user, jwt, refreshJwt } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("quick");
  const [draft, setDraft] = useState<BattleDraftOut | null>(null);
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [brief, setBrief] = useState("");
  const [testCode, setTestCode] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [judgeId, setJudgeId] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [save, setSave] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const { host, yours } = useMemo(() => splitProviders(providers), [providers]);

  useEffect(() => {
    if (!jwt) return;
    (async () => {
      const token = (await refreshJwt()) || jwt;
      try {
        const p = await api.providers(token);
        setProviders(p);
        const hostIds = p.filter((x) => isHostProviderId(x.id)).map((x) => x.id);
        const fb = hostIds[0] || p[0]?.id || "host:openrouter-free";
        const alt = hostIds[1] || hostIds.find((id) => id !== fb) || fb;
        setSelected((prev) => (prev.length ? prev : [fb, alt]));
      } catch {
        setProviders([]);
      }
    })();
  }, [jwt]);

  useEffect(() => {
    if (!draft?.spec) return;
    setTitle(draft.spec.title || "");
    setBrief(draft.spec.brief || "");
    setTestCode(draft.spec.test_code || "");
  }, [draft?.revision, draft?.spec]);

  async function tokenOrThrow(): Promise<string> {
    const token = (await refreshJwt()) || jwt;
    if (!token) throw new Error("Not signed in");
    return token;
  }

  async function ensureDraft(nextMode = mode): Promise<BattleDraftOut> {
    if (draft && draft.mode === nextMode && draft.status !== "launched") return draft;
    const token = await tokenOrThrow();
    const created = await api.createBattleDraft(token, { mode: nextMode });
    setDraft(created);
    return created;
  }

  async function onMode(next: Mode) {
    setMode(next);
    setErr(null);
    try {
      const created = await ensureDraft(next);
      setDraft(created);
    } catch (er) {
      setErr(er instanceof Error ? er.message : "Could not create draft");
    }
  }

  async function sendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim()) return;
    setBusy("chat");
    setErr(null);
    try {
      const token = await tokenOrThrow();
      const current = await ensureDraft();
      const updated = await api.postDraftMessage(token, current.id, { content: message.trim() });
      setDraft(updated);
      setMessage("");
    } catch (er) {
      setErr(er instanceof Error ? er.message : "Architect failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveSpec() {
    if (!draft) return;
    setBusy("spec");
    setErr(null);
    try {
      const token = await tokenOrThrow();
      const updated = await api.patchDraftSpec(token, draft.id, {
        title,
        brief,
        test_code: mode === "verified" ? testCode : null,
      });
      setDraft(updated);
    } catch (er) {
      setErr(er instanceof Error ? er.message : "Spec update failed");
    } finally {
      setBusy(null);
    }
  }

  function addFighter() {
    if (selected.length >= 6) return;
    const fb = host[0]?.id || providers[0]?.id || "host:openrouter-free";
    const used = new Set(selected);
    const next = host.find((p) => !used.has(p.id))?.id || yours.find((p) => !used.has(p.id))?.id || fb;
    setSelected([...selected, next]);
  }

  async function launch() {
    if (!draft) return;
    const allowed = new Set(providers.map((p) => p.id));
    const invalid = selected.some((id) => !allowed.has(id) && !isHostProviderId(id));
    if (invalid) {
      setErr("Invalid provider — choose any host: or your own");
      return;
    }
    if (new Set(selected).size !== selected.length) {
      setErr("Fighters must be unique models");
      return;
    }
    setBusy("launch");
    setErr(null);
    try {
      const token = await tokenOrThrow();
      const battle = await api.launchDraft(token, draft.id, {
        revision: draft.revision,
        model_ids: selected,
        timeout_seconds: timeoutSec,
        save,
        judge_provider_id: judgeId || null,
      });
      try {
        const key = "arena_battle_ids";
        const prev = JSON.parse(localStorage.getItem(key) || "[]") as string[];
        localStorage.setItem(key, JSON.stringify([battle.id, ...prev].slice(0, 50)));
      } catch {
        void 0;
      }
      nav(`/battles/${battle.id}`);
    } catch (er) {
      setErr(er instanceof Error ? er.message : "Launch failed");
    } finally {
      setBusy(null);
    }
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[36ch] space-y-3 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Custom battle</div>
          <p className="text-[14px] text-muted">Log in to chat a brief and freeze it before launch.</p>
          <Link to="/login" className="btn btn-primary mx-auto h-10 px-6">Log in</Link>
        </div>
      </div>
    );
  }

  const ready = draft?.status === "ready";
  const transcript = draft?.transcript || [];

  return (
    <div className="min-h-[calc(100vh-56px)] bg-background text-foreground">
      <div className="border-b border-border px-6 py-5">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">Battle architect</div>
            <h1 className="mt-1 font-display text-[40px] leading-none tracking-[-0.04em] md:text-[56px]">
              Custom prompt
            </h1>
          </div>
          <div className="flex gap-2">
            {(["quick", "verified"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onMode(m)}
                className={`btn h-10 px-4 text-[12px] ${mode === m ? "btn-primary" : "btn-ghost"}`}
              >
                {m === "quick" ? "Quick · judge-only" : "Verified · Python tests"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12">
        <section className="col-span-12 border-b border-border lg:col-span-6 lg:border-r lg:border-b-0">
          <div className="px-6 py-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Chat</div>
            <div className="mt-3 max-h-[360px] space-y-3 overflow-y-auto">
              {transcript.length === 0 && (
                <p className="text-[13px] text-muted">
                  Describe the battle. Quick mode freezes a brief for any language.
                  Verified mode compiles Python acceptance tests you must approve.
                </p>
              )}
              {transcript.map((turn, i) => (
                <div key={`${turn.role}-${i}`} className="border-b border-border pb-3">
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">{turn.role}</div>
                  <p className="mt-1 whitespace-pre-wrap text-[13px] leading-5">{turn.content}</p>
                </div>
              ))}
            </div>
            <form onSubmit={sendMessage} className="mt-4 space-y-3">
              <textarea
                className="input min-h-[96px] font-mono text-[12px]"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={mode === "verified" ? "Python kata, API, or bug to fix…" : "Any language or artifact battle…"}
              />
              <button type="submit" disabled={busy === "chat" || !message.trim()} className="btn btn-primary h-10 px-4 text-[12px]">
                {busy === "chat" ? "Compiling…" : "Send to architect"}
              </button>
            </form>
          </div>
        </section>

        <section className="col-span-12 lg:col-span-6">
          <div className="px-6 py-5">
            <div className="flex items-center justify-between">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Frozen spec</div>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                rev {draft?.revision ?? 0} · {draft?.status || "draft"}
              </span>
            </div>
            <label className="mt-4 block font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Title</label>
            <input className="input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} />
            <label className="mt-3 block font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Brief</label>
            <textarea className="input mt-1 min-h-[120px] font-mono text-[12px]" value={brief} onChange={(e) => setBrief(e.target.value)} />
            {mode === "verified" && (
              <>
                <label className="mt-3 block font-mono text-[10px] uppercase tracking-[0.16em] text-muted">tests/test_target.py</label>
                <textarea className="input mt-1 min-h-[160px] font-mono text-[12px]" value={testCode} onChange={(e) => setTestCode(e.target.value)} />
              </>
            )}
            <pre className="mt-3 max-h-[160px] overflow-auto border border-border bg-surface p-3 font-mono text-[11px] text-muted">
              {specText(draft?.spec)}
            </pre>
            {draft?.spec_hash && (
              <div className="mt-2 font-mono text-[10px] text-muted">spec {draft.spec_hash.slice(0, 16)}</div>
            )}
            <button type="button" onClick={saveSpec} disabled={!draft || busy === "spec"} className="btn btn-ghost mt-3 h-10 px-4 text-[12px]">
              {busy === "spec" ? "Validating…" : "Approve this revision"}
            </button>
          </div>
        </section>
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12 border-y border-border">
        {selected.map((mid, i) => (
          <div key={i} className="col-span-12 border-b border-border px-6 py-6 last:border-b-0 md:col-span-6 md:border-r md:last:border-r-0">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">Fighter {i + 1}</div>
            <div className="mt-3">
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
            {selected.length > 2 && (
              <button
                type="button"
                className="mt-3 font-mono text-[11px] text-muted"
                onClick={() => setSelected(selected.filter((_, idx) => idx !== i))}
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="mx-auto grid max-w-[1360px] grid-cols-12 border-b border-border">
        <div className="col-span-12 space-y-2 border-b border-border px-6 py-5 md:col-span-4 md:border-b-0 md:border-r">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Judge</label>
          <select className="select font-mono text-[12px]" value={judgeId} onChange={(e) => setJudgeId(e.target.value)}>
            <option value="">Default host judge</option>
            {host.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>)}
            {yours.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.model_name}</option>)}
          </select>
        </div>
        <div className="col-span-6 space-y-2 border-r border-border px-6 py-5 md:col-span-3">
          <label className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Timeout</label>
          <input type="number" min={30} max={3600} value={timeoutSec} onChange={(e) => setTimeoutSec(Number(e.target.value))} className="input font-mono" />
        </div>
        <div className="col-span-6 flex items-end px-6 py-5 md:col-span-3 md:border-r">
          <button type="button" onClick={addFighter} disabled={selected.length >= 6} className="btn btn-ghost h-10 px-4 text-[12px]">
            Add fighter
          </button>
        </div>
        <label className="col-span-12 flex items-center gap-3 px-6 py-5 md:col-span-2">
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} className="h-4 w-4 border-borderStrong accent-accent" />
          <span className="font-mono text-[11px] uppercase tracking-[0.12em]">Save</span>
        </label>
      </div>

      {err && (
        <div className="mx-auto max-w-[1360px] border-b border-danger px-6 py-3 font-mono text-[12px] text-danger">{err}</div>
      )}
      {draft?.architect_error && (
        <div className="mx-auto max-w-[1360px] border-b border-border px-6 py-3 font-mono text-[12px] text-muted">{draft.architect_error}</div>
      )}

      <div className="mx-auto max-w-[1360px] px-6 py-6">
        <button type="button" disabled={!ready || busy === "launch"} onClick={launch} className="btn btn-primary h-14 w-full text-[13px]">
          {busy === "launch" ? "Launching…" : ready ? "Launch isolated battle" : "Approve a spec to launch"}
        </button>
        <p className="mt-3 font-mono text-[11px] text-muted">Unranked. Isolated workspaces. Same frozen brief for every fighter.</p>
      </div>
    </div>
  );
}
