import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Code2,
  Cpu,
  Flame,
  Layers,
  Lock,
  Plus,
  RefreshCw,
  Send,
  Shield,
  Sparkles,
  Swords,
  Trash2,
  Zap,
} from "lucide-react";
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

const PROMPT_SUGGESTIONS = [
  "Django ORM N+1 Query Prefetch Fix",
  "FastAPI JWT Token Refresh & Expiry",
  "SQLAlchemy Connection Pool Starvation",
  "Distributed LRU Cache with TTL Expiry",
  "Async WebSocket Heartbeat & Reconnection",
  "Thread-Safe Bounded Queue with Poison Pill",
];

function cleanErrorMessage(err: unknown, fallback: string): string {
  if (!err) return fallback;
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message);
      if (parsed && typeof parsed.detail === "string") return parsed.detail;
    } catch {}
    return err.message;
  }
  return String(err);
}

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
  const [searchParams, setSearchParams] = useSearchParams();

  const initialMode: Mode =
    searchParams.get("mode") === "verified" ? "verified" : "quick";

  const [mode, setMode] = useState<Mode>(initialMode);

  useEffect(() => {
    const requested = searchParams.get("mode");
    if (requested === "verified" || requested === "quick") {
      setMode(requested);
    }
  }, [searchParams]);

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
  const [showRawSpec, setShowRawSpec] = useState(false);

  const { host, yours } = useMemo(
    () => splitProviders(providers),
    [providers],
  );

  useEffect(() => {
    if (!jwt) return;
    (async () => {
      const token = (await refreshJwt()) || jwt;
      try {
        const p = await api.providers(token);
        setProviders(p);
        const hostIds = p
          .filter((x) => isHostProviderId(x.id))
          .map((x) => x.id);
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
    if (draft && draft.mode === nextMode && draft.status !== "launched")
      return draft;
    const token = await tokenOrThrow();
    const created = await api.createBattleDraft(token, { mode: nextMode });
    setDraft(created);
    return created;
  }

  async function onMode(next: Mode) {
    setMode(next);
    setSearchParams({ mode: next });
    setErr(null);
    try {
      const created = await ensureDraft(next);
      setDraft(created);
    } catch (er) {
      setErr(cleanErrorMessage(er, "Could not create draft"));
    }
  }

  async function sendMessage(e?: React.FormEvent, customMsg?: string) {
    if (e) e.preventDefault();
    const textToSend = (customMsg !== undefined ? customMsg : message).trim();
    if (!textToSend) return;
    setBusy("chat");
    setErr(null);
    try {
      const token = await tokenOrThrow();
      const current = await ensureDraft();
      const updated = await api.postDraftMessage(token, current.id, {
        content: textToSend,
      });
      setDraft(updated);
      if (customMsg === undefined) {
        setMessage("");
      }
    } catch (er) {
      setErr(cleanErrorMessage(er, "Architect failed"));
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
      setErr(cleanErrorMessage(er, "Spec update failed"));
    } finally {
      setBusy(null);
    }
  }

  function addFighter() {
    if (selected.length >= 6) return;
    const fb = host[0]?.id || providers[0]?.id || "host:openrouter-free";
    const used = new Set(selected);
    const next =
      host.find((p) => !used.has(p.id))?.id ||
      yours.find((p) => !used.has(p.id))?.id ||
      fb;
    setSelected([...selected, next]);
  }

  async function launch() {
    if (!draft) return;
    const allowed = new Set(providers.map((p) => p.id));
    const invalid = selected.some(
      (id) => !allowed.has(id) && !isHostProviderId(id),
    );
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
        const prev = JSON.parse(
          localStorage.getItem(key) || "[]",
        ) as string[];
        localStorage.setItem(
          key,
          JSON.stringify([battle.id, ...prev].slice(0, 50)),
        );
      } catch {
        void 0;
      }
      nav(`/battles/${battle.id}`);
    } catch (er) {
      setErr(cleanErrorMessage(er, "Launch failed"));
    } finally {
      setBusy(null);
    }
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[42ch] space-y-4 rounded-2xl border border-border bg-[#09090E] p-8 text-center shadow-2xl">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-accent/40 bg-accent/15 text-accent">
            <Swords className="h-6 w-6" />
          </div>
          <div className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-accent">
            Custom Arena Protocol
          </div>
          <h2 className="text-xl font-extrabold text-white">
            Sign in to Architect Battles
          </h2>
          <p className="text-xs leading-relaxed text-muted">
            Log in to chat with the AI architect, generate frozen briefs,
            compile acceptance test suites, and launch isolated microVM duels.
          </p>
          <Link
            to="/login"
            className="btn btn-primary mx-auto flex h-11 w-full items-center justify-center gap-2 text-xs font-bold"
          >
            <span>Authenticate Session</span>
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    );
  }

  const ready = draft?.status === "ready";
  const transcript = draft?.transcript || [];

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] py-8 text-foreground">
      <div className="mx-auto max-w-[1560px] space-y-8 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* MAIN OBSIDIAN COCKPIT CONTAINER (Matching Home Page Hero bg-[#09090E]) */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-2xl space-y-8 md:p-8">
          {/* Ambient Neon Radial Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.22)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.12)_0%,transparent_70%)]"></div>

          {/* Top Header Stage */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-[#1F1F22] pb-6 lg:flex-row lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
                </span>
                CUSTOM ARENA FORGE • UNRANKED ISOLATED MODAL MICROVMS
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Battle{" "}
                <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                  Architect
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-400">
                Collaborate with the AI architect to iteratively define,
                compile, review, and freeze hermetic acceptance test suites.
              </p>
            </div>

            {/* Mode Selector */}
            <div className="flex items-center gap-2 rounded-xl border border-[#1F1F22] bg-[#050508] p-1.5">
              <button
                type="button"
                onClick={() => onMode("quick")}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold transition-all ${
                  mode === "quick"
                    ? "btn-primary"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <span>⚡ Quick Mode</span>
                <span className="text-[10px] font-normal opacity-80">
                  Judge Rubric
                </span>
              </button>
              <button
                type="button"
                onClick={() => onMode("verified")}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold transition-all ${
                  mode === "verified"
                    ? "btn-primary"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <span>🛡️ Verified Mode</span>
                <span className="text-[10px] font-normal opacity-80">
                  Pytest Suite
                </span>
              </button>
            </div>
          </div>

          {/* Progressive Lifecycle Stage Pipeline */}
          <div className="relative z-10 flex items-center justify-between overflow-x-auto rounded-xl border border-[#1F1F22] bg-[#050508] px-6 py-3.5 text-xs mono">
            <div className="flex items-center gap-2 text-emerald-400 font-bold">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-950 border border-emerald-500/40 text-[10px]">
                ✓
              </span>
              <span>DESCRIBE</span>
            </div>
            <span className="text-zinc-600">→</span>
            <div className="flex items-center gap-2 text-emerald-400 font-bold">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-950 border border-emerald-500/40 text-[10px]">
                ✓
              </span>
              <span>COMPILE</span>
            </div>
            <span className="text-zinc-600">→</span>
            <div
              className={`flex items-center gap-2 font-bold ${
                ready ? "text-emerald-400" : "text-accent"
              }`}
            >
              <span
                className={`grid h-5 w-5 place-items-center rounded-full text-[10px] ${
                  ready
                    ? "bg-emerald-950 border border-emerald-500/40"
                    : "bg-accent/20 border border-accent animate-pulse"
                }`}
              >
                {ready ? "✓" : "●"}
              </span>
              <span>REVIEW</span>
            </div>
            <span className="text-zinc-600">→</span>
            <div
              className={`flex items-center gap-2 font-bold ${
                ready ? "text-accent" : "text-zinc-500"
              }`}
            >
              <span className="grid h-5 w-5 place-items-center rounded-full border border-zinc-700 bg-zinc-900 text-[10px]">
                {ready ? "●" : "○"}
              </span>
              <span>FREEZE</span>
            </div>
            <span className="text-zinc-600">→</span>
            <div className="flex items-center gap-2 font-bold text-zinc-500">
              <span className="grid h-5 w-5 place-items-center rounded-full border border-zinc-700 bg-zinc-900 text-[10px]">
                ○
              </span>
              <span>DEPLOY</span>
            </div>
          </div>

          {/* =============================================================== */}
          {/* ASYMMETRIC 2-COLUMN STUDIO GRID */}
          {/* =============================================================== */}
          <div className="relative z-10 grid grid-cols-12 gap-7">
            {/* Left Rail (5-Cols): AI Prompt Architect Chat Drawer */}
            <div className="col-span-12 flex flex-col justify-between space-y-4 rounded-xl border border-[#1F1F22] bg-[#050508] p-5 shadow-xl lg:col-span-5">
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-accent animate-pulse"></span>
                    <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                      AI Prompt Architect
                    </span>
                  </div>
                  <span className="mono rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-bold text-accent">
                    MODAL GPT-4.5
                  </span>
                </div>

                {/* Chat Stream History */}
                <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
                  {transcript.length === 0 ? (
                    <div className="space-y-2 rounded-xl border border-accent/30 bg-accent/10 p-4">
                      <div className="mono text-[10px] font-bold uppercase text-accent">
                        ■ SeekHarness Architect
                      </div>
                      <p className="text-xs leading-relaxed text-zinc-300">
                        {mode === "verified"
                          ? "Verified Mode active: Describe a Python challenge, bug fix, or kata. I will generate starter files and automated acceptance test suites in `tests/test_target.py`."
                          : "Quick Mode active: Describe a challenge in any language. I will generate a structured brief, deliverables, and rubric for the automated judge."}
                      </p>
                    </div>
                  ) : null}

                  {transcript.map((turn, i) => {
                    const isUser = turn.role.toLowerCase() === "user";
                    const isSystem =
                      turn.role.toLowerCase().includes("system") ||
                      turn.role.toLowerCase().includes("compiler");
                    return (
                      <div
                        key={`${turn.role}-${i}`}
                        className={`rounded-xl p-3.5 text-xs transition-all ${
                          isUser
                            ? "ml-4 border border-[#2A2A2E] bg-[#161619] text-white"
                            : isSystem
                              ? "border border-emerald-500/30 bg-emerald-950/40 text-emerald-200"
                              : "border border-accent/30 bg-accent/10 text-zinc-200"
                        }`}
                      >
                        <div
                          className={`mono mb-1 text-[10px] font-bold uppercase ${
                            isUser
                              ? "text-zinc-400"
                              : isSystem
                                ? "text-emerald-400"
                                : "text-accent"
                          }`}
                        >
                          {isUser
                            ? "You"
                            : isSystem
                              ? "✓ Compiler Validation"
                              : "■ SeekHarness Architect"}
                        </div>
                        <p className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed">
                          {turn.content}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Chat Input & Idea Chips */}
              <div className="space-y-3 border-t border-[#1F1F22] pt-3">
                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  {PROMPT_SUGGESTIONS.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => sendMessage(undefined, item)}
                      disabled={busy === "chat"}
                      className="mono cursor-pointer whitespace-nowrap rounded-md border border-[#2A2A2E] bg-[#161619] px-2.5 py-1 text-[10px] text-zinc-400 transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                    >
                      {item}
                    </button>
                  ))}
                </div>

                <form onSubmit={sendMessage} className="space-y-2">
                  <textarea
                    className="mono h-20 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] p-2.5 text-xs text-white placeholder:text-zinc-600 focus:border-accent focus:outline-none"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder={
                      mode === "verified"
                        ? "Describe Python challenge, edge cases, or test requirements..."
                        : "Describe any language task or artifact battle..."
                    }
                  />
                  <button
                    type="submit"
                    disabled={busy === "chat" || !message.trim()}
                    className="btn btn-primary flex h-9 w-full items-center justify-center gap-2 rounded-lg text-xs font-bold"
                  >
                    {busy === "chat" ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Compiling Revision…</span>
                      </>
                    ) : (
                      <>
                        <span>Send to Architect</span>
                        <Send className="h-3.5 w-3.5" />
                      </>
                    )}
                  </button>
                </form>
              </div>
            </div>

            {/* Right Canvas (7-Cols): Active Spec & Acceptance Sandbox */}
            <div className="col-span-12 space-y-5 lg:col-span-7">
              {/* Active Spec Card */}
              <div className="space-y-4 rounded-xl border border-[#1F1F22] bg-[#050508] p-5 shadow-xl">
                <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="mono text-xs font-bold uppercase tracking-wider text-white">
                      Active Specification
                    </span>
                    <span
                      className={`mono rounded px-2.5 py-0.5 text-[10px] font-bold ${
                        ready
                          ? "border border-emerald-500/40 bg-emerald-950/40 text-emerald-400"
                          : "border border-amber-500/40 bg-amber-950/40 text-amber-400"
                      }`}
                    >
                      {ready
                        ? `REV #${draft?.revision ?? 0} LOCKED`
                        : `REV #${draft?.revision ?? 0} DRAFT`}
                    </span>
                  </div>
                  {draft?.spec_hash && (
                    <span className="mono text-[10px] text-zinc-500">
                      hash: {draft.spec_hash.slice(0, 14)}
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Battle Title
                    </label>
                    <input
                      className="mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-3.5 py-2 text-xs font-semibold text-white focus:border-accent focus:outline-none"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Title of this custom battle..."
                    />
                  </div>

                  <div>
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Brief Directive
                    </label>
                    <textarea
                      className="mono mt-1 h-24 w-full rounded-lg border border-[#1F1F22] bg-[#09090E] p-3 text-xs leading-relaxed text-zinc-300 focus:border-accent focus:outline-none"
                      value={brief}
                      onChange={(e) => setBrief(e.target.value)}
                      placeholder="Provide precise functional guidelines and constraints for the competing models..."
                    />
                  </div>

                  {mode === "verified" && (
                    <div>
                      <div className="flex items-center justify-between">
                        <label className="mono text-[10px] font-bold uppercase tracking-wider text-accent">
                          Pytest Sandbox (tests/test_target.py)
                        </label>
                        <span className="mono text-[10px] text-zinc-400">
                          Automated acceptance tests
                        </span>
                      </div>
                      <textarea
                        className="mono mt-1 h-36 w-full rounded-lg border border-[#1F1F22] bg-[#000000] p-3 text-[11px] leading-relaxed text-emerald-300 focus:border-accent focus:outline-none"
                        value={testCode}
                        onChange={(e) => setTestCode(e.target.value)}
                        placeholder="def test_example():\n    assert True"
                      />
                    </div>
                  )}

                  {/* Optional Spec Inspector Accordion */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowRawSpec(!showRawSpec)}
                      className="mono flex items-center gap-1 text-[10px] text-zinc-400 hover:text-white"
                    >
                      <span>{showRawSpec ? "▼ Hide" : "▶ Show"} Raw YAML Spec & Starter Files</span>
                    </button>
                    {showRawSpec && (
                      <pre className="mono mt-2 max-h-36 overflow-auto rounded-lg border border-[#1F1F22] bg-[#000000] p-3 text-[10.5px] text-zinc-400">
                        {specText(draft?.spec) || "# No additional spec details generated yet."}
                      </pre>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={saveSpec}
                    disabled={!draft || busy === "spec"}
                    className="mono flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/30 text-xs font-bold uppercase tracking-wider text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.15)] transition-all hover:bg-emerald-950/50 disabled:opacity-50"
                  >
                    {busy === "spec" ? (
                      <>
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        <span>Validating Spec…</span>
                      </>
                    ) : (
                      <>
                        <Check className="h-4 w-4" />
                        <span>[ FREEZE SPEC ] · Lock Revision</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Contenders & Parameter Dock */}
              <div className="space-y-4 rounded-xl border border-[#2A2A2E] bg-[#0D0D0F] p-5 shadow-lg">
                <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-accent">■</span>
                    <span className="mono text-xs font-bold uppercase tracking-widest text-white">
                      Contender Lineup ({selected.length})
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={addFighter}
                    disabled={selected.length >= 6}
                    className="mono text-xs font-bold text-accent hover:underline disabled:opacity-40"
                  >
                    + Add Contender
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {selected.map((mid, i) => (
                    <div
                      key={i}
                      className="space-y-2 rounded-xl border border-accent/40 bg-accent/10 p-3.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="mono grid h-6 w-6 place-items-center rounded bg-accent/20 text-[10px] font-bold text-accent">
                            P{i + 1}
                          </span>
                          <span className="mono text-[11px] font-bold uppercase text-white">
                            Fighter {i + 1}
                          </span>
                        </div>
                        {selected.length > 2 && (
                          <button
                            type="button"
                            onClick={() =>
                              setSelected(selected.filter((_, idx) => idx !== i))
                            }
                            className="text-zinc-500 hover:text-red-400"
                            title="Remove Fighter"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
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
                  ))}
                </div>

                {/* Judge & Timeout Controls */}
                <div className="grid grid-cols-12 gap-4 border-t border-[#1F1F22] pt-4">
                  <div className="col-span-12 space-y-1 sm:col-span-6">
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Judge Provider
                    </label>
                    <select
                      className="mono w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-3 py-2 text-xs text-white focus:border-accent focus:outline-none"
                      value={judgeId}
                      onChange={(e) => setJudgeId(e.target.value)}
                    >
                      <option value="">Default Modal Kimi-K3</option>
                      {host.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} · {p.model_name}
                        </option>
                      ))}
                      {yours.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} · {p.model_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="col-span-6 space-y-1 sm:col-span-3">
                    <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Timeout (Sec)
                    </label>
                    <input
                      type="number"
                      min={30}
                      max={3600}
                      value={timeoutSec}
                      onChange={(e) => setTimeoutSec(Number(e.target.value))}
                      className="mono w-full rounded-lg border border-[#1F1F22] bg-[#09090E] px-3 py-2 text-xs text-white focus:border-accent focus:outline-none"
                    />
                  </div>

                  <div className="col-span-6 flex items-center pt-5 sm:col-span-3">
                    <label className="mono flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
                      <input
                        type="checkbox"
                        checked={save}
                        onChange={(e) => setSave(e.target.checked)}
                        className="h-4 w-4 rounded accent-accent"
                      />
                      <span>Save Replay</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Error Warnings */}
              {err && (
                <div className="flex items-center gap-2 rounded-xl border border-red-500/40 bg-red-950/40 p-3.5 text-xs text-red-200">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" />
                  <span className="mono">{err}</span>
                </div>
              )}
              {draft?.architect_error && (
                <div className="flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-950/40 p-3.5 text-xs text-amber-200">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                  <span className="mono">{draft.architect_error}</span>
                </div>
              )}

              {/* Bottom Action Console */}
              <div className="space-y-3">
                <button
                  type="button"
                  disabled={!ready || busy === "launch"}
                  onClick={launch}
                  className="btn btn-primary flex h-14 w-full items-center justify-center gap-3 rounded-xl text-sm font-extrabold tracking-wide shadow-[0_0_20px_rgba(255,0,160,0.4)] disabled:opacity-50"
                >
                  {busy === "launch" ? (
                    <>
                      <RefreshCw className="h-5 w-5 animate-spin" />
                      <span>Igniting Isolated Modal Sandboxes…</span>
                    </>
                  ) : ready ? (
                    <>
                      <Swords className="h-5 w-5" />
                      <span>⚔️ Launch Isolated Battle</span>
                      <ChevronRight className="h-5 w-5" />
                    </>
                  ) : (
                    <span>Approve Spec Revision to Launch</span>
                  )}
                </button>
                <div className="mono flex items-center justify-between text-[11px] text-zinc-500">
                  <span>Unranked · Isolated MicroVM Sandboxes</span>
                  <span>Identical frozen acceptance brief for all fighters</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
