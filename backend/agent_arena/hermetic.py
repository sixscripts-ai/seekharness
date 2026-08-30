"""Fail-closed hermetic test mode.

Ordinary `pytest` must never inherit repository `.env` credentials or open
Appwrite, Postgres, Modal, or paid model APIs. The only opt-in is
`ARENA_INTEGRATION_TESTS=1` (plus a dedicated Postgres URL when PG tests run).

This module is import-safe: it must not import config, db, or persistence.
"""

from __future__ import annotations

import os

HERMETIC_FLAG = "ARENA_HERMETIC"
INTEGRATION_FLAG = "ARENA_INTEGRATION_TESTS"

HERMETIC_APPWRITE_KEY = "hermetic-blocked"
HERMETIC_INTERNAL_KEY = "hermetic-internal-key"

_TRUTHY = ("1", "true", "yes", "on")

# Process-env names that would let tests reach real infrastructure.
_EXTERNAL_ENV_KEYS = (
    "DATABASE_URL",
    "DATABASE_URL_UNPOOLED",
    "APPWRITE_ENDPOINT",
    "APPWRITE_PROJECT_ID",
    "APPWRITE_API_KEY",
    "APPWRITE_DATABASE_ID",
    "INTERNAL_API_KEY",
    "FERNET_KEY",
    "FERNET_KEY_OLD",
    "HOST_OPENROUTER_KEY",
    "HOST_XAI_KEY",
    "HOST_DEEPSEEK_KEY",
    "HOST_OPENAI_KEY",
    "HOST_META_KEY",
    "HOST_MERGE_KEY",
    "HOST_TOKENROUTER_KEY",
    "HOST_GROQ_KEY",
    "HOST_OPENCODE_GO_KEY",
    "HOST_ANTHROPIC_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "MODAL_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "JUDGE_MODAL_KEY",
    "JUDGE_MODAL_SECRET",
    "JUDGE_MODAL_BASE",
    "JUDGE_MODAL_MODEL",
    "ARENA_USE_MODAL_SANDBOX",
)


def integration_tests_enabled() -> bool:
    return os.environ.get(INTEGRATION_FLAG, "").strip().lower() in _TRUTHY


def hermetic_mode() -> bool:
    if integration_tests_enabled():
        return False
    return os.environ.get(HERMETIC_FLAG, "").strip() == "1"


def should_load_dotenv() -> bool:
    """Repository .env / .env.local may load only outside hermetic pytest."""
    return not hermetic_mode()


def apply_hermetic_environment() -> None:
    """Strip real credentials and install fake settings defaults.

    Called from tests/conftest.py at import time, before any agent_arena
    config/dotenv import.
    """
    if integration_tests_enabled():
        os.environ.pop(HERMETIC_FLAG, None)
        return

    os.environ[HERMETIC_FLAG] = "1"
    for key in list(os.environ):
        up = key.upper()
        if key in _EXTERNAL_ENV_KEYS or up.startswith("HOST_") or up.startswith("JUDGE_"):
            os.environ.pop(key, None)

    os.environ["APPWRITE_ENDPOINT"] = "http://127.0.0.1:9"
    os.environ["APPWRITE_PROJECT_ID"] = "hermetic-project"
    os.environ["APPWRITE_API_KEY"] = HERMETIC_APPWRITE_KEY
    os.environ["APPWRITE_DATABASE_ID"] = "hermetic-db"
    os.environ["PERSISTENCE_BACKEND"] = "appwrite"
    os.environ["APPWRITE_READ_FALLBACK"] = "false"
    os.environ["APPWRITE_DUAL_WRITE"] = "false"
    os.environ["ARENA_USE_MOCK"] = "1"
    os.environ["ARENA_USE_MODAL_SANDBOX"] = "0"
    os.environ["INTERNAL_API_KEY"] = HERMETIC_INTERNAL_KEY
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("DATABASE_URL_UNPOOLED", None)


def assert_not_hermetic(kind: str) -> None:
    """Fail closed when hermetic tests attempt external infrastructure."""
    if not hermetic_mode():
        return
    label = kind.strip() or "infrastructure"
    if label.lower() == "appwrite":
        raise RuntimeError("External Appwrite access blocked in hermetic test mode")
    if label.lower() in ("postgres", "postgresql", "neon"):
        raise RuntimeError("External Postgres access requires ARENA_INTEGRATION_TESTS=1")
    if label.lower() == "modal":
        raise RuntimeError("External Modal access blocked in hermetic test mode")
    raise RuntimeError(f"External {label} access blocked in hermetic test mode")
