"""Isolated PostgreSQL URL for opted-in tests.

Never uses production Neon / DATABASE_URL. Tests run only when:

    ARENA_INTEGRATION_TESTS=1
    ARENA_PG_TEST_URL=postgresql://...

Set ARENA_PG_ALLOW_NEON=1 only for an explicit disposable Neon branch.
"""

from __future__ import annotations

import os

import pytest

_TRUTHY = ("1", "true", "yes", "on")


def integration_enabled() -> bool:
    return os.environ.get("ARENA_INTEGRATION_TESTS", "").strip().lower() in _TRUTHY


def postgres_tests_enabled() -> bool:
    return integration_enabled() and bool(os.environ.get("ARENA_PG_TEST_URL", "").strip())


def test_database_url() -> str:
    if not integration_enabled():
        pytest.skip("External Postgres access requires ARENA_INTEGRATION_TESTS=1")
    url = os.environ.get("ARENA_PG_TEST_URL", "").strip()
    if not url:
        pytest.skip("ARENA_PG_TEST_URL is required for PostgreSQL tests")
    host = url.lower()
    if "neon.tech" in host and os.environ.get("ARENA_PG_ALLOW_NEON", "").strip() not in _TRUTHY:
        pytest.skip("Refusing neon.tech unless ARENA_PG_ALLOW_NEON=1 (disposable branch only)")
    return url


def sqlalchemy_test_url() -> str:
    url = test_database_url()
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url
