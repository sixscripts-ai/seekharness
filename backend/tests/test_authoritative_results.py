"""Tests for Canonical Authoritative Result Contract (Change Set C — Phase C1)."""

import pytest
from datetime import datetime, timezone

from agent_arena.results import (
    AuthoritativeResult,
    normalize_participant_identity,
)


def test_authoritative_result_dataclass_identity():
    """Test identity property and serialization."""
    res = AuthoritativeResult(
        battle_id="b-123",
        phase="race",
        role="player_a",
        model_id="gpt-4o",
        status="completed",
        passed=True,
        score=10.0,
        verification_status="verified_pass",
        termination_reason="TEST_PASS",
        artifact_refs=["solution.py"],
        metrics={"turns": 2, "steps": 4, "duration_ms": 1250},
        finalized_at=datetime(2026, 8, 30, 2, 0, 0, tzinfo=timezone.utc),
        result_version=1,
    )

    assert res.identity == ("b-123", "race", "player_a", "gpt-4o")
    d = res.to_dict()
    assert d["battle_id"] == "b-123"
    assert d["passed"] is True
    assert d["metrics"]["duration_ms"] == 1250
    assert "2026-08-30" in d["finalized_at"]

    # Reconstruct
    res2 = AuthoritativeResult.from_dict(d)
    assert res2.identity == res.identity
    assert res2.passed is True
    assert res2.score == 10.0
    assert res2.verification_status == "verified_pass"


def test_normalize_participant_identity():
    """Test identity normalization for solo, race, and builder/breaker."""
    # Solo / default
    assert normalize_participant_identity("b-solo", model_id="m1") == ("b-solo", "main", "fighter", "m1")

    # Race
    assert normalize_participant_identity("b-race", phase="race", role="player_a", model_id="m1") == (
        "b-race", "race", "player_a", "m1"
    )

    # Builder / Breaker
    assert normalize_participant_identity("b-bb", phase="builder", role="builder", model_id="b_mod") == (
        "b-bb", "builder", "builder", "b_mod"
    )
    assert normalize_participant_identity("b-bb", phase="breaker", role="breaker", model_id="k_mod") == (
        "b-bb", "breaker", "breaker", "k_mod"
    )


def test_authoritative_result_repository_in_memory():
    """Test repository and service layer methods."""
    from agent_arena.persistence.service import battle_result_upsert, battle_results_list

    res = battle_result_upsert(
        battle_id="b-test-repo",
        model_id="gpt-4o",
        phase="main",
        role="fighter",
        status="completed",
        passed=True,
        score=10.0,
        verification_status="verified_pass",
        termination_reason="TEST_PASS",
        artifact_refs=["solution.py"],
        metrics={"turns": 3, "steps": 5},
    )
    assert res["battle_id"] == "b-test-repo"
    assert res["passed"] is True
def test_same_model_two_roles_have_distinct_identities():
    builder = AuthoritativeResult(
        battle_id="b-same",
        phase="builder",
        role="builder",
        model_id="shared-model",
        status="completed",
        passed=True,
        score=1.0,
        verification_status="verified_pass",
        termination_reason="TEST_PASS",
    )
    breaker = AuthoritativeResult(
        battle_id="b-same",
        phase="breaker",
        role="breaker",
        model_id="shared-model",
        status="timeout",
        passed=False,
        score=0.0,
        verification_status="verified_fail",
        termination_reason="TEST_FAIL",
    )
    assert builder.identity == ("b-same", "builder", "builder", "shared-model")
    assert breaker.identity == ("b-same", "breaker", "breaker", "shared-model")
    assert builder.identity != breaker.identity
    from agent_arena.results import aggregate_scores_by_model

    aggregated = aggregate_scores_by_model(
        {
            ("builder", "builder", "shared-model"): 1.0,
            ("breaker", "breaker", "shared-model"): 0.0,
        }
    )
    assert aggregated["shared-model"] == 1.0
