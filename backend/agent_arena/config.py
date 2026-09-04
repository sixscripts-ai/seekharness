import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .hermetic import should_load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if should_load_dotenv():
    load_dotenv(_REPO_ROOT / ".env")

_TRUTHY = ("true", "1", "yes", "on")


def _env_flag(name: str, default: str = "false") -> bool:
    raw = os.environ.get(name, default)
    if raw is None or not str(raw).strip():
        raw = default
    return str(raw).strip().lower() in _TRUTHY


def persistence_backend() -> str:
    raw = (os.environ.get("PERSISTENCE_BACKEND") or "postgres").strip().lower()
    return raw or "postgres"


@lru_cache
def settings() -> dict:
    persistence = persistence_backend()
    read_fallback = _env_flag("APPWRITE_READ_FALLBACK", "false")
    dual_write = _env_flag("APPWRITE_DUAL_WRITE", "false")

    if persistence == "postgres" and not (read_fallback or dual_write):
        # Appwrite is identity-only: JWT Account.get() needs project + endpoint.
        required = ["APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID"]
    else:
        required = [
            "APPWRITE_ENDPOINT",
            "APPWRITE_PROJECT_ID",
            "APPWRITE_API_KEY",
            "APPWRITE_DATABASE_ID",
        ]

    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    return {
        "APPWRITE_ENDPOINT": os.environ.get("APPWRITE_ENDPOINT", ""),
        "APPWRITE_PROJECT_ID": os.environ.get("APPWRITE_PROJECT_ID", ""),
        "APPWRITE_API_KEY": os.environ.get("APPWRITE_API_KEY", ""),
        "APPWRITE_DATABASE_ID": os.environ.get("APPWRITE_DATABASE_ID", ""),
        "FERNET_KEY": os.environ.get("FERNET_KEY", ""),
        # Comma-separated retired keys kept only for decrypting old ciphertexts.
        "FERNET_KEY_OLD": os.environ.get("FERNET_KEY_OLD", ""),
        "HOST_OPENROUTER_KEY": os.environ.get("HOST_OPENROUTER_KEY", ""),
        "HOST_XAI_KEY": os.environ.get("HOST_XAI_KEY", ""),
        "HOST_DEEPSEEK_KEY": os.environ.get("HOST_DEEPSEEK_KEY", ""),
        "HOST_OPENAI_KEY": os.environ.get("HOST_OPENAI_KEY", ""),
        "HOST_META_KEY": os.environ.get("HOST_META_KEY", ""),
        "HOST_MERGE_KEY": os.environ.get("HOST_MERGE_KEY", ""),
        "HOST_TOKENROUTER_KEY": os.environ.get("HOST_TOKENROUTER_KEY", ""),
        "HOST_GROQ_KEY": os.environ.get("HOST_GROQ_KEY", ""),
        "INTERNAL_API_KEY": os.environ.get("INTERNAL_API_KEY", ""),
        "JUDGE_MODAL_KEY": os.environ.get("JUDGE_MODAL_KEY", ""),
        "JUDGE_MODAL_SECRET": os.environ.get("JUDGE_MODAL_SECRET", ""),
        "JUDGE_MODAL_BASE": os.environ.get("JUDGE_MODAL_BASE", ""),
        "JUDGE_MODAL_MODEL": os.environ.get("JUDGE_MODAL_MODEL", ""),
        "HOST_OPENCODE_GO_KEY": os.environ.get("HOST_OPENCODE_GO_KEY", ""),
        # Neon is the battle system of record. Appwrite dual-write / read-fallback
        # stay off unless an operator explicitly re-enables them.
        "PERSISTENCE_BACKEND": persistence,
        "APPWRITE_READ_FALLBACK": "true" if read_fallback else "false",
        "APPWRITE_DUAL_WRITE": "true" if dual_write else "false",
    }
