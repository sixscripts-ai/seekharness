import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Eye,
  EyeOff,
  Flame,
  HelpCircle,
  Key,
  Layers,
  Lock,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldCheck,
  Sparkles,
  Swords,
  Trash2,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { ApiError, api, isHostProviderId, type ProviderOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useHiddenProviders } from "@/lib/hiddenProviders";

declare const __DEFAULT_MODAL_URL__: string;

type CatalogModel = {
  arena_model_id: string;
  provider_id: string;
  upstream_model: string;
  display_name: string;
  roles: string[];
  tier: string;
  context: number | null;
  context_class: string;
  reasoning_support: boolean;
  reasoning_efforts: string[];
  tool_support: boolean;
  structured_output_support: boolean;
  status: string;
  available: boolean;
};

type CatalogProvider = {
  id: string;
  protocol: string;
  base_url: string;
  credential_env: string;
  auth_style: string;
  status: string;
};

type ModelCatalog = {
  providers: CatalogProvider[];
  models: CatalogModel[];
};

async function loadModelCatalog(token: string): Promise<ModelCatalog> {
  const base = (import.meta.env.VITE_MODAL_URL || __DEFAULT_MODAL_URL__).replace(
    /\/$/,
    "",
  );
  const res = await fetch(`${base}/providers/catalog`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  return JSON.parse(text) as ModelCatalog;
}

function formatContext(model: CatalogModel): string {
  if (model.context && model.context_class) {
    const window =
      model.context >= 1000
        ? `${Math.round(model.context / 1000)}k`
        : String(model.context);
    return `${window} · ${model.context_class}`;
  }
  if (model.context_class) return model.context_class;
  return "n/a";
}

function formatRoles(roles: string[]): string {
  if (!roles.length) return "none";
  return roles
    .map((role) => role.charAt(0).toUpperCase() + role.slice(1))
    .join(" · ");
}

function formatReasoning(model: CatalogModel): string {
  if (!model.reasoning_support) return "none";
  return model.reasoning_efforts.join(", ") || "supported";
}

function catalogStatusLabel(model: CatalogModel): {
  label: string;
  className: string;
} {
  if (model.status === "retired") {
    return {
      label: "RETIRED",
      className: "border-zinc-600 bg-zinc-900 text-zinc-400",
    };
  }
  if (!model.available) {
    return {
      label: "UNAVAILABLE",
      className: "border-amber-500/40 bg-amber-950/40 text-amber-300",
    };
  }
  if (model.status === "preview") {
    return {
      label: "PREVIEW",
      className: "border-sky-500/40 bg-sky-950/40 text-sky-300",
    };
  }
  return {
    label: "CONFIGURED",
    className: "border-emerald-500/40 bg-emerald-950/40 text-emerald-400",
  };
}

type AuthoritativeState = "UNTESTED" | "TESTING" | "HEALTHY" | "ERROR";

interface HealthRecord {
  state: AuthoritativeState;
  latencyMs?: number;
  lastChecked?: string;
  detail?: string;
}

type PresetKey =
  | "openai"
  | "anthropic"
  | "openrouter"
  | "deepseek"
  | "xai"
  | "groq"
  | "mistral"
  | "custom";

interface PresetConfig {
  name: string;
  brand: string;
  base_url: string;
  auth_style: string;
  model_name: string;
  context_window: string;
  description: string;
}

const PRESETS: Record<PresetKey, PresetConfig> = {
  anthropic: {
    name: "Anthropic Claude",
    brand: "Anthropic",
    base_url: "https://api.anthropic.com/v1",
    auth_style: "bearer",
    model_name: "claude-3-7-sonnet-20250219",
    context_window: "200k",
    description: "Claude 3.7 Sonnet hybrid reasoning models.",
  },
  openai: {
    name: "OpenAI GPT",
    brand: "OpenAI",
    base_url: "https://api.openai.com/v1",
    auth_style: "bearer",
    model_name: "gpt-4o",
    context_window: "128k",
    description: "Standard OpenAI endpoints (GPT-4o, o3-mini).",
  },
  deepseek: {
    name: "DeepSeek Official",
    brand: "DeepSeek",
    base_url: "https://api.deepseek.com/v1",
    auth_style: "bearer",
    model_name: "deepseek-reasoner",
    context_window: "64k",
    description: "DeepSeek R1 and V3 reasoning APIs.",
  },
  openrouter: {
    name: "OpenRouter Gateway",
    brand: "OpenRouter",
    base_url: "https://openrouter.ai/api/v1",
    auth_style: "bearer",
    model_name: "anthropic/claude-3.7-sonnet",
    context_window: "200k",
    description: "Universal multi-provider router gateway.",
  },
  groq: {
    name: "Groq High Speed",
    brand: "Groq",
    base_url: "https://api.groq.com/openai/v1",
    auth_style: "bearer",
    model_name: "llama-3.3-70b-versatile",
    context_window: "128k",
    description: "Ultra-low latency LPU hardware inference.",
  },
  xai: {
    name: "xAI Grok",
    brand: "xAI",
    base_url: "https://api.x.ai/v1",
    auth_style: "bearer",
    model_name: "grok-2-1212",
    context_window: "128k",
    description: "Grok 2 and Grok Beta models.",
  },
  mistral: {
    name: "Mistral AI",
    brand: "Mistral",
    base_url: "https://api.mistral.ai/v1",
    auth_style: "bearer",
    model_name: "mistral-large-latest",
    context_window: "128k",
    description: "Mistral Large and Codestral endpoints.",
  },
  custom: {
    name: "Custom Gateway",
    brand: "Custom",
    base_url: "https://api.openai.com/v1",
    auth_style: "bearer",
    model_name: "",
    context_window: "Flexible",
    description: "Any OpenAI-compatible or Modal reverse proxy endpoint.",
  },
};

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

function formatRelativeTime(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 30) return "Just now";
  if (seconds < 90) return "1 min ago";
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
}

export default function Providers() {
  const { user, jwt, refreshJwt } = useAuth();
  const nav = useNavigate();
  const { hiddenIds, hide, toggle, isHidden, unhide, clearAll } =
    useHiddenProviders();

  const [items, setItems] = useState<ProviderOut[]>([]);
  const [catalog, setCatalog] = useState<ModelCatalog>({
    providers: [],
    models: [],
  });
  const [loading, setLoading] = useState(true);
  const [filterQuery, setFilterQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "personal" | "hidden">(
    "all",
  );

  // Health Tracking Map: provider_id -> HealthRecord
  const [healthMap, setHealthMap] = useState<Record<string, HealthRecord>>({});

  // Feedback notifications
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Modal State for Registering / Editing
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ProviderOut | null>(
    null,
  );
  const [activePreset, setActivePreset] = useState<PresetKey>("anthropic");
  const [name, setName] = useState(PRESETS.anthropic.name);
  const [baseUrl, setBaseUrl] = useState(PRESETS.anthropic.base_url);
  const [apiKey, setApiKey] = useState("");
  const [authStyle, setAuthStyle] = useState(PRESETS.anthropic.auth_style);
  const [modelName, setModelName] = useState(PRESETS.anthropic.model_name);
  const [showKeyText, setShowKeyText] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalTestStatus, setModalTestStatus] = useState<{
    tested: boolean;
    ok: boolean;
    text: string;
  } | null>(null);

  // Delete Confirmation Modal State
  const [deleteTarget, setDeleteTarget] = useState<ProviderOut | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!jwt) {
      setLoading(false);
      return;
    }
    loadProviders();
  }, [jwt]);

  async function loadProviders() {
    setLoading(true);
    setErr(null);
    try {
      const token = (await refreshJwt()) || jwt;
      if (!token) return;
      const [data, modelCatalog] = await Promise.all([
        api.providers(token),
        loadModelCatalog(token),
      ]);
      setItems(data);
      setCatalog(modelCatalog);
    } catch (e) {
      setErr(cleanErrorMessage(e, "Failed to load provider registry"));
    } finally {
      setLoading(false);
    }
  }

  const providerById = useMemo(
    () => Object.fromEntries(catalog.providers.map((p) => [p.id, p])),
    [catalog.providers],
  );

  const { platformModels, personalProviders } = useMemo(() => {
    return {
      platformModels: catalog.models,
      personalProviders: items.filter((p) => !isHostProviderId(p.id)),
    };
  }, [catalog.models, items]);

  function matchesProviderSearch(p: ProviderOut) {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      p.model_name.toLowerCase().includes(q) ||
      p.base_url.toLowerCase().includes(q)
    );
  }

  function matchesCatalogSearch(model: CatalogModel) {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    const provider = providerById[model.provider_id];
    return (
      model.display_name.toLowerCase().includes(q) ||
      model.upstream_model.toLowerCase().includes(q) ||
      model.provider_id.toLowerCase().includes(q) ||
      model.tier.toLowerCase().includes(q) ||
      model.status.toLowerCase().includes(q) ||
      model.roles.some((role) => role.toLowerCase().includes(q)) ||
      Boolean(provider?.base_url.toLowerCase().includes(q))
    );
  }

  const visiblePlatform = useMemo(() => {
    return platformModels.filter((model) => {
      const hidden = isHidden(model.arena_model_id);
      if (activeTab === "hidden") return hidden && matchesCatalogSearch(model);
      return !hidden && matchesCatalogSearch(model);
    });
  }, [platformModels, activeTab, isHidden, filterQuery, providerById]);

  const visiblePersonal = useMemo(() => {
    return personalProviders.filter((p) => {
      if (activeTab === "hidden") return isHidden(p.id) && matchesProviderSearch(p);
      return !isHidden(p.id) && matchesProviderSearch(p);
    });
  }, [personalProviders, activeTab, isHidden, filterQuery]);

  const totalActiveCount =
    platformModels.filter((model) => !isHidden(model.arena_model_id)).length +
    personalProviders.filter((p) => !isHidden(p.id)).length;
  const totalHiddenCount =
    platformModels.filter((model) => isHidden(model.arena_model_id)).length +
    personalProviders.filter((p) => isHidden(p.id)).length;

  function handleToggleHide(id: string, name: string) {
    const isNowHidden = toggle(id);
    if (isNowHidden) {
      setMsg(`Removed "${name}" from active arena lineup.`);
    } else {
      setMsg(`Restored "${name}" to active arena lineup.`);
    }
  }

  // Test provider connection with real backend verification
  async function testProviderConnection(providerId: string) {
    const token = (await refreshJwt()) || jwt;
    if (!token) return;

    setHealthMap((prev) => ({
      ...prev,
      [providerId]: {
        state: "TESTING",
      },
    }));

    try {
      const res = await api.testProviderHealth(token, providerId);
      const now = new Date();
      if (res.ok && res.status === "HEALTHY") {
        setHealthMap((prev) => ({
          ...prev,
          [providerId]: {
            state: "HEALTHY",
            latencyMs: res.latency_ms,
            lastChecked: formatRelativeTime(now),
            detail: undefined,
          },
        }));
      } else {
        setHealthMap((prev) => ({
          ...prev,
          [providerId]: {
            state: "ERROR",
            latencyMs: res.latency_ms,
            lastChecked: formatRelativeTime(now),
            detail: res.detail || "Provider returned non-200 status",
          },
        }));
      }
    } catch (e) {
      const now = new Date();
      setHealthMap((prev) => ({
        ...prev,
        [providerId]: {
          state: "ERROR",
          lastChecked: formatRelativeTime(now),
          detail: cleanErrorMessage(e, "Connection failed"),
        },
      }));
    }
  }

  function openRegisterModal(provider?: ProviderOut) {
    setErr(null);
    setMsg(null);
    setModalTestStatus(null);
    setShowKeyText(false);

    if (provider) {
      setEditingProvider(provider);
      setName(provider.name);
      setBaseUrl(provider.base_url);
      setApiKey(""); // Leave empty unless replacing
      setAuthStyle(provider.auth_style);
      setModelName(provider.model_name);
      setActivePreset("custom");
    } else {
      setEditingProvider(null);
      selectPreset("anthropic");
    }
    setModalOpen(true);
  }

  function selectPreset(key: PresetKey) {
    setActivePreset(key);
    const cfg = PRESETS[key];
    setName(cfg.name);
    setBaseUrl(cfg.base_url);
    setAuthStyle(cfg.auth_style);
    setModelName(cfg.model_name);
    setApiKey("");
    setModalTestStatus(null);
  }

  async function handleSaveProvider(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !baseUrl.trim()) {
      setErr("Name and Base URL are required.");
      return;
    }
    if (!editingProvider && !apiKey.trim()) {
      setErr("API Key is required for new provider registration.");
      return;
    }

    setSubmitting(true);
    setErr(null);
    try {
      const token = (await refreshJwt()) || jwt;
      if (!token) throw new Error("Not authenticated");

      const created = await api.createProvider(token, {
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || "masked_key_reused",
        auth_style: authStyle,
        model_name: modelName.trim(),
      });

      setMsg(`Provider "${created.name}" registered in encrypted vault.`);
      setModalOpen(false);
      await loadProviders();
    } catch (e) {
      setErr(cleanErrorMessage(e, "Failed to register provider"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteProvider() {
    if (!deleteTarget) return;
    setDeleting(true);
    setErr(null);
    try {
      if (isHostProviderId(deleteTarget.id)) {
        hide(deleteTarget.id);
        setMsg(`Platform model "${deleteTarget.name}" removed from active lineup.`);
        setDeleteTarget(null);
        return;
      }
      const token = (await refreshJwt()) || jwt;
      if (!token) throw new Error("Not authenticated");
      await api.deleteProvider(token, deleteTarget.id);
      unhide(deleteTarget.id);
      setItems((current) => current.filter((p) => p.id !== deleteTarget.id));
      setMsg(`Provider "${deleteTarget.name}" permanently deleted from vault.`);
      setDeleteTarget(null);
    } catch (e) {
      setErr(cleanErrorMessage(e, "Failed to delete provider key"));
    } finally {
      setDeleting(false);
    }
  }

  function copyText(text: string, id: string) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  if (!user) {
    return (
      <div className="grid min-h-[70vh] place-items-center px-6">
        <div className="max-w-[44ch] space-y-4 rounded-2xl border border-[#1F1F22] bg-[#09090E] p-8 text-center shadow-2xl">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl border border-accent/40 bg-accent/15 text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
            <Lock className="h-6 w-6" />
          </div>
          <div className="mono text-[11px] font-bold uppercase tracking-[0.2em] text-accent">
            Vault Authentication
          </div>
          <h2 className="text-2xl font-extrabold text-white">
            Model Registry Locked
          </h2>
          <p className="text-xs leading-relaxed text-zinc-400">
            Log in to manage platform-hosted models, register personal API
            credentials with AES-256 encryption, and verify live endpoints.
          </p>
          <Link
            to="/login"
            className="btn btn-primary mx-auto flex h-11 w-full items-center justify-center gap-2 text-xs font-bold"
          >
            <span>Authenticate Session</span>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#0A0A0A] py-8 text-foreground">
      <div className="mx-auto max-w-[1560px] space-y-10 px-4 sm:px-6">
        {/* ================================================================= */}
        {/* HERO CONTAINER WITH RADIAL HOME PAGE GLOWS                        */}
        {/* ================================================================= */}
        <div className="relative overflow-hidden rounded-2xl border border-[#1F1F22] bg-[#09090E] p-6 shadow-2xl space-y-8 md:p-8">
          {/* Ambient Neon Radial Glows */}
          <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.22)_0%,transparent_70%)]"></div>
          <div className="pointer-events-none absolute -bottom-24 -left-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(255,0,160,0.12)_0%,transparent_70%)]"></div>

          {/* Header Row */}
          <div className="relative z-10 flex flex-col justify-between gap-6 border-b border-[#1F1F22] pb-6 lg:flex-row lg:items-end">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1 text-[11px] font-semibold text-accent shadow-[0_0_12px_rgba(255,0,160,0.25)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent"></span>
                </span>
                AUTHORITATIVE MODEL REGISTRY • ZERO FABRICATED LOGS
              </div>

              <h1 className="text-3xl font-extrabold tracking-[-0.03em] text-white md:text-4xl">
                Model{" "}
                <span className="text-accent drop-shadow-[0_0_20px_rgba(255,0,160,0.45)]">
                  Registry
                </span>
              </h1>
              <p className="max-w-2xl text-xs leading-relaxed text-zinc-400">
                Authoritative catalog of platform-hosted models and encrypted
                personal credentials with real-time health verification.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => openRegisterModal()}
                className="btn btn-primary flex h-11 items-center gap-2 px-6 text-xs font-bold shadow-[0_0_18px_rgba(255,0,160,0.4)]"
              >
                <Plus className="h-4 w-4" />
                <span>Register Provider</span>
              </button>
            </div>
          </div>

          {loading && (
            <div className="relative z-10 flex items-center gap-2 rounded-xl border border-[#1F1F22] bg-[#0D0D0F] p-4 text-xs text-zinc-400">
              <RefreshCw className="h-4 w-4 animate-spin text-accent" />
              <span className="mono">Loading model registry…</span>
            </div>
          )}

          {/* Feedback Notices */}
          {msg && (
            <div className="relative z-10 flex items-center justify-between rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-4 text-xs text-emerald-200">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span className="mono">{msg}</span>
              </div>
              <button
                type="button"
                onClick={() => setMsg(null)}
                className="text-emerald-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {err && (
            <div className="relative z-10 flex items-center justify-between rounded-xl border border-red-500/40 bg-red-950/40 p-4 text-xs text-red-200">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-red-400" />
                <span className="mono">{err}</span>
              </div>
              <button
                type="button"
                onClick={() => setErr(null)}
                className="text-red-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* =============================================================== */}
          {/* GLOBAL TABS & SEARCH CONTROLS                                    */}
          {/* =============================================================== */}
          <div className="relative z-10 flex flex-col gap-4 border-b border-[#1F1F22] pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-1.5 rounded-xl border border-[#1F1F22] bg-[#050508] p-1.5">
              <button
                type="button"
                onClick={() => setActiveTab("all")}
                className={`mono rounded-lg px-4 py-2 text-xs font-bold transition-all ${
                  activeTab === "all"
                    ? "bg-accent text-white shadow-[0_0_12px_rgba(255,0,160,0.35)]"
                    : "text-zinc-400 hover:text-white hover:bg-[#161619]"
                }`}
              >
                All Active ({totalActiveCount})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("hidden")}
                className={`mono rounded-lg px-4 py-2 text-xs font-bold transition-all ${
                  activeTab === "hidden"
                    ? "bg-accent text-white shadow-[0_0_12px_rgba(255,0,160,0.35)]"
                    : "text-zinc-400 hover:text-white hover:bg-[#161619]"
                }`}
              >
                Hidden ({totalHiddenCount})
              </button>
            </div>

            <div className="flex items-center gap-3">
              {activeTab === "hidden" && totalHiddenCount > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    clearAll();
                    setMsg("Restored all hidden models to active arena lineup.");
                  }}
                  className="mono h-9 px-3.5 rounded-xl border border-emerald-500/40 bg-emerald-950/30 text-xs font-bold text-emerald-400 hover:bg-emerald-950/60"
                >
                  [ RESTORE ALL HIDDEN ]
                </button>
              )}

              <div className="relative">
                <Search className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  placeholder="Search models & credentials..."
                  className="mono h-9 w-60 rounded-xl border border-[#1F1F22] bg-[#050508] pl-9 pr-3 text-xs text-white placeholder:text-zinc-600 focus:border-accent focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* =============================================================== */}
          {/* TAB 1: ALL ACTIVE MODELS                                         */}
          {/* =============================================================== */}
          {activeTab === "all" && (
            <div className="relative z-10 space-y-8">
              {/* Platform Models */}
              {visiblePlatform.length > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-accent">■</span>
                      <h2 className="mono text-xs font-bold uppercase tracking-widest text-white">
                        Platform Models ({visiblePlatform.length})
                      </h2>
                    </div>
                    <span className="mono text-[10px] text-zinc-500">
                      HOSTED BY MODAL & SEEKHARNESS CLUSTER
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {visiblePlatform.map((model) => {
                      const health = healthMap[model.arena_model_id] || {
                        state: "UNTESTED",
                      };
                      const isTesting = health.state === "TESTING";
                      const catalogStatus = catalogStatusLabel(model);
                      const liveStatus =
                        health.state === "HEALTHY"
                          ? {
                              label: "HEALTHY",
                              className:
                                "border-emerald-500/40 bg-emerald-950/40 text-emerald-400",
                            }
                          : health.state === "ERROR"
                            ? {
                                label: "ERROR",
                                className:
                                  "border-red-500/40 bg-red-950/40 text-red-400",
                              }
                            : health.state === "TESTING"
                              ? {
                                  label: "TESTING",
                                  className:
                                    "border-accent/40 bg-accent/10 text-accent",
                                }
                              : catalogStatus;

                      return (
                        <div
                          key={model.arena_model_id}
                          className="flex flex-col justify-between rounded-xl border border-[#1F1F22] bg-[#050508] p-5 shadow-lg space-y-4 transition-all hover:border-accent/40"
                        >
                          <div className="space-y-2">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="mono text-[10px] font-bold uppercase tracking-wider text-accent">
                                  {model.provider_id}
                                </div>
                                <h3 className="text-sm font-bold text-white">
                                  {model.display_name}
                                </h3>
                              </div>
                              <span
                                className={`mono flex items-center gap-1.5 rounded border px-2.5 py-0.5 text-[10px] font-bold ${liveStatus.className}`}
                              >
                                <span className="h-1.5 w-1.5 rounded-full bg-current"></span>
                                {liveStatus.label}
                              </span>
                            </div>
                            <div className="mono text-[11px] text-zinc-400">
                              {model.upstream_model}
                            </div>
                          </div>

                          <div className="border-t border-[#1F1F22] pt-3 text-[11px] space-y-1.5 mono text-zinc-400">
                            <div className="flex justify-between">
                              <span>Roles:</span>
                              <span className="text-white font-medium">
                                {formatRoles(model.roles)}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span>Reasoning:</span>
                              <span className="text-white font-medium">
                                {formatReasoning(model)}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span>Context:</span>
                              <span className="text-white font-medium">
                                {formatContext(model)}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span>Tier:</span>
                              <span className="text-white font-medium uppercase">
                                {model.tier}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span>Availability:</span>
                              <span className="text-white font-medium">
                                {model.available ? "ready" : "credential missing"}
                              </span>
                            </div>
                            {health.latencyMs ? (
                              <div className="flex justify-between">
                                <span>Latency:</span>
                                <span className="text-emerald-400 font-medium">
                                  {health.latencyMs}ms
                                </span>
                              </div>
                            ) : null}
                          </div>

                          <div className="flex items-center gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() =>
                                testProviderConnection(model.arena_model_id)
                              }
                              disabled={isTesting || !model.available}
                              className="mono flex-1 h-8 items-center justify-center gap-2 rounded-lg border border-[#2A2A2E] bg-[#0D0D0F] text-[11px] font-bold text-zinc-300 transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                            >
                              {isTesting ? (
                                <>
                                  <RefreshCw className="h-3 w-3 animate-spin" />
                                  <span>TESTING…</span>
                                </>
                              ) : (
                                <span>[ TEST CONNECTION ]</span>
                              )}
                            </button>

                            <button
                              type="button"
                              onClick={() =>
                                handleToggleHide(
                                  model.arena_model_id,
                                  model.display_name,
                                )
                              }
                              title="Remove/Hide from arena selectors"
                              className="mono h-8 px-3 rounded-lg border border-[#2A2A2E] bg-[#0D0D0F] text-[10.5px] font-bold text-zinc-400 hover:border-zinc-600 hover:text-white transition-colors"
                            >
                              [ HIDE ]
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Personal Providers */}
              <div className="space-y-4 pt-2">
                <div className="flex items-center justify-between border-b border-[#1F1F22] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-accent">■</span>
                    <h2 className="mono text-xs font-bold uppercase tracking-widest text-white">
                      Your Providers ({visiblePersonal.length})
                    </h2>
                  </div>
                  <span className="mono text-[10px] text-zinc-500">
                    AES-256 ENCRYPTED PERSONAL CREDENTIALS
                  </span>
                </div>

                {visiblePersonal.length === 0 ? (
                  <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-8 text-center space-y-3">
                    <Key className="mx-auto h-8 w-8 text-zinc-600" />
                    <h4 className="text-sm font-bold text-white">
                      No Personal Keys Registered
                    </h4>
                    <p className="text-xs text-zinc-400 max-w-md mx-auto">
                      Add your OpenAI, Anthropic, DeepSeek, or custom API keys to battle with proprietary weights.
                    </p>
                    <button
                      type="button"
                      onClick={() => openRegisterModal()}
                      className="btn btn-primary mx-auto inline-flex h-9 items-center gap-2 px-5 text-xs font-bold mt-2"
                    >
                      <Plus className="h-4 w-4" />
                      <span>Register Provider Key</span>
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {visiblePersonal.map((p) => {
                      const health = healthMap[p.id] || { state: "UNTESTED" };
                      const maskedCred = p.masked_key
                        ? `••••••${p.masked_key.slice(-4)}`
                        : "••••••••••••";

                      return (
                        <div
                          key={p.id}
                          className="flex flex-col justify-between rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl space-y-5 transition-all hover:border-accent/40"
                        >
                          <div className="space-y-1">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="mono text-[10px] font-bold uppercase tracking-wider text-accent">
                                  {p.name}
                                </div>
                                <h3 className="text-base font-extrabold text-white mt-0.5">
                                  {p.model_name || "Custom Model"}
                                </h3>
                              </div>
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => handleToggleHide(p.id, p.name)}
                                  className="grid h-7 w-7 place-items-center rounded text-zinc-400 hover:bg-[#161619] hover:text-white"
                                  title="Hide from selectors"
                                >
                                  <EyeOff className="h-3.5 w-3.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setDeleteTarget(p)}
                                  className="grid h-7 w-7 place-items-center rounded text-zinc-400 hover:bg-red-950/40 hover:text-red-400"
                                  title="Delete Provider Key"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            </div>
                          </div>

                          <div className="border-b border-[#1F1F22]" />

                          <div className="space-y-2 mono text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-zinc-500">Credential</span>
                              <span className="text-white font-medium">
                                {maskedCred}
                              </span>
                            </div>

                            <div className="flex items-center justify-between">
                              <span className="text-zinc-500">Status</span>
                              <span>
                                {health.state === "HEALTHY" && (
                                  <span className="inline-flex items-center gap-1.5 text-emerald-400 font-bold">
                                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                                    ● HEALTHY
                                    {health.latencyMs ? ` (${health.latencyMs}ms)` : ""}
                                  </span>
                                )}
                                {health.state === "ERROR" && (
                                  <span className="inline-flex items-center gap-1.5 text-red-400 font-bold" title={health.detail}>
                                    <span className="h-1.5 w-1.5 rounded-full bg-red-400"></span>
                                    ● ERROR
                                  </span>
                                )}
                                {health.state === "TESTING" && (
                                  <span className="inline-flex items-center gap-1.5 text-accent font-bold animate-pulse">
                                    <span className="h-1.5 w-1.5 rounded-full bg-accent"></span>
                                    ● TESTING…
                                  </span>
                                )}
                                {health.state === "UNTESTED" && (
                                  <span className="inline-flex items-center gap-1.5 text-zinc-400">
                                    ○ UNTESTED
                                  </span>
                                )}
                              </span>
                            </div>

                            {health.detail && health.state === "ERROR" && (
                              <div className="rounded bg-red-950/30 border border-red-500/20 p-2 text-[10.5px] text-red-300">
                                {health.detail}
                              </div>
                            )}

                            <div className="flex items-center justify-between">
                              <span className="text-zinc-500">Last checked</span>
                              <span className="text-zinc-300">
                                {health.lastChecked || "Never"}
                              </span>
                            </div>

                            <div className="flex items-center justify-between">
                              <span className="text-zinc-500">Fighter</span>
                              <span className="text-emerald-400 font-bold">✓</span>
                            </div>

                            <div className="flex items-center justify-between">
                              <span className="text-zinc-500">Judge</span>
                              <span className="text-emerald-400 font-bold">✓</span>
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 pt-2">
                            <button
                              type="button"
                              onClick={() => testProviderConnection(p.id)}
                              disabled={health.state === "TESTING"}
                              className="mono flex-1 min-w-[130px] h-9 rounded-lg border border-accent/40 bg-accent/10 text-xs font-bold text-accent transition-all hover:bg-accent/20 disabled:opacity-50"
                            >
                              {health.state === "TESTING" ? "TESTING…" : "[ TEST CONNECTION ]"}
                            </button>
                            <button
                              type="button"
                              onClick={() => openRegisterModal(p)}
                              className="mono h-9 px-3.5 rounded-lg border border-[#2A2A2E] bg-[#0D0D0F] text-xs font-bold text-zinc-300 hover:text-white hover:border-[#3F3F46]"
                            >
                              [ EDIT ]
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeleteTarget(p)}
                              className="mono h-9 px-3.5 rounded-lg border border-red-500/40 bg-red-950/20 text-xs font-bold text-red-400 hover:bg-red-950/50 hover:border-red-500 transition-all flex items-center gap-1.5"
                              title="Delete Provider Key"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              <span>[ DELETE ]</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* =============================================================== */}
          {/* TAB 2: HIDDEN MODELS & PROVIDERS                                 */}
          {/* =============================================================== */}
          {activeTab === "hidden" && (
            <div className="relative z-10 space-y-6">
              {visiblePlatform.length === 0 && visiblePersonal.length === 0 ? (
                <div className="rounded-xl border border-[#1F1F22] bg-[#050508] p-12 text-center space-y-3">
                  <Eye className="mx-auto h-8 w-8 text-zinc-600" />
                  <h4 className="text-base font-bold text-white">
                    No Hidden Models or Keys
                  </h4>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    Any platform model or custom provider you remove/hide will appear here for easy restoration.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                  {/* Hidden Platform Models */}
                  {visiblePlatform.map((model) => (
                    <div
                      key={model.arena_model_id}
                      className="flex flex-col justify-between rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl space-y-4 opacity-80 hover:opacity-100 transition-opacity"
                    >
                      <div className="space-y-1">
                        <div className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                          HIDDEN PLATFORM MODEL · {model.provider_id}
                        </div>
                        <h3 className="text-base font-bold text-white">
                          {model.display_name}
                        </h3>
                        <div className="mono text-xs text-zinc-400">
                          {model.upstream_model}
                        </div>
                      </div>

                      <div className="pt-2 border-t border-[#1F1F22] flex items-center justify-between">
                        <span className="mono text-[10px] text-zinc-500">Excluded from arena</span>
                        <button
                          type="button"
                          onClick={() =>
                            handleToggleHide(
                              model.arena_model_id,
                              model.display_name,
                            )
                          }
                          className="mono h-8 px-4 rounded-lg border border-emerald-500/40 bg-emerald-950/30 text-xs font-bold text-emerald-400 hover:bg-emerald-950/60 transition-all flex items-center gap-1.5"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          <span>[ UNHIDE / RESTORE ]</span>
                        </button>
                      </div>
                    </div>
                  ))}

                  {/* Hidden Personal Providers */}
                  {visiblePersonal.map((p) => (
                    <div
                      key={p.id}
                      className="flex flex-col justify-between rounded-xl border border-[#1F1F22] bg-[#050508] p-6 shadow-xl space-y-4 opacity-80 hover:opacity-100 transition-opacity"
                    >
                      <div className="space-y-1">
                        <div className="mono text-[10px] font-bold uppercase tracking-wider text-accent">
                          HIDDEN CUSTOM KEY
                        </div>
                        <h3 className="text-base font-bold text-white">
                          {p.name}
                        </h3>
                        <div className="mono text-xs text-zinc-400">
                          {p.model_name || "Custom"}
                        </div>
                      </div>

                      <div className="pt-2 border-t border-[#1F1F22] flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(p)}
                          className="mono h-8 px-3 rounded-lg border border-red-500/40 bg-red-950/20 text-xs font-bold text-red-400 hover:bg-red-950/50"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleHide(p.id, p.name)}
                          className="mono flex-1 h-8 px-4 rounded-lg border border-emerald-500/40 bg-emerald-950/30 text-xs font-bold text-emerald-400 hover:bg-emerald-950/60 transition-all flex items-center justify-center gap-1.5"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          <span>[ UNHIDE / RESTORE ]</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* =================================================================== */}
      {/* MODAL: REGISTER / EDIT PROVIDER                                     */}
      {/* =================================================================== */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl border border-accent/40 bg-[#09090E] p-6 shadow-2xl space-y-6 md:p-8">
            <div className="flex items-center justify-between border-b border-[#1F1F22] pb-4">
              <div className="flex items-center gap-2">
                <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 border border-accent/40 text-accent">
                  <Key className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white">
                    {editingProvider ? "Edit Provider Key" : "Register Provider"}
                  </h3>
                  <p className="text-xs text-zinc-400">
                    AES-256 encrypted at rest in server vault.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="text-zinc-500 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Preset Selector */}
            {!editingProvider && (
              <div className="space-y-2">
                <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                  Select Provider Type
                </label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {(Object.keys(PRESETS) as PresetKey[]).map((key) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => selectPreset(key)}
                      className={`mono rounded-lg p-2 text-center text-xs font-bold transition-all border ${
                        activePreset === key
                          ? "border-accent bg-accent/15 text-accent shadow-[0_0_10px_rgba(255,0,160,0.25)]"
                          : "border-[#1F1F22] bg-[#050508] text-zinc-400 hover:border-zinc-700"
                      }`}
                    >
                      {PRESETS[key].brand}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <form onSubmit={handleSaveProvider} className="space-y-4">
              <div>
                <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                  Provider Label
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#050508] px-3.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                  placeholder="e.g. Anthropic Claude Key"
                  required
                />
              </div>

              <div>
                <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                  Base URL
                </label>
                <input
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#050508] px-3.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                  required
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                    API Key
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowKeyText(!showKeyText)}
                    className="mono text-[10px] text-accent hover:underline"
                  >
                    {showKeyText ? "Hide Key" : "Show Key"}
                  </button>
                </div>
                <input
                  type={showKeyText ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#050508] px-3.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                  placeholder={
                    editingProvider
                      ? "Leave empty to keep existing encrypted key"
                      : "sk-ant-... or sk-..."
                  }
                  required={!editingProvider}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                    Default Model Name
                  </label>
                  <input
                    type="text"
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                    className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#050508] px-3.5 py-2 text-xs text-white focus:border-accent focus:outline-none"
                    placeholder="e.g. claude-3-7-sonnet"
                  />
                </div>
                <div>
                  <label className="mono text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                    Auth Style
                  </label>
                  <select
                    value={authStyle}
                    onChange={(e) => setAuthStyle(e.target.value)}
                    className="mono mt-1 w-full rounded-lg border border-[#1F1F22] bg-[#050508] px-3 py-2 text-xs text-white focus:border-accent focus:outline-none"
                  >
                    <option value="bearer">Bearer Token</option>
                    <option value="modal_proxy">Modal Proxy (Key:Secret)</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#1F1F22]">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="mono px-4 py-2 text-xs text-zinc-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn btn-primary px-6 py-2.5 text-xs font-bold"
                >
                  {submitting ? "Saving Vault Key…" : "Save to Vault"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* DELETE CONFIRMATION DIALOG                                          */}
      {/* =================================================================== */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-red-500/40 bg-[#09090E] p-6 shadow-2xl space-y-5">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-red-950/60 border border-red-500/40 text-red-400">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  Delete Provider Key
                </h3>
                <p className="text-xs text-zinc-400">Permanent vault removal</p>
              </div>
            </div>

            <p className="text-xs text-zinc-300 leading-relaxed">
              Are you sure you want to permanently delete{" "}
              <strong className="text-white font-mono">
                "{deleteTarget.name}"
              </strong>
              ? Its encrypted credentials will be immediately purged from the
              database.
            </p>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="mono px-4 py-2 text-xs text-zinc-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteProvider}
                disabled={deleting}
                className="mono rounded-lg border border-red-500/50 bg-red-600 px-5 py-2 text-xs font-bold text-white shadow-[0_0_12px_rgba(220,38,38,0.4)] hover:bg-red-500 disabled:opacity-50"
              >
                {deleting ? "Purging Key…" : "Delete Provider"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
