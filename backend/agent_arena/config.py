import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .hermetic import should_load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if should_load_dotenv():
    load_dotenv(_REPO_ROOT / ".env")

_REQUIRED = [
    "APPWRITE_ENDPOINT",
    "APPWRITE_PROJECT_ID",
    "APPWRITE_API_KEY",
    "APPWRITE_DATABASE_ID",
]


@lru_cache
def settings() -> dict:
    persistence = os.environ.get("PERSISTENCE_BACKEND", "appwrite").lower()
    read_fallback = os.environ.get("APPWRITE_READ_FALLBACK", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    dual_write = os.environ.get("APPWRITE_DUAL_WRITE", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    if persistence == "postgres" and not (read_fallback or dual_write):
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
        # Persistence backend selection (Phase 2 cutover). Defaults keep the
        # legacy Appwrite behavior until explicitly switched.
        "PERSISTENCE_BACKEND": os.environ.get("PERSISTENCE_BACKEND", "appwrite"),
        "APPWRITE_READ_FALLBACK": os.environ.get("APPWRITE_READ_FALLBACK", "false"),
        "APPWRITE_DUAL_WRITE": os.environ.get("APPWRITE_DUAL_WRITE", "false"),
    }
