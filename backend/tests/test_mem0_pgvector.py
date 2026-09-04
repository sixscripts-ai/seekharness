import pytest
from unittest.mock import MagicMock
from agent_arena.mem0_pgvector import (
    EMBEDDING_DIM,
    _deterministic_hash_vector,
    get_embedding,
    NeonPgVectorMem0Store,
)


def test_deterministic_hash_vector_properties():
    vec = _deterministic_hash_vector("sample engineering lesson")
    assert len(vec) == EMBEDDING_DIM
    # Verify unit vector (L2 norm close to 1.0)
    norm = sum(x * x for x in vec) ** 0.5
    assert 0.99 <= norm <= 1.01

    empty_vec = _deterministic_hash_vector("")
    assert len(empty_vec) == EMBEDDING_DIM
    assert all(x == 0.0 for x in empty_vec)


def test_mem0_strict_mode_returns_empty():
    session = MagicMock()
    store = NeonPgVectorMem0Store(session)
    res = store.search("how to fix issue", context_mode="strict")
    assert res == []
    assert not session.execute.called


def test_mem0_search_empty_query_returns_empty():
    session = MagicMock()
    store = NeonPgVectorMem0Store(session)
    res = store.search("   ", context_mode="adaptive")
    assert res == []
    assert not session.execute.called


def test_mem0_provenance_and_safety_filtering():
    session = MagicMock()
    store = NeonPgVectorMem0Store(session)

    # Mock database returning 3 candidate rows
    mock_row_safe = MagicMock()
    mock_row_safe.id = "mem_1"
    mock_row_safe.user_id = "villain"
    mock_row_safe.model_id = "model_a"
    mock_row_safe.insight = "Properly configure connection pool recycle time."
    mock_row_safe.theory = "Prevents dropped connections on restart."
    mock_row_safe.tokens = ["connection", "pool", "recycle"]
    mock_row_safe.battle_id = "battle_1"
    mock_row_safe.format = "target"
    mock_row_safe.chosen_skills = ["postgres-tuning"]
    mock_row_safe.outcome = "win"
    mock_row_safe.target_id = "target_1"
    mock_row_safe.role = "general"
    mock_row_safe.visibility_class = "model_private"
    mock_row_safe.authoritative_status = "verified_pass"
    mock_row_safe.context_mode = "adaptive"
    mock_row_safe.source_result_id = None
    mock_row_safe.created_at = None

    # Forbidden secret leak row
    mock_row_secret = MagicMock()
    mock_row_secret.id = "mem_2"
    mock_row_secret.user_id = "villain"
    mock_row_secret.model_id = "model_a"
    mock_row_secret.insight = "Leaked secret: FLAG{super_secret_token_123}"
    mock_row_secret.theory = "test"
    mock_row_secret.tokens = ["flag"]
    mock_row_secret.battle_id = "battle_2"
    mock_row_secret.format = "target"
    mock_row_secret.chosen_skills = []
    mock_row_secret.outcome = "win"
    mock_row_secret.target_id = "target_1"
    mock_row_secret.role = "general"
    mock_row_secret.visibility_class = "model_private"
    mock_row_secret.authoritative_status = "verified_pass"
    mock_row_secret.context_mode = "adaptive"
    mock_row_secret.source_result_id = None
    mock_row_secret.created_at = None

    # Different user row
    mock_row_wrong_user = MagicMock()
    mock_row_wrong_user.id = "mem_3"
    mock_row_wrong_user.user_id = "other_user"
    mock_row_wrong_user.model_id = "model_a"
    mock_row_wrong_user.insight = "Valid insight from another user"
    mock_row_wrong_user.theory = "test"
    mock_row_wrong_user.tokens = ["valid"]
    mock_row_wrong_user.battle_id = "battle_3"
    mock_row_wrong_user.format = "target"
    mock_row_wrong_user.chosen_skills = []
    mock_row_wrong_user.outcome = "win"
    mock_row_wrong_user.target_id = "target_1"
    mock_row_wrong_user.role = "general"
    mock_row_wrong_user.visibility_class = "model_private"
    mock_row_wrong_user.authoritative_status = "verified_pass"
    mock_row_wrong_user.context_mode = "adaptive"
    mock_row_wrong_user.source_result_id = None
    mock_row_wrong_user.created_at = None

    # session.execute returns list of (row, distance) tuples
    session.execute.return_value.all.return_value = [
        (mock_row_safe, 0.15),
        (mock_row_secret, 0.05),
        (mock_row_wrong_user, 0.10),
    ]

    results = store.search(
        "connection pool recycle",
        user_id="villain",
        model_id="model_a",
        context_mode="adaptive",
        skills=["postgres-tuning"],
    )

    # Only mock_row_safe should pass all provenance and safety gates
    assert len(results) == 1
    assert results[0]["id"] == "mem_1"
    assert "FLAG" not in results[0]["insight"]
    assert results[0]["user_id"] == "villain"
    assert results[0]["score"] > 0
