"""Prove default pytest cannot reach Appwrite, Postgres, Modal, or model APIs."""

from __future__ import annotations

import os

import pytest

from agent_arena.hermetic import hermetic_mode, integration_tests_enabled


def test_default_pytest_is_hermetic():
    if integration_tests_enabled():
        pytest.skip("running under ARENA_INTEGRATION_TESTS=1")
    assert hermetic_mode() is True
    assert os.environ.get("ARENA_HERMETIC") == "1"
    assert os.environ.get("APPWRITE_API_KEY") == "hermetic-blocked"
    assert "DATABASE_URL" not in os.environ
    assert "DATABASE_URL_UNPOOLED" not in os.environ
    assert os.environ.get("HOST_OPENROUTER_KEY") in (None, "")
    assert os.environ.get("HOST_GROQ_KEY") in (None, "")


def test_appwrite_client_blocked_in_hermetic():
    if integration_tests_enabled():
        pytest.skip("running under ARENA_INTEGRATION_TESTS=1")
    from agent_arena import db

    with pytest.raises(RuntimeError, match="External Appwrite access blocked in hermetic test mode"):
        db.get_client()
    with pytest.raises(RuntimeError, match="External Appwrite access blocked in hermetic test mode"):
        db.get_databases()


def test_postgres_url_blocked_in_hermetic(monkeypatch):
    if integration_tests_enabled():
        pytest.skip("running under ARENA_INTEGRATION_TESTS=1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.neon.tech/neondb")
    from agent_arena.persistence.engine import database_url

    database_url.cache_clear()
    with pytest.raises(RuntimeError, match="External Postgres access requires ARENA_INTEGRATION_TESTS=1"):
        database_url()
    database_url.cache_clear()


def test_model_api_blocked_in_hermetic():
    if integration_tests_enabled():
        pytest.skip("running under ARENA_INTEGRATION_TESTS=1")
    from agent_arena import llm_client

    with pytest.raises(RuntimeError, match="External model API access blocked in hermetic test mode"):
        llm_client.chat_completion(
            base_url="https://openrouter.ai/api/v1",
            auth_style="bearer",
            api_key="sk-test",
            model="x",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_modal_spawn_blocked_in_hermetic():
    if integration_tests_enabled():
        pytest.skip("running under ARENA_INTEGRATION_TESTS=1")
    from agent_arena import sandbox_launcher

    with pytest.raises(RuntimeError, match="External Modal access blocked in hermetic test mode"):
        sandbox_launcher.try_spawn_modal_sandbox("battle-hermetic")
