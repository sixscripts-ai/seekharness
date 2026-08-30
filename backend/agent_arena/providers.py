import os
import time
from dataclasses import dataclass

import httpx
from appwrite.exception import AppwriteException
from appwrite.query import Query
from fastapi import APIRouter, Depends, HTTPException

from . import crypto, db
from .auth import get_current_user
from .config import settings
from .schemas import ProviderCreate, ProviderHealth, ProviderOut
from .ssrf import validate_base_url

router = APIRouter(prefix="/providers", tags=["providers"])

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_PROVIDER_ID = "openrouter"
OPENROUTER_CREDENTIAL_ENV = "OPENROUTER_API_KEY"
OPENROUTER_CREDENTIAL_FALLBACK_ENV = "HOST_OPENROUTER_KEY"
MODAL_KIMI_BASE = os.environ.get(
    "JUDGE_MODAL_BASE", "https://inference.us-west.modal.direct/v1"
)
MODAL_KIMI_MODEL = os.environ.get("JUDGE_MODAL_MODEL", "moonshotai/Kimi-K3")
HOST_FREE_ID = "host:openrouter-free"

REASONING_OFF = "off"
REASONING_HIGH = "high"
REASONING_MAX = "max"
REASONING_XHIGH = "xhigh"
_REASONING_ALIASES = {
    REASONING_OFF: REASONING_OFF,
    REASONING_HIGH: REASONING_HIGH,
    REASONING_MAX: REASONING_MAX,
    REASONING_XHIGH: REASONING_MAX,
}
REASONING_NONE = (REASONING_OFF,)
REASONING_OFF_HIGH = (REASONING_OFF, REASONING_HIGH)
REASONING_FULL = (REASONING_OFF, REASONING_HIGH, REASONING_MAX)

_FIGHTER_JUDGE = ("fighter", "judge")
_FIGHTER_ONLY = ("fighter",)


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    protocol: str
    base_url: str
    credential_env: str
    auth_style: str
    cred: str
    masked_key: str


@dataclass(frozen=True)
class ModelSpec:
    arena_model_id: str
    provider_id: str
    upstream_model: str
    display_name: str
    roles: tuple[str, ...]
    tier: str
    context: int | None
    context_class: str
    reasoning_support: bool
    reasoning_efforts: tuple[str, ...]
    tool_support: bool
    structured_output_support: bool
    status: str


@dataclass(frozen=True)
class ResolvedModelCall:
    arena_model_id: str
    provider_id: str
    protocol: str
    base_url: str
    auth_style: str
    api_key: str
    upstream_model: str


def _provider(
    pid: str,
    *,
    protocol: str,
    base_url: str,
    credential_env: str,
    auth_style: str,
    cred: str,
    masked_key: str,
) -> ProviderSpec:
    return ProviderSpec(
        id=pid,
        protocol=protocol,
        base_url=base_url,
        credential_env=credential_env,
        auth_style=auth_style,
        cred=cred,
        masked_key=masked_key,
    )


def _model(
    arena_model_id: str,
    provider_id: str,
    upstream_model: str,
    display_name: str,
    *,
    roles: tuple[str, ...] = _FIGHTER_JUDGE,
    tier: str = "value",
    context: int | None = 128_000,
    context_class: str = "medium",
    reasoning_support: bool = False,
    reasoning_efforts: tuple[str, ...] = REASONING_NONE,
    tool_support: bool = True,
    structured_output_support: bool = False,
    status: str = "active",
) -> ModelSpec:
    return ModelSpec(
        arena_model_id=arena_model_id,
        provider_id=provider_id,
        upstream_model=upstream_model,
        display_name=display_name,
        roles=roles,
        tier=tier,
        context=context,
        context_class=context_class,
        reasoning_support=reasoning_support,
        reasoning_efforts=reasoning_efforts,
        tool_support=tool_support,
        structured_output_support=structured_output_support,
        status=status,
    )


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    spec.id: spec
    for spec in (
        _provider(
            "modal",
            protocol="modal-proxy",
            base_url=MODAL_KIMI_BASE,
            credential_env="JUDGE_MODAL_KEY",
            auth_style="modal_proxy",
            cred="modal_judge",
            masked_key="modal-key…",
        ),
        _provider(
            OPENROUTER_PROVIDER_ID,
            protocol="openai-compatible",
            base_url=OPENROUTER_BASE,
            credential_env=OPENROUTER_CREDENTIAL_ENV,
            auth_style="bearer",
            cred="openrouter",
            masked_key="sk-or-…",
        ),
        _provider(
            "deepseek",
            protocol="openai-compatible",
            base_url="https://api.deepseek.com/v1",
            credential_env="HOST_DEEPSEEK_KEY",
            auth_style="bearer",
            cred="deepseek",
            masked_key="sk-…",
        ),
        _provider(
            "groq",
            protocol="openai-compatible",
            base_url="https://api.groq.com/openai/v1",
            credential_env="HOST_GROQ_KEY",
            auth_style="bearer",
            cred="groq",
            masked_key="gsk_…",
        ),
        _provider(
            "xai",
            protocol="openai-compatible",
            base_url="https://api.x.ai/v1",
            credential_env="HOST_XAI_KEY",
            auth_style="bearer",
            cred="xai",
            masked_key="xai-…",
        ),
        _provider(
            "openai",
            protocol="openai-compatible",
            base_url="https://api.openai.com/v1",
            credential_env="HOST_OPENAI_KEY",
            auth_style="bearer",
            cred="openai",
            masked_key="sk-…",
        ),
        _provider(
            "opencode_go",
            protocol="openai-compatible",
            base_url="https://opencode.ai/zen/go/v1",
            credential_env="HOST_OPENCODE_GO_KEY",
            auth_style="bearer",
            cred="opencode_go",
            masked_key="sk-u98...",
        ),
        _provider(
            "merge",
            protocol="openai-compatible",
            base_url="https://api-gateway.merge.dev/v1/openai",
            credential_env="HOST_MERGE_KEY",
            auth_style="bearer",
            cred="merge",
            masked_key="mg__…",
        ),
        _provider(
            "tokenrouter",
            protocol="openai-compatible",
            base_url="https://api.tokenrouter.com/v1",
            credential_env="HOST_TOKENROUTER_KEY",
            auth_style="bearer",
            cred="tokenrouter",
            masked_key="sk-…",
        ),
        _provider(
            "meta",
            protocol="openai-compatible",
            base_url="https://api.meta.ai/v1",
            credential_env="HOST_META_KEY",
            auth_style="bearer",
            cred="meta",
            masked_key="sk-…",
        ),
    )
}

MODEL_SPECS: tuple[ModelSpec, ...] = (
    _model(
        "host:modal-kimi",
        "modal",
        MODAL_KIMI_MODEL,
        "Modal (Kimi-K3)",
        tier="premium",
        reasoning_support=True,
        reasoning_efforts=REASONING_OFF_HIGH,
        structured_output_support=True,
    ),
    _model(
        HOST_FREE_ID,
        OPENROUTER_PROVIDER_ID,
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "OpenRouter Free (Nemotron Ultra)",
        tier="free",
        context=256_000,
        context_class="long",
    ),
    _model(
        "host:or-nemotron-lightning",
        OPENROUTER_PROVIDER_ID,
        "nvidia/nemotron-3.5-lightning:free",
        "OpenRouter Free (Nemotron 3.5 Lightning)",
        tier="free",
    ),
    _model(
        "host:or-laguna-s",
        OPENROUTER_PROVIDER_ID,
        "poolside/laguna-s-2.1:free",
        "OpenRouter Free (Laguna S)",
        tier="free",
    ),
    _model(
        "host:or-laguna-xs",
        OPENROUTER_PROVIDER_ID,
        "poolside/laguna-xs-2.1:free",
        "OpenRouter Free (Laguna XS)",
        tier="free",
        roles=_FIGHTER_ONLY,
        context=64_000,
        context_class="medium",
    ),
    _model(
        "host:or-minimax-m3",
        OPENROUTER_PROVIDER_ID,
        "minimax/minimax-m3:free",
        "OpenRouter Free (MiniMax M3)",
        tier="free",
        reasoning_support=True,
        reasoning_efforts=REASONING_OFF_HIGH,
    ),
    _model(
        "host:or-minimax-m27",
        OPENROUTER_PROVIDER_ID,
        "minimax/minimax-m2.7:free",
        "OpenRouter Free (MiniMax M2.7)",
        tier="free",
    ),
    _model(
        "host:or-router-free",
        OPENROUTER_PROVIDER_ID,
        "openrouter/free",
        "OpenRouter Free (Auto)",
        roles=_FIGHTER_ONLY,
        tier="free",
        context=None,
        context_class="variable",
        tool_support=False,
    ),
    _model(
        "host:or-glm52",
        OPENROUTER_PROVIDER_ID,
        "z-ai/glm-5.2",
        "OpenRouter (GLM 5.2)",
        tier="premium",
        context=200_000,
        context_class="long",
        reasoning_support=True,
        reasoning_efforts=REASONING_FULL,
        structured_output_support=True,
    ),
    _model(
        "host:or-glm52-free",
        OPENROUTER_PROVIDER_ID,
        "z-ai/glm-5.2:free",
        "OpenRouter Free (GLM 5.2)",
        tier="free",
        context=200_000,
        context_class="long",
        reasoning_support=True,
        reasoning_efforts=REASONING_FULL,
        structured_output_support=True,
    ),
    _model(
        "host:or-deepseek-v4-pro",
        OPENROUTER_PROVIDER_ID,
        "deepseek/deepseek-v4-pro",
        "OpenRouter (DeepSeek V4 Pro)",
        tier="premium",
        reasoning_support=True,
        reasoning_efforts=REASONING_FULL,
        structured_output_support=True,
    ),
    _model(
        "host:or-deepseek-v4-pro-0813",
        OPENROUTER_PROVIDER_ID,
        "deepseek/deepseek-v4-pro-0813",
        "OpenRouter (DeepSeek V4 Pro 0813)",
        tier="premium",
        reasoning_support=True,
        reasoning_efforts=REASONING_FULL,
        structured_output_support=True,
    ),
    _model(
        "host:or-gemini-37-flash",
        OPENROUTER_PROVIDER_ID,
        "google/gemini-3.7-flash",
        "OpenRouter (Gemini 3.7 Flash)",
        tier="value",
        context=1_000_000,
        context_class="long",
        reasoning_support=True,
        reasoning_efforts=REASONING_OFF_HIGH,
        structured_output_support=True,
    ),
    _model(
        "host:or-qwen3-coder",
        OPENROUTER_PROVIDER_ID,
        "qwen/qwen3-coder",
        "OpenRouter (Qwen3 Coder)",
        tier="value",
        context=256_000,
        context_class="long",
        reasoning_support=True,
        reasoning_efforts=REASONING_OFF_HIGH,
        structured_output_support=True,
    ),
    _model(
        "host:or-qwen3-coder-flash",
        OPENROUTER_PROVIDER_ID,
        "qwen/qwen3-coder-flash",
        "OpenRouter (Qwen3 Coder Flash)",
        roles=_FIGHTER_ONLY,
        tier="value",
        reasoning_support=False,
        reasoning_efforts=REASONING_NONE,
    ),
    _model(
        "host:or-gpt5-nano",
        OPENROUTER_PROVIDER_ID,
        "openai/gpt-5-nano",
        "OpenRouter (GPT-5 Nano)",
        tier="value",
        reasoning_support=True,
        reasoning_efforts=REASONING_FULL,
        structured_output_support=True,
    ),
    _model(
        "host:or-nex-n2-mini",
        OPENROUTER_PROVIDER_ID,
        "nex-agi/nex-n2-mini",
        "OpenRouter (Nex N2 Mini)",
        roles=_FIGHTER_ONLY,
        tier="value",
        context=64_000,
        context_class="medium",
    ),
    _model(
        "host:or-hy4",
        OPENROUTER_PROVIDER_ID,
        "tencent/hy4-preview",
        "OpenRouter (Hunyuan 4 Preview)",
        tier="premium",
        context=256_000,
        context_class="long",
        reasoning_support=True,
        reasoning_efforts=REASONING_OFF_HIGH,
        status="preview",
    ),
    _model(
        "host:deepseek-chat",
        "deepseek",
        "deepseek-v4-flash",
        "DeepSeek (Chat)",
        tier="value",
        context=64_000,
        context_class="medium",
        structured_output_support=True,
    ),
    _model(
        "host:groq-qwen",
        "groq",
        "qwen/qwen3.6-27b",
        "Groq (Qwen 3.6 27B)",
        tier="value",
    ),
    _model(
        "host:groq-compound",
        "groq",
        "groq/compound",
        "Groq (Compound)",
        tier="value",
        tool_support=True,
    ),
    _model(
        "host:opencode-go",
        "opencode_go",
        "deepseek-v4-flash",
        "OpenCode Go (DeepSeek V4 Flash)",
        status="retired",
    ),
    _model(
        "host:or-nemotron-super",
        OPENROUTER_PROVIDER_ID,
        "nvidia/nemotron-3-super-120b-a12b:free",
        "OpenRouter Free (Nemotron Super)",
        tier="free",
        status="retired",
    ),
    _model(
        "host:or-gemma-31b",
        OPENROUTER_PROVIDER_ID,
        "google/gemma-4-31b-it:free",
        "OpenRouter Free (Gemma 4 31B)",
        tier="free",
        status="retired",
    ),
    _model(
        "host:groq-llama",
        "groq",
        "llama-3.3-70b-versatile",
        "Groq (Llama 3.3 70B)",
        status="retired",
    ),
    _model(
        "host:merge-gateway",
        "merge",
        "openai/gpt-4o-mini",
        "Merge Gateway",
        status="retired",
    ),
    _model(
        "host:tokenrouter",
        "tokenrouter",
        "moonshotai/kimi-k3",
        "TokenRouter",
        status="retired",
    ),
    _model(
        "host:xai-grok",
        "xai",
        "grok-4-1-fast-non-reasoning",
        "xAI (Grok)",
        tier="premium",
        reasoning_support=False,
        reasoning_efforts=REASONING_NONE,
    ),
    _model(
        "host:openai-gpt4o-mini",
        "openai",
        "gpt-4o-mini",
        "OpenAI (GPT-4o mini)",
        tier="value",
        structured_output_support=True,
    ),
    _model(
        "host:meta-muse",
        "meta",
        "muse-spark-1.1",
        "Meta (Muse Spark)",
        status="retired",
    ),
)

_dupes = [m.arena_model_id for m in MODEL_SPECS]
if len(_dupes) != len(set(_dupes)):
    raise RuntimeError("duplicate Arena model IDs in MODEL_SPECS")

MODEL_BY_ID: dict[str, ModelSpec] = {m.arena_model_id: m for m in MODEL_SPECS}
_PUBLIC_KEYS = (
    "id",
    "name",
    "base_url",
    "masked_key",
    "auth_style",
    "model_name",
    "provider_id",
    "roles",
    "tier",
    "context",
    "context_class",
    "reasoning_support",
    "reasoning_efforts",
    "tool_support",
    "structured_output_support",
    "status",
)


def _host_row(spec: ModelSpec) -> dict:
    provider = PROVIDER_SPECS[spec.provider_id]
    retired = spec.status == "retired"
    return {
        "id": spec.arena_model_id,
        "name": spec.display_name,
        "base_url": provider.base_url,
        "masked_key": provider.masked_key,
        "auth_style": provider.auth_style,
        "model_name": spec.upstream_model,
        "cred": "" if retired else provider.cred,
        "provider_id": spec.provider_id,
        "roles": list(spec.roles),
        "tier": spec.tier,
        "context": spec.context,
        "context_class": spec.context_class,
        "reasoning_support": spec.reasoning_support,
        "reasoning_efforts": list(spec.reasoning_efforts),
        "tool_support": spec.tool_support,
        "structured_output_support": spec.structured_output_support,
        "status": spec.status,
    }


HOST_PROVIDERS: list[dict] = [_host_row(spec) for spec in MODEL_SPECS]
HOST_FREE = next(p for p in HOST_PROVIDERS if p["id"] == HOST_FREE_ID)
HOST_BY_ID = {p["id"]: p for p in HOST_PROVIDERS}


def is_host_model(model_id: str) -> bool:
    return model_id in HOST_BY_ID


def get_model_spec(arena_model_id: str) -> ModelSpec:
    spec = MODEL_BY_ID.get(arena_model_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown model_id")
    return spec


def get_provider_spec(provider_id: str) -> ProviderSpec:
    spec = PROVIDER_SPECS.get(provider_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown provider_id")
    return spec


def normalize_reasoning_effort(effort: str | None) -> str | None:
    if effort is None:
        return None
    key = str(effort).strip().lower()
    if not key:
        return None
    canonical = _REASONING_ALIASES.get(key)
    if canonical is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reasoning effort: {effort}",
        )
    return canonical


def validate_reasoning_effort(arena_model_id: str, effort: str | None) -> str | None:
    spec = get_model_spec(arena_model_id)
    normalized = normalize_reasoning_effort(effort)
    if normalized is None:
        return None
    if normalized not in spec.reasoning_efforts:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Model {arena_model_id} does not support reasoning effort "
                f"{normalized}"
            ),
        )
    return normalized


def reasoning_request_fields(arena_model_id: str, effort: str | None) -> dict:
    """Provider-layer payload fragment. Battle code must not branch on vendor."""
    spec = get_model_spec(arena_model_id)
    provider = get_provider_spec(spec.provider_id)
    normalized = validate_reasoning_effort(arena_model_id, effort)
    if normalized is None or normalized == REASONING_OFF:
        return {}
    if provider.id == OPENROUTER_PROVIDER_ID:
        or_effort = REASONING_XHIGH if normalized == REASONING_MAX else normalized
        return {"reasoning": {"effort": or_effort}}
    return {"reasoning_effort": normalized}


def _cred_material(cred: str) -> str | None:
    """Return api_key material for a host cred type, or None if unavailable."""
    s = settings()
    if cred == "openrouter":
        return (
            s.get(OPENROUTER_CREDENTIAL_FALLBACK_ENV)
            or os.environ.get(OPENROUTER_CREDENTIAL_ENV)
            or None
        )
    if cred == "opencode_go":
        return s.get("HOST_OPENCODE_GO_KEY") or None
    if cred == "modal_judge":
        key = s.get("JUDGE_MODAL_KEY") or ""
        secret = s.get("JUDGE_MODAL_SECRET") or ""
        if key and secret:
            return f"{key}:{secret}"
        return None
    if cred == "merge":
        return s.get("HOST_MERGE_KEY") or None
    if cred == "tokenrouter":
        return s.get("HOST_TOKENROUTER_KEY") or None
    if cred == "groq":
        return s.get("HOST_GROQ_KEY") or None
    if cred == "xai":
        return s.get("HOST_XAI_KEY") or None
    if cred == "deepseek":
        return s.get("HOST_DEEPSEEK_KEY") or None
    if cred == "openai":
        return s.get("HOST_OPENAI_KEY") or None
    if cred == "meta":
        return s.get("HOST_META_KEY") or None
    return None


def _host_configured(p: dict) -> bool:
    return bool(_cred_material(p.get("cred", "")))


def _model_available(spec: ModelSpec) -> bool:
    if spec.status == "retired":
        return False
    return bool(_cred_material(PROVIDER_SPECS[spec.provider_id].cred))


def _provider_status(spec: ProviderSpec) -> str:
    return "configured" if _cred_material(spec.cred) else "unconfigured"


def configured_host_providers() -> list[dict]:
    return [
        {k: p[k] for k in _PUBLIC_KEYS} for p in HOST_PROVIDERS if _host_configured(p)
    ]


def public_provider_catalog() -> list[dict]:
    return [
        {
            "id": spec.id,
            "protocol": spec.protocol,
            "base_url": spec.base_url,
            "credential_env": spec.credential_env,
            "auth_style": spec.auth_style,
            "status": _provider_status(spec),
        }
        for spec in PROVIDER_SPECS.values()
    ]


def public_model_catalog() -> list[dict]:
    return [
        {
            "arena_model_id": spec.arena_model_id,
            "provider_id": spec.provider_id,
            "upstream_model": spec.upstream_model,
            "display_name": spec.display_name,
            "roles": list(spec.roles),
            "tier": spec.tier,
            "context": spec.context,
            "context_class": spec.context_class,
            "reasoning_support": spec.reasoning_support,
            "reasoning_efforts": list(spec.reasoning_efforts),
            "tool_support": spec.tool_support,
            "structured_output_support": spec.structured_output_support,
            "status": spec.status,
            "available": _model_available(spec),
        }
        for spec in MODEL_SPECS
    ]


def public_catalog() -> dict:
    return {"providers": public_provider_catalog(), "models": public_model_catalog()}


def _fernet_keys() -> list[bytes]:
    """Return all valid encryption keys, newest first.

    ``FERNET_KEY`` is the active key; ``FERNET_KEY_OLD`` (comma-separated)
    holds retired keys still needed to decrypt previously-stored ciphertexts.
    This lets an operator rotate the key without bricking existing providers:
    decryption tries each key, while new writes use the active key only.
    """
    s = settings()
    active = s["FERNET_KEY"]
    if not active:
        raise HTTPException(
            status_code=500, detail="Server encryption key not configured"
        )
    keys = [active]
    for old in (s.get("FERNET_KEY_OLD") or "").split(","):
        old = old.strip()
        if old and old not in keys:
            keys.append(old)
    return [k.encode() for k in keys]


def _fernet_key() -> bytes:
    return _fernet_keys()[0]


def _decrypt_with_any(token: str) -> str:
    """Decrypt a stored ciphertext, trying every configured key in order."""
    last_err: Exception | None = None
    for key in _fernet_keys():
        try:
            return crypto.decrypt_key(token, key)
        except ValueError as exc:
            last_err = exc
    raise HTTPException(
        status_code=500, detail="Unable to decrypt provider key (key rotated?)"
    ) from last_err


def _find_existing(databases, database_id, user_id, name):
    res = databases.list_documents(
        database_id,
        "providers",
        queries=[
            Query.equal("user_id", user_id),
            Query.equal("name", name),
            Query.limit(1),
        ],
    )
    docs = res.documents
    return docs[0] if docs else None


@router.post("", response_model=ProviderOut)
def create_provider(body: ProviderCreate, user_id: str = Depends(get_current_user)):
    base_url = validate_base_url(body.base_url)
    encrypted = crypto.encrypt_key(body.api_key, _fernet_key())
    masked = crypto.mask_key(body.api_key)
    from .persistence import service

    try:
        record = service.provider_upsert(
            user_id, body.name, base_url, encrypted, masked, body.auth_style, body.model_name
        )
    except AppwriteException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProviderOut(
        id=record["id"],
        name=body.name,
        base_url=body.base_url,
        masked_key=masked,
        auth_style=body.auth_style,
        model_name=body.model_name,
    )


@router.get("/catalog")
def list_model_catalog(_user_id: str = Depends(get_current_user)):
    """Authoritative provider + model fleet. Credentials stay backend-only."""
    return public_catalog()


@router.get("")
def list_providers(user_id: str = Depends(get_current_user)):
    from .persistence import service

    records = service.providers_list(user_id)
    items = [
        ProviderOut(
            id=r["id"],
            name=r["name"],
            base_url=r["base_url"],
            masked_key=r["masked_key"],
            auth_style=r["auth_style"],
            model_name=r.get("model_name", ""),
        ).model_dump()
        for r in records
    ]
    return configured_host_providers() + items


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, user_id: str = Depends(get_current_user)):
    """Delete a user-registered custom provider and its encrypted credentials."""
    if is_host_model(provider_id):
        raise HTTPException(
            status_code=400,
            detail="System host providers cannot be deleted from the server. You can hide them from the interface instead.",
        )
    from .persistence import service

    try:
        deleted, name = service.provider_delete(user_id, provider_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Provider not found") from exc
    except AppwriteException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You do not have permission to delete this provider",
        )
    return {"ok": True, "id": provider_id, "name": name}


def resolve_model_call(model_id: str, user_id: str) -> ResolvedModelCall:
    """Arena model ID → ModelSpec → ProviderSpec → resolved API call."""
    spec = MODEL_BY_ID.get(model_id)
    if spec is not None:
        provider = PROVIDER_SPECS[spec.provider_id]
        key = _cred_material("" if spec.status == "retired" else provider.cred)
        if not key:
            raise HTTPException(
                status_code=500,
                detail=f"Host credentials not configured for {model_id}",
            )
        return ResolvedModelCall(
            arena_model_id=spec.arena_model_id,
            provider_id=provider.id,
            protocol=provider.protocol,
            base_url=provider.base_url,
            auth_style=provider.auth_style,
            api_key=key,
            upstream_model=spec.upstream_model,
        )
    from .persistence import service

    doc = service.provider_get(user_id, model_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Unknown model_id")
    if doc.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your provider")
    api_key = _decrypt_with_any(doc["encrypted_key"])
    return ResolvedModelCall(
        arena_model_id=model_id,
        provider_id="user",
        protocol="openai-compatible",
        base_url=doc["base_url"],
        auth_style=doc["auth_style"],
        api_key=api_key,
        upstream_model=doc.get("model_name") or "",
    )


def get_model_call_spec(model_id: str, user_id: str) -> tuple[str, str, str, str]:
    """Return (base_url, auth_style, api_key, model_name) for a battle model_id."""
    resolved = resolve_model_call(model_id, user_id)
    return (
        resolved.base_url,
        resolved.auth_style,
        resolved.api_key,
        resolved.upstream_model,
    )


@router.post("/{provider_id}/health")
def provider_id_health(provider_id: str, user_id: str = Depends(get_current_user)):
    """Test health of a stored provider (either host model or user's registered provider) by retrieving the actual stored secret."""
    try:
        base_url, auth_style, api_key, model_name = get_model_call_spec(
            provider_id, user_id
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Cannot load provider credentials: {exc}"
        ) from exc

    base_url = validate_base_url(base_url)
    headers = {}
    if auth_style == "modal_proxy":
        parts = [p.strip() for p in api_key.split(":")]
        if len(parts) != 2:
            raise HTTPException(
                status_code=400, detail="modal_proxy key must be 'wk-...:ws-...'"
            )
        headers = {"Modal-Key": parts[0], "Modal-Secret": parts[1]}
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model_name or "moonshotai/Kimi-K3",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    t0 = time.perf_counter()
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "status_code": 502,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "detail": f"Connection failed: {exc}",
        }

    if resp.status_code == 200:
        return {
            "ok": True,
            "status": "HEALTHY",
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "detail": None,
        }
    else:
        err_detail = resp.text[:200]
        return {
            "ok": False,
            "status": "ERROR",
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "detail": f"Provider returned HTTP {resp.status_code}: {err_detail}",
        }


@router.post("/health")
def provider_health(body: ProviderHealth, _user_id: str = Depends(get_current_user)):
    base_url = validate_base_url(body.base_url)
    headers = {}
    if body.auth_style == "modal_proxy":
        parts = [p.strip() for p in body.api_key.split(":")]
        if len(parts) != 2:
            raise HTTPException(
                status_code=400, detail="modal_proxy key must be 'wk-...:ws-...'"
            )
        headers = {"Modal-Key": parts[0], "Modal-Secret": parts[1]}
    else:
        headers["Authorization"] = f"Bearer {body.api_key}"
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": body.model or "moonshotai/Kimi-K3",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Provider returned {resp.status_code}: {resp.text[:200]}",
        )
    return {"ok": True, "status_code": resp.status_code}
