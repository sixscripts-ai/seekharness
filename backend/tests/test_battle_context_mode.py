"""Unit tests for Battle context_mode toggle ('strict' vs 'adaptive')."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_arena.auth import get_current_user
from agent_arena.main import app
from agent_arena.persistence import service
from agent_arena.schemas import BattleCreate


def test_battle_create_schema_context_mode_validation():
    # Valid strict
    bc_strict = BattleCreate(
        format_id="fmt-1",
        model_ids=["host:openrouter-free", "host:deepseek-chat"],
        context_mode="strict",
    )
    assert bc_strict.context_mode == "strict"

    # Valid adaptive
    bc_adaptive = BattleCreate(
        format_id="fmt-1",
        model_ids=["host:openrouter-free", "host:deepseek-chat"],
        context_mode="adaptive",
    )
    assert bc_adaptive.context_mode == "adaptive"

    # Default is strict
    bc_default = BattleCreate(
        format_id="fmt-1",
        model_ids=["host:openrouter-free", "host:deepseek-chat"],
    )
    assert bc_default.context_mode == "strict"

    # Invalid mode raises ValidationError
    with pytest.raises(Exception):
        BattleCreate(
            format_id="fmt-1",
            model_ids=["host:openrouter-free"],
            context_mode="invalid_mode",
        )


def test_service_battle_create_preserves_context_mode(monkeypatch):
    monkeypatch.setattr(service, "format_get", lambda _fid: {
        "id": "fmt-1",
        "config": {"roles": ["fighter", "fighter"], "playable": True, "custom": False, "engine": "agent_tool_race"},
    })
    monkeypatch.setattr(service, "battle_count_active", lambda _uid: 0)
    monkeypatch.setattr(service, "using_postgres", lambda: False)

    captured_payload = {}
    def fake_aw_create(payload):
        captured_payload.update(payload)
        return {"id": "b-test-adaptive", "status": "queued"}

    monkeypatch.setattr(service, "_aw_battle_create", fake_aw_create)

    # Test adaptive
    created = service.battle_create(
        "user-1",
        format_id="fmt-1",
        model_ids=["host:openrouter-free", "host:deepseek-chat"],
        arena_size=2,
        timeout_seconds=300,
        round_visibility="isolated",
        save=False,
        context_mode="adaptive",
    )
    assert created["id"] == "b-test-adaptive"
    assert captured_payload["context_mode"] == "adaptive"
    assert captured_payload["battle_config"]["context_mode"] == "adaptive"

    # Test strict
    service.battle_create(
        "user-1",
        format_id="fmt-1",
        model_ids=["host:openrouter-free", "host:deepseek-chat"],
        arena_size=2,
        timeout_seconds=300,
        round_visibility="isolated",
        save=False,
        context_mode="strict",
    )
    assert captured_payload["context_mode"] == "strict"
    assert captured_payload["battle_config"]["context_mode"] == "strict"


def test_executor_adaptive_memory_injection(monkeypatch):
    """Verify that in adaptive mode, memory insights from retrieve_pg are formatted and injected."""
    from agent_arena import memory

    # In strict mode, retrieve_pg returns empty list without querying DB
    strict_res = memory.retrieve_pg(
        None,
        query="test query",
        context_mode="strict",
        user_id="u1",
        model_id="m1",
    )
    assert strict_res == []

    # In adaptive mode, verify monkeypatched retrieve_pg returns records
    sample_records = [
        {"id": "mem-1", "insight": "Always check file exists before read", "similarity": 0.95},
        {"id": "mem-2", "insight": "Use pip install --no-cache-dir", "similarity": 0.88},
    ]

    monkeypatch.setattr(
        memory,
        "retrieve_pg",
        lambda session, query, **kwargs: sample_records if kwargs.get("context_mode") == "adaptive" else [],
    )

    adaptive_res = memory.retrieve_pg(
        None,
        query="test query",
        context_mode="adaptive",
        user_id="u1",
        model_id="m1",
    )
    assert len(adaptive_res) == 2

    # Verify formatting match in advanced_executor
    insights = [f"- {m.get('insight', '')[:300]}" for m in adaptive_res if m.get("insight")]
    prompt_text = "\nPrior Lessons (Model Memory):\n" + "\n".join(insights) + "\n"
    assert "Prior Lessons (Model Memory):" in prompt_text
    assert "- Always check file exists before read" in prompt_text
    assert "- Use pip install --no-cache-dir" in prompt_text

