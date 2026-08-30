"""Finalization authority: sandbox scores never become authoritative; terminal states stick."""

from __future__ import annotations

from agent_arena.finalization import (
    INCOMPLETE_EVIDENCE,
    derive_trusted_scores,
    finalize_battle,
    is_terminal_battle_status,
)


def test_caller_scores_are_never_authoritative():
    scores, source, error, summary, decision = derive_trusted_scores(
        battle_id="b-hint",
        results=[],
        fmt_cfg={},
        battle_model_ids=["model-a", "model-b"],
        untrusted_hint_scores={"model-a": 999.0, "model-b": 0.0},
    )
    assert scores is None
    assert error == INCOMPLETE_EVIDENCE
    assert 999.0 not in (scores or {}).values()


def test_trusted_results_produce_deterministic_scores_not_caller():
    results = [
        {
            "model_id": "model-a",
            "role": "player_a",
            "phase": "race",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 3,
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
        {
            "model_id": "model-b",
            "role": "player_b",
            "phase": "race",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 8,
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
    ]
    scores, source, error, summary, decision = derive_trusted_scores(
        battle_id="b-ev",
        results=results,
        fmt_cfg={},
        battle_model_ids=["model-a", "model-b"],
        untrusted_hint_scores={"model-a": 999.0, "model-b": 0.0},
    )
    assert error is None
    assert source == "arena-score-v1"
    assert scores is not None
    assert scores["model-a"] != 999.0
    assert scores["model-a"] > scores["model-b"]


def test_no_trusted_evidence_caller_999_is_not_persisted(monkeypatch):
    battle = {
        "id": "b-999",
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "battle_config": {},
    }
    stored_scores: dict = {}
    updates: list[dict] = []

    from agent_arena.persistence import service

    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle) if bid == "b-999" else None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: False)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "rounds_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.setdefault(bid, {}).__setitem__(mid, score),
    )
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda *a, **k: (_ for _ in ()).throw(AssertionError("elo must not run")))
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda bid, payload: (updates.append(payload), battle.update(payload)),
    )

    result = finalize_battle(
        "b-999",
        caller_status="completed",
        caller_scores={"model-a": 999.0, "model-b": 0.0},
    )
    assert result["ok"] is False
    assert result.get("retryable") is True
    assert result.get("authoritative") is False
    assert result.get("error") == INCOMPLETE_EVIDENCE
    assert result.get("scores") == {}
    assert stored_scores == {}
    assert updates == []


def test_cancelled_battle_stays_cancelled(monkeypatch):
    battle = {
        "id": "b-can",
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "cancelled",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "battle_config": {},
    }
    from agent_arena.persistence import service

    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cancelled must not be rewritten")),
    )
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cancelled must not receive scores")),
    )

    result = finalize_battle(
        "b-can",
        caller_status="completed",
        caller_scores={"model-a": 999.0, "model-b": 0.0},
        override_results=[
            {
                "model_id": "model-a",
                "role": "player_a",
                "phase": "race",
                "outcome": "TEST_PASS",
                "passed": True,
                "steps": 1,
            }
        ],
    )
    assert result["already_finalized"] is True
    assert result["status"] == "cancelled"
    assert is_terminal_battle_status("cancelled")
    assert is_terminal_battle_status("failed")
    assert is_terminal_battle_status("completed")
