"""Finalization authority: sandbox scores never become authoritative; terminal states stick."""

from __future__ import annotations

from agent_arena.finalization import (
    INCOMPLETE_EVIDENCE,
    INFRA_SCORE_JUSTIFICATION,
    canonical_infra_termination_reason,
    derive_trusted_scores,
    fail_closed_incomplete,
    finalize_battle,
    is_terminal_battle_status,
    sandbox_end_finalize,
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


def test_untrusted_only_results_are_incomplete_not_diagnostic():
    results = [
        {
            "model_id": "model-a",
            "role": "fighter",
            "phase": "main",
            "outcome": "UNTRUSTED_EXECUTION",
            "passed": False,
            "_trusted": False,
        },
        {
            "model_id": "model-b",
            "role": "fighter",
            "phase": "main",
            "outcome": "UNTRUSTED_EXECUTION",
            "passed": False,
            "_trusted": False,
        },
    ]
    scores, source, error, summary, decision = derive_trusted_scores(
        battle_id="b-untrusted",
        results=results,
        fmt_cfg={},
        battle_model_ids=["model-a", "model-b"],
        untrusted_hint_scores={"model-a": 999.0, "model-b": 0.0},
    )
    del summary, decision
    assert scores is None
    assert source == ""
    assert error == INCOMPLETE_EVIDENCE


def test_finalize_battle_untrusted_executor_stays_retryable(monkeypatch):
    import json

    from agent_arena.persistence import service
    from agent_arena.results import EXECUTOR_RESULT_MARKER

    battle = {
        "id": "b-untr",
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
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle) if bid == "b-untr" else None)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            {
                "phase": "main",
                "model_id": mid,
                "artifact": EXECUTOR_RESULT_MARKER
                + " "
                + json.dumps(
                    {
                        "model_id": mid,
                        "role": "fighter",
                        "phase": "main",
                        "outcome": "TEST_PASS",
                        "passed": True,
                    }
                ),
            }
            for mid in ("model-a", "model-b")
        ],
    )
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.setdefault(bid, {}).__setitem__(mid, score),
    )
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("elo must not run")),
    )
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda bid, payload: (updates.append(payload), battle.update(payload)),
    )
    result = finalize_battle(
        "b-untr",
        caller_status="completed",
        caller_scores={"model-a": 999.0, "model-b": 0.0},
    )
    assert result["ok"] is False
    assert result.get("retryable") is True
    assert result.get("error") == INCOMPLETE_EVIDENCE
    assert stored_scores == {}
    assert updates == []


def test_sandbox_end_finalize_untrusted_fail_closes(monkeypatch):
    import json

    from agent_arena.persistence import service
    from agent_arena.results import EXECUTOR_RESULT_MARKER

    battle = {
        "id": "b-end-untr",
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "battle_config": {},
    }
    updates: list[dict] = []
    elo_calls: list = []
    upserts: list[dict] = []
    scores: list[dict] = []
    events: list = []
    _wire_fail_closed(
        monkeypatch,
        battle,
        updates=updates,
        elo_calls=elo_calls,
        upserts=upserts,
        scores=scores,
        events=events,
    )
    monkeypatch.setattr(service, "events_load", lambda bid: [])
    monkeypatch.setattr(
        service,
        "rounds_list",
        lambda bid: [
            {
                "phase": "main",
                "model_id": mid,
                "artifact": EXECUTOR_RESULT_MARKER
                + " "
                + json.dumps(
                    {
                        "model_id": mid,
                        "role": "fighter",
                        "phase": "main",
                        "outcome": "TEST_PASS",
                        "passed": True,
                    }
                ),
            }
            for mid in ("model-a", "model-b")
        ],
    )
    result = sandbox_end_finalize(
        "b-end-untr",
        caller_status="completed",
        caller_scores={"model-a": 999.0, "model-b": 0.0},
    )
    assert result["status"] == "failed"
    assert result.get("retryable") is False
    assert battle["status"] == "failed"
    assert battle.get("finalized_at") is not None
    assert elo_calls == []
    assert 999.0 not in (result.get("scores") or {}).values()


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


def test_derive_trusted_scores_fullstack_clean_defense():
    """Finalization call site must pass evidence so fullstack scoring runs."""
    results = [
        {
            "model_id": "model_builder",
            "role": "builder",
            "phase": "build",
            "outcome": "TEST_PASS",
            "passed": True,
            "deployment_status": "DEPLOY_SUCCESS",
            "deployment_ready": True,
            "tests": {"passed": 5, "total": 5},
            "_trusted": True,
        },
        {
            "model_id": "model_breaker",
            "role": "breaker",
            "phase": "break",
            "outcome": "COMPLETED",
            "passed": False,
            "exploit_evidence": {
                "server_crashed": False,
                "availability_degraded": False,
                "unauthorized_mutation": False,
                "flag_captured": False,
            },
            "_trusted": True,
        },
    ]
    scores, source, error, summary, decision = derive_trusted_scores(
        battle_id="b-fullstack",
        results=results,
        fmt_cfg={},
        battle_model_ids=["model_builder", "model_breaker"],
        format_id="fullstack",
        untrusted_hint_scores={"model_builder": 0.0, "model_breaker": 99.0},
    )
    assert error is None
    assert source == "arena-score-v1"
    assert scores is not None
    assert scores["model_builder"] == 100.0
    assert scores["model_breaker"] == 0.0
    assert 99.0 not in scores.values()


def test_canonical_infra_termination_reason():
    from agent_arena.first_token import FAILURE_REASON

    assert canonical_infra_termination_reason("INCOMPLETE_EVIDENCE") == INCOMPLETE_EVIDENCE
    assert canonical_infra_termination_reason("SANDBOX_BOOT_FAILURE") == "SANDBOX_BOOT_FAILURE"
    assert canonical_infra_termination_reason(
        f"{FAILURE_REASON} after 200s (budget 120s)"
    ) == FAILURE_REASON
    assert (
        canonical_infra_termination_reason(
            "Stuck in 'running' for 901s (timeout 600s + grace 300s)"
        )
        == "TIMEOUT"
    )


def _wire_fail_closed(monkeypatch, battle: dict, *, updates, elo_calls, upserts, scores, events):
    from agent_arena.persistence import service

    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle) if bid == battle["id"] else None)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "scores_list", lambda bid: [])
    monkeypatch.setattr(
        service,
        "battle_result_upsert",
        lambda bid, mid, **kw: upserts.append({"battle_id": bid, "model_id": mid, **kw})
        or {"battle_id": bid, "model_id": mid, **kw},
    )
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: scores.append(
            {"battle_id": bid, "model_id": mid, "score": score, **kw}
        ),
    )
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo_calls.append(a),
    )
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda bid, payload: (updates.append(dict(payload)), battle.update(payload)),
    )
    monkeypatch.setattr(
        "agent_arena.event_bus.publish",
        lambda bid, ev: events.append(ev),
    )


def test_fail_closed_incomplete_writes_failed_infra_results_no_elo(monkeypatch):
    battle = {
        "id": "b-fail-closed",
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "target_id": "tinyshop",
        "battle_config": {},
    }
    updates: list[dict] = []
    elo_calls: list = []
    upserts: list[dict] = []
    scores: list[dict] = []
    events: list = []
    _wire_fail_closed(
        monkeypatch,
        battle,
        updates=updates,
        elo_calls=elo_calls,
        upserts=upserts,
        scores=scores,
        events=events,
    )

    result = fail_closed_incomplete("b-fail-closed", reason=INCOMPLETE_EVIDENCE)
    assert result["ok"] is True
    assert result["status"] == "failed"
    assert result["already_finalized"] is False
    assert result["authoritative"] is True
    assert result.get("retryable") is False
    assert battle["status"] == "failed"
    assert battle.get("failure_reason") == INCOMPLETE_EVIDENCE
    assert battle.get("finalized_at") is not None
    assert [item.get("status") for item in updates] == ["failed"]
    assert all(item.get("finalized_at") is not None for item in updates)
    assert elo_calls == []
    assert len(upserts) == 2
    assert {(row["phase"], row["role"], row["model_id"]) for row in upserts} == {
        ("main", "fighter", "model-a"),
        ("main", "fighter", "model-b"),
    }
    for row in upserts:
        assert row["passed"] is False
        assert row["score"] == 0.0
        assert row["status"] == "crashed"
        assert row["verification_status"] == "infra_failure"
        assert row["termination_reason"] == INCOMPLETE_EVIDENCE
        assert 999.0 != row["score"]
    assert scores and all(item["score"] == 0.0 for item in scores)
    assert all(item.get("justification") == INFRA_SCORE_JUSTIFICATION for item in scores)
    assert all("arena-score-v1" not in str(item.get("justification") or "") for item in scores)
    dumped = str(events)
    assert "failed" in dumped
    assert any(
        ev.get("type") == "battle_status"
        and (ev.get("data") or {}).get("authoritative") is True
        for ev in events
    )

    again = fail_closed_incomplete("b-fail-closed", reason=INCOMPLETE_EVIDENCE)
    assert again["already_finalized"] is True
    assert again["status"] == "failed"
    assert len(upserts) == 2
    assert len(scores) == 2
    assert elo_calls == []


def test_fail_closed_does_not_overwrite_cancelled(monkeypatch):
    battle = {
        "id": "b-fail-can",
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
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cancelled must not be rewritten")),
    )
    monkeypatch.setattr(
        service,
        "battle_result_upsert",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cancelled must not receive results")),
    )
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cancelled must not receive scores")),
    )

    result = fail_closed_incomplete("b-fail-can", reason=INCOMPLETE_EVIDENCE)
    assert result["already_finalized"] is True
    assert result["status"] == "cancelled"


def test_internal_finalize_sandbox_end_fail_closes(monkeypatch):
    from agent_arena.internal_router import FinalizeBody, internal_finalize

    monkeypatch.setattr(
        "agent_arena.internal_router._require_battle_token", lambda *a, **k: None
    )
    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda *a, **k: None)

    finalize_calls = {"n": 0}
    fail_closed_calls: list[tuple[str, str]] = []

    def fake_finalize(bid, **kw):
        finalize_calls["n"] += 1
        assert kw.get("caller_scores") == {"model-a": 999.0}
        return {
            "ok": False,
            "status": "running",
            "already_finalized": False,
            "authoritative": False,
            "retryable": True,
            "error": INCOMPLETE_EVIDENCE,
            "scores": {},
            "results": [],
        }

    def fake_fail_closed(bid, *, reason):
        fail_closed_calls.append((bid, reason))
        return {
            "ok": True,
            "status": "failed",
            "already_finalized": False,
            "authoritative": True,
            "retryable": False,
            "results": [
                {
                    "model_id": "model-a",
                    "passed": False,
                    "score": 0.0,
                    "verification_status": "infra_failure",
                }
            ],
            "scores": {"model-a": 0.0},
        }

    monkeypatch.setattr("agent_arena.finalization.finalize_battle", fake_finalize)
    monkeypatch.setattr("agent_arena.finalization.fail_closed_incomplete", fake_fail_closed)

    resp = internal_finalize(
        FinalizeBody(
            battle_id="b-end",
            status="completed",
            scores={"model-a": 999.0},
        ),
        x_sandbox_token="t",
    )
    assert finalize_calls["n"] == 2
    assert fail_closed_calls == [("b-end", INCOMPLETE_EVIDENCE)]
    assert resp["status"] == "failed"
    assert resp["authoritative"] is True
    assert 999.0 not in (resp.get("scores") or {}).values()


def test_internal_finalize_reread_completes_without_fail_closed(monkeypatch):
    from agent_arena.internal_router import FinalizeBody, internal_finalize

    monkeypatch.setattr(
        "agent_arena.internal_router._require_battle_token", lambda *a, **k: None
    )
    monkeypatch.setattr("agent_arena.internal_router._rate_limit", lambda *a, **k: None)

    n = {"i": 0}

    def fake_finalize(bid, **kw):
        n["i"] += 1
        if n["i"] == 1:
            return {
                "ok": False,
                "status": "running",
                "retryable": True,
                "error": INCOMPLETE_EVIDENCE,
                "scores": {},
            }
        return {
            "ok": True,
            "status": "completed",
            "already_finalized": False,
            "authoritative": True,
            "scores": {"model-a": 1.0},
        }

    monkeypatch.setattr("agent_arena.finalization.finalize_battle", fake_finalize)
    monkeypatch.setattr(
        "agent_arena.finalization.fail_closed_incomplete",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not fail-close after evidence lands")
        ),
    )

    resp = internal_finalize(
        FinalizeBody(battle_id="b-race", status="completed", scores={}),
        x_sandbox_token="t",
    )
    assert n["i"] == 2
    assert resp["status"] == "completed"
