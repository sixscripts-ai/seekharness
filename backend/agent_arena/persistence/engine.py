"""PostgreSQL engine configuration for the Agent Arena persistence layer.

Resolves DATABASE_URL from the environment. For local development the value
comes from the workspace-level .env.local (the repo is nested one level below
the seekharness workspace directory); in production it will come from Modal
secrets. No connection string is ever printed, logged, or exposed to the
frontend.

Pooling is deliberately conservative because the backend runs on Modal:
  - pool_pre_ping=True to drop stale connections after Neon suspends
  - a small pool (the Neon pooler multiplexes connections)
  - pool_recycle to avoid connections outliving the pooler limits
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from agent_arena.hermetic import assert_not_hermetic, hermetic_mode

_REPO_ROOT = Path(__file__).resolve().parents[2]

_ENV_CANDIDATES = [
    _REPO_ROOT / ".env.local",
    _REPO_ROOT.parent / ".env.local",
]


def _load_env() -> None:
    """Load local env files without overriding values already in the process env."""
    if hermetic_mode():
        return
    for path in _ENV_CANDIDATES:
        if path.is_file():
            load_dotenv(path, override=False)


@lru_cache(maxsize=1)
def database_url(unpooled: bool = False) -> str:
    """Return the Postgres connection URL, preferring the pooled variant.

    Raises RuntimeError with a clear message when not configured. The value
    itself is never logged.
    """
    assert_not_hermetic("postgres")
    _load_env()
    key = "DATABASE_URL_UNPOOLED" if unpooled else "DATABASE_URL"
    url = os.environ.get(key) or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "PostgreSQL is not configured: set DATABASE_URL in the environment "
            "(local dev: workspace .env.local; production: Modal secrets)"
        )
    return url.strip()


def sqlalchemy_url() -> str:
    """Normalize the configured URL to the psycopg3 dialect scheme.

    Neon URLs use the plain postgresql:// scheme, which SQLAlchemy would map
    to psycopg2. The application stack is psycopg (v3).
    """
    url = database_url()
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache(maxsize=1)
def engine() -> Engine:
    """Application engine bound to the pooled Neon connection."""
    return create_engine(
        sqlalchemy_url(),
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=4,
        pool_recycle=1800,
    )


def redacted_host() -> str:
    """Return a credentials-free description of the configured host for reports."""
    from urllib.parse import urlparse

    parsed = urlparse(database_url())
    if parsed.hostname:
        db = parsed.path.lstrip("/") or "neondb"
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 5432}/{db}"
    return "(host redacted)"
