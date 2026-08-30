"""Tests for Change Set B — Memory Mode Gating, Scoping, Safety Filtering, and Post-Authoritative Creation."""

from __future__ import annotations

import pytest

from agent_arena.memory import (
    is_memory_content_safe,
    maybe_remember,
    remember,
    retrieve,
    sanitize_memory_content,
)


class FakeMemoryDatabases:
    def __init__(self):
        self._docs = []

    def create_document(self, database_id, collection, doc_id, payload):
        doc = type("Doc", (), {"id": f"mem_{len(self._docs)+1}", "data": dict(payload)})()
        self._docs.append(doc)
        return doc

    def list_documents(self, database_id, collection, queries=None):
        return type("Res", (), {"documents": list(self._docs)})()


def test_strict_mode_memory_retrieval_returns_zero_memories():
    """Test 9: Strict mode memory retrieval ALWAYS returns empty list."""
    db = FakeMemoryDatabases()
    remember(
        db,
        "test_db",
        insight="Inspect package.json before debugging Node.js exports.",
        battle_id="b-1",
        model_id="gpt-4o",
        user_id="user_1",
    )

    # In strict mode, retrieval returns []
    strict_res = retrieve(db, "test_db", "Node.js package.json debugging", context_mode="strict", model_id="gpt-4o", user_id="user_1")
    assert strict_res == []

    # In adaptive mode, retrieval succeeds
    adaptive_res = retrieve(db, "test_db", "Node.js package.json debugging", context_mode="adaptive", model_id="gpt-4o", user_id="user_1")
    assert len(adaptive_res) == 1
    assert "package.json" in adaptive_res[0]["insight"]


def test_memory_model_scoping():
    """Test 20: Memory is strictly model-scoped in adaptive retrieval."""
    db = FakeMemoryDatabases()
    remember(
        db,
        "test_db",
        insight="Model A private strategy: cache intermediate regex lookups.",
        battle_id="b-100",
        model_id="claude-3-7-sonnet",
        user_id="user_1",
    )
    remember(
        db,
        "test_db",
        insight="Model B private strategy: tokenize ast nodes before editing.",
        battle_id="b-101",
        model_id="gpt-4o",
        user_id="user_1",
    )

    # Query as gpt-4o: must NOT receive claude-3-7-sonnet memory
    gpt_mems = retrieve(db, "test_db", "strategy regex ast", context_mode="adaptive", model_id="gpt-4o", user_id="user_1")
    assert len(gpt_mems) == 1
    assert gpt_mems[0]["model_id"] == "gpt-4o"
    assert "Model B" in gpt_mems[0]["insight"]


def test_memory_user_scoping():
    """Test 21: Memory is user-scoped."""
    db = FakeMemoryDatabases()
    remember(
        db,
        "test_db",
        insight="User A secret notes.",
        battle_id="b-1",
        model_id="gpt-4o",
        user_id="user_alpha",
    )
    remember(
        db,
        "test_db",
        insight="User B secret notes.",
        battle_id="b-2",
        model_id="gpt-4o",
        user_id="user_beta",
    )

    mems = retrieve(db, "test_db", "secret notes", context_mode="adaptive", model_id="gpt-4o", user_id="user_alpha")
    assert len(mems) == 1
    assert mems[0]["user_id"] == "user_alpha"


def test_memory_safety_blocks_hidden_tests_and_verifier_content():
    """Test 23: Memory safety blocks hidden test code and verifier content."""
    assert is_memory_content_safe("Inspect package scripts before source exports.") is True

    # Forbidden patterns
    assert is_memory_content_safe("Read test_target.py and assert output == 'FLAG'") is False
    assert is_memory_content_safe("Hidden verifier check: test_verifier runs on port 8000") is False
    assert is_memory_content_safe("Run hidden_tests to find failure") is False


def test_memory_safety_blocks_reference_solutions_and_credentials():
    """Tests 24, 25: Memory safety blocks challenge secrets, bearer tokens, API keys, and reference solutions."""
    assert is_memory_content_safe("Solution has FLAG{super_secret_flag_1234}") is False
    assert is_memory_content_safe("Use header Bearer sk-ant-api03-abcdef12345678901234567890") is False
    assert is_memory_content_safe("Backend key is APPWRITE_API_KEY=xyz") is False
    assert is_memory_content_safe("Dump REFERENCE_SOLUTION from memory") is False


def test_memory_safety_blocks_builder_breaker_cross_boundary():
    """Test 26: Builder/Breaker private information cannot cross memory boundaries."""
    assert is_memory_content_safe("breaker_private exploit payload: send null bytes") is False
    assert is_memory_content_safe("builder_private_pre_handoff source code dump") is False


def test_unsafe_memory_excluded_from_adaptive_retrieval():
    """Tests 22, 27: Unsafe memories seeded in storage are rejected during retrieval."""
    db = FakeMemoryDatabases()

    # Seed safe memory
    remember(
        db,
        "test_db",
        insight="Safe lesson: Check file permissions before running scripts.",
        battle_id="b-1",
        model_id="gpt-4o",
        user_id="user_1",
    )

    # Seed unsafe memory directly into DB storage (simulating legacy/corrupted record)
    db._docs.append(
        type(
            "Doc",
            (),
            {
                "id": "mem_unsafe",
                "data": {
                    "user_id": "user_1",
                    "model_id": "gpt-4o",
                    "insight": "Leak secret: FLAG{compromised_verifier_flag}",
                    "tokens": ["leak", "secret"],
                    "created_at": 100000.0,
                },
            },
        )()
    )

    retrieved = retrieve(db, "test_db", "lesson secret scripts", context_mode="adaptive", model_id="gpt-4o", user_id="user_1")
    retrieved_insights = [m["insight"] for m in retrieved]

    assert any("Safe lesson" in ins for ins in retrieved_insights)
    assert not any("FLAG{" in ins for ins in retrieved_insights)


def test_memory_entries_created_only_after_authoritative_outcomes():
    """Test 27: Memory creation occurs only for valid authoritative winners."""
    db = FakeMemoryDatabases()

    # Learnable Pass condition creates verified_pass memory
    doc_pass = maybe_remember(
        db,
        "test_db",
        insight="Valid winning pattern",
        battle_id="b-pass",
        model_id="gpt-4o",
        user_id="user_1",
        outcome="TEST_PASS",
    )
    assert doc_pass is not None
    assert doc_pass.get("authoritative_status") == "verified_pass"

    # Learnable Fail condition (e.g. model attempt that failed assertion) creates verified_fail memory
    doc_fail = maybe_remember(
        db,
        "test_db",
        insight="Valid fail lesson: index out of range on empty input list",
        battle_id="b-fail",
        model_id="gpt-4o",
        user_id="user_1",
        outcome="TEST_FAIL",
        policy_status="clean",
    )
    assert doc_fail is not None
    assert doc_fail.get("authoritative_status") == "verified_fail"

    # Unlearnable Infrastructure / Provider failure returns None (rejected)
    doc_infra = maybe_remember(
        db,
        "test_db",
        insight="Infrastructure failed with connection timeout",
        battle_id="b-infra",
        model_id="gpt-4o",
        user_id="user_1",
        outcome="PROVIDER_ERROR",
        policy_status="clean",
    )
    assert doc_infra is None
