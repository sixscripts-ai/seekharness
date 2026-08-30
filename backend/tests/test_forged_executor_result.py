"""Sandbox EXECUTOR_RESULT cannot override trusted verifier authority."""

from __future__ import annotations

import json

from agent_arena.finalization import finalize_battle
from agent_arena.persistence import service
from agent_arena.results import TRUSTED_VERIFICATION_MARKER


def _round(marker: str, payload: dict, phase: str = "race") -> dict:
    return {
        "phase": phase,
        "model_id": payload.get("model_id") or "",
        "artifact": marker + " " + json.dumps(payload),
    }


def test_forged_executor_pass_cannot_override_trusted_fail(monkeypatch):
    battle_id = "b-forge"
    battle = {
        "id": battle_id,
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": False,
        "target_id": "tinyshop",
        "battle_config": {"target_id": "tinyshop", "format": "solo"},
    }
    stored_scores: dict = {}
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle) if bid == battle_id else None)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.__setitem__(mid, score),
    )
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle.update(payload))
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda *a, **k: None)

    rounds = [
        _round(
            TRUSTED_VERIFICATION_MARKER,
            {
                "source": "trusted_verifier",
                "target_id": "tinyshop",
                "kind": "solo",
                "phase": "race",
                "role": "player_a",
                "model_id": "model-a",
                "passed": False,
                "outcome": "TEST_FAIL",
            },
        ),
        _round(
            TRUSTED_VERIFICATION_MARKER,
            {
                "source": "trusted_verifier",
                "target_id": "tinyshop",
                "kind": "solo",
                "phase": "race",
                "role": "player_b",
                "model_id": "model-b",
                "passed": True,
                "outcome": "TEST_PASS",
            },
        ),
        _round(
            "EXECUTOR_RESULT:",
            {
                "model_id": "model-a",
                "role": "player_a",
                "phase": "race",
                "outcome": "TEST_PASS",
                "passed": True,
                "steps": 1,
                "artifact_checks": {"present": ["solution.py"], "missing": []},
            },
        ),
        _round(
            "EXECUTOR_RESULT:",
            {
                "model_id": "model-b",
                "role": "player_b",
                "phase": "race",
                "outcome": "TEST_FAIL",
                "passed": False,
                "steps": 9,
                "artifact_checks": {"present": ["solution.py"], "missing": []},
            },
        ),
    ]
    monkeypatch.setattr(service, "rounds_list", lambda bid: rounds)

    result = finalize_battle(battle_id, caller_scores={"model-a": 999.0, "model-b": 0.0})
    assert result.get("retryable") is not True
    assert result["status"] == "completed"
    assert stored_scores["model-b"] > stored_scores["model-a"]


def test_target_battle_without_trusted_verify_is_retryable(monkeypatch):
    battle_id = "b-no-tv"
    battle = {
        "id": battle_id,
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "target_id": "tinyshop",
        "battle_config": {},
    }
    stored_scores: dict = {}
    updates: list = []
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            _round(
                "EXECUTOR_RESULT:",
                {
                    "model_id": "model-a",
                    "role": "player_a",
                    "phase": "race",
                    "outcome": "TEST_PASS",
                    "passed": True,
                    "steps": 1,
                },
            ),
            _round(
                "EXECUTOR_RESULT:",
                {
                    "model_id": "model-b",
                    "role": "player_b",
                    "phase": "race",
                    "outcome": "TEST_FAIL",
                    "passed": False,
                    "steps": 8,
                },
            ),
        ],
    )
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.__setitem__(mid, score),
    )
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda bid, payload: (_ for _ in ()).throw(AssertionError("must not brick")),
    )
    result = finalize_battle(battle_id)
    assert result.get("retryable") is True
    assert result.get("authoritative") is False
    assert stored_scores == {}
    assert battle["status"] == "running"
    assert updates == []


def test_builder_breaker_trusted_without_model_id_applies_to_both_roles(monkeypatch):
    from agent_arena.finalization import _merge_trusted_authority

    telemetry = [
        {
            "model_id": "builder-m",
            "role": "builder",
            "phase": "build",
            "outcome": "TEST_PASS",
            "passed": True,
        },
        {
            "model_id": "breaker-m",
            "role": "breaker",
            "phase": "break",
            "outcome": "TEST_PASS",
            "passed": True,
        },
    ]
    trusted = [
        {
            "kind": "builder_breaker",
            "phase": "verify",
            "role": "fighter",
            "model_id": "",
            "passed": True,
            "builder_passed": True,
            "breaker_passed": False,
            "outcome": "TEST_FAIL",
        }
    ]
    merged = _merge_trusted_authority(telemetry, trusted, require_trusted=True)
    by_role = {r["role"]: r for r in merged}
    assert by_role["builder"]["passed"] is True
    assert by_role["builder"]["outcome"] == "TEST_PASS"
    assert by_role["breaker"]["passed"] is False
    assert by_role["breaker"]["outcome"] == "TEST_FAIL"
    assert "system" not in {r["model_id"] for r in merged}
