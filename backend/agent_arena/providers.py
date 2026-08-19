import os

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
MODAL_KIMI_BASE = os.environ.get(
    "JUDGE_MODAL_BASE", "https://inference.us-west.modal.direct/v1"
)
MODAL_KIMI_MODEL = os.environ.get("JUDGE_MODAL_MODEL", "moonshotai/Kimi-K3")
HOST_FREE_ID = "host:openrouter-free"

# Multi-backend host catalog. Each entry declares how to resolve credentials.
# Public list only includes entries whose credentials are present.
HOST_PROVIDERS: list[dict] = [
    # --- Modal (Kimi) ---
    {
        "id": "host:modal-kimi",
        "name": "Modal (Kimi-K3)",
        "base_url": MODAL_KIMI_BASE,
        "masked_key": "modal-key…",
        "auth_style": "modal_proxy",
        "model_name": MODAL_KIMI_MODEL,
        "cred": "modal_judge",
    },
    # --- OpenCode Go (DeepSeek V4 Flash) ---
    {
        "id": "host:opencode-go",
        "name": "OpenCode Go (DeepSeek V4 Flash)",
        "base_url": "https://opencode.ai/zen/go/v1",
        "masked_key": "sk-u98...",
        "auth_style": "bearer",
        "model_name": "deepseek-v4-flash",
        "cred": "opencode_go",
    },
    # --- OpenRouter free tier (HOST_OPENROUTER_KEY) ---
    {
        "id": HOST_FREE_ID,
        "name": "OpenRouter Free (Nemotron Ultra)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-nemotron-super",
        "name": "OpenRouter Free (Nemotron Super)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "nvidia/nemotron-3-super-120b-a12b:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-nemotron-nano",
        "name": "OpenRouter Free (Nemotron Nano)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "nvidia/nemotron-3-nano-30b-a3b:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-laguna-s",
        "name": "OpenRouter Free (Laguna S)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "poolside/laguna-s-2.1:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-gemma-31b",
        "name": "OpenRouter Free (Gemma 4 31B)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "google/gemma-4-31b-it:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-gpt-oss-20b",
        "name": "OpenRouter Free (GPT-OSS 20B)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "openai/gpt-oss-20b:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-ling-flash",
        "name": "OpenRouter Free (Ling 3 Flash)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "inclusionai/ling-3.0-flash:free",
        "cred": "openrouter",
    },
    {
        "id": "host:or-router-free",
        "name": "OpenRouter Free (Auto)",
        "base_url": OPENROUTER_BASE,
        "masked_key": "sk-or-...free",
        "auth_style": "bearer",
        "model_name": "openrouter/free",
        "cred": "openrouter",
    },
    # --- Optional host backends (appear when env key is set) ---
    {
        "id": "host:merge-gateway",
        "name": "Merge Gateway",
        "base_url": "https://api-gateway.merge.dev/v1/openai",
        "masked_key": "mg__…",
        "auth_style": "bearer",
        "model_name": "openai/gpt-4o-mini",
        "cred": "merge",
    },
    {
        "id": "host:tokenrouter",
        "name": "TokenRouter",
        "base_url": "https://api.tokenrouter.com/v1",
        "masked_key": "sk-…",
        "auth_style": "bearer",
        "model_name": "moonshotai/kimi-k3",
        "cred": "tokenrouter",
    },
    {
        "id": "host:groq-llama",
        "name": "Groq (Llama 3.3 70B)",
        "base_url": "https://api.groq.com/openai/v1",
        "masked_key": "gsk_…",
        "auth_style": "bearer",
        "model_name": "llama-3.3-70b-versatile",
        "cred": "groq",
    },
    {
        "id": "host:xai-grok",
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "masked_key": "xai-…",
        "auth_style": "bearer",
        "model_name": "grok-4-1-fast-non-reasoning",
        "cred": "xai",
    },
    {
        "id": "host:deepseek-chat",
        "name": "DeepSeek (Chat)",
        "base_url": "https://api.deepseek.com/v1",
        "masked_key": "sk-…",
        "auth_style": "bearer",
        "model_name": "deepseek-v4-flash",
        "cred": "deepseek",
    },
    {
        "id": "host:openai-gpt4o-mini",
        "name": "OpenAI (GPT-4o mini)",
        "base_url": "https://api.openai.com/v1",
        "masked_key": "sk-…",
        "auth_style": "bearer",
        "model_name": "gpt-4o-mini",
        "cred": "openai",
    },
    {
        "id": "host:meta-muse",
        "name": "Meta (Muse Spark)",
        "base_url": "https://api.meta.ai/v1",
        "masked_key": "sk-…",
        "auth_style": "bearer",
        "model_name": "muse-spark-1.1",
        "cred": "meta",
    },
]

HOST_FREE = next(p for p in HOST_PROVIDERS if p["id"] == HOST_FREE_ID)
HOST_BY_ID = {p["id"]: p for p in HOST_PROVIDERS}
_PUBLIC_KEYS = ("id", "name", "base_url", "masked_key", "auth_style", "model_name")


def is_host_model(model_id: str) -> bool:
    return model_id in HOST_BY_ID


def _cred_material(cred: str) -> str | None:
    """Return api_key material for a host cred type, or None if unavailable."""
    s = settings()
    if cred == "openrouter":
        return s.get("HOST_OPENROUTER_KEY") or None
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


def configured_host_providers() -> list[dict]:
    return [
        {k: p[k] for k in _PUBLIC_KEYS} for p in HOST_PROVIDERS if _host_configured(p)
    ]


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
            return decrypt_key(token, key)
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
    databases = db.get_databases()
    database_id = db.get_database_id()
    payload = {
        "user_id": user_id,
        "name": body.name,
        "base_url": base_url,
        "encrypted_key": encrypted,
        "masked_key": masked,
        "auth_style": body.auth_style,
        "model_name": body.model_name,
    }
    try:
        existing = _find_existing(databases, database_id, user_id, body.name)
        if existing:
            doc = databases.update_document(
                database_id, "providers", existing.id, payload
            )
        else:
            doc = databases.create_document(
                database_id, "providers", "unique()", payload
            )
    except AppwriteException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProviderOut(
        id=doc.id,
        name=body.name,
        base_url=body.base_url,
        masked_key=masked,
        auth_style=body.auth_style,
        model_name=body.model_name,
    )


@router.get("")
def list_providers(user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    res = databases.list_documents(
        db.get_database_id(),
        "providers",
        queries=[Query.equal("user_id", user_id), Query.limit(100)],
    )
    items = [
        ProviderOut(
            id=d.id,
            name=d.data["name"],
            base_url=d.data["base_url"],
            masked_key=d.data["masked_key"],
            auth_style=d.data["auth_style"],
            model_name=d.data.get("model_name", ""),
        ).model_dump()
        for d in res.documents
    ]
    return configured_host_providers() + items


def get_model_call_spec(model_id: str, user_id: str) -> tuple[str, str, str, str]:
    """Return (base_url, auth_style, api_key, model_name) for a battle model_id."""
    host = HOST_BY_ID.get(model_id)
    if host is not None:
        key = _cred_material(host.get("cred", ""))
        if not key:
            raise HTTPException(
                status_code=500,
                detail=f"Host credentials not configured for {model_id}",
            )
        return (
            host["base_url"],
            host["auth_style"],
            key,
            host["model_name"],
        )
    databases = db.get_databases()
    database_id = db.get_database_id()
    try:
        doc = databases.get_document(database_id, "providers", model_id)
    except AppwriteException as exc:
        raise HTTPException(status_code=404, detail="Unknown model_id") from exc
    if doc.data.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your provider")
    api_key = _decrypt_with_any(doc.data["encrypted_key"])
    return (
        doc.data["base_url"],
        doc.data["auth_style"],
        api_key,
        doc.data.get("model_name") or "",
    )


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
