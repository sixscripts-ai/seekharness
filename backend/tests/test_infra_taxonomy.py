"""Infrastructure outcomes must not become learnable model losses."""

from __future__ import annotations

from agent_arena.memory import maybe_remember
from agent_arena.results import is_infra_outcome, is_learnable_model_outcome
from agent_arena.skills.attribution import compute_skill_attributions, is_learnable_outcome


def test_infra_outcomes_are_not_learnable():
    for outcome in (
        "PROVIDER_ERROR",
        "PROVIDER_TIMEOUT",
        "SANDBOX_ERROR",
        "VERIFY_ERROR",
        "VERIFICATION_ERROR",
        "EXECUTOR_CRASH",
        "INFRASTRUCTURE_FAILURE",
        "TIMEOUT",
        "CANCELLED",
    ):
        assert is_infra_outcome(outcome) is True
        assert is_learnable_model_outcome(outcome) is False
        assert is_learnable_outcome(outcome) is False


def test_model_failures_remain_learnable():
    for outcome in ("TEST_FAIL", "STEP_BUDGET_EXCEEDED", "TEST_PASS"):
        assert is_infra_outcome(outcome) is False
        assert is_learnable_model_outcome(outcome) is True


def test_infra_does_not_attribute_skill_loss():
    results = [
        {
            "role": "player_a",
            "passed": False,
            "outcome": "PROVIDER_ERROR",
            "skill_reads": ["python-kata-fixer"],
        },
        {
            "role": "player_b",
            "passed": True,
            "outcome": "TEST_PASS",
            "skill_reads": ["python-kata-fixer"],
        },
    ]
    attrs = compute_skill_attributions(results)
    assert attrs["player_a"] == []
    assert attrs["player_b"][0]["outcome"] == "win"


class _FakeDB:
    def __init__(self):
        self._docs = []

    def create_document(self, database_id, collection, doc_id, payload):
        doc = type("Doc", (), {"id": "m1", "data": dict(payload)})()
        self._docs.append(doc)
        return doc

    def list_documents(self, database_id, collection, queries=None):
        return type("Res", (), {"documents": list(self._docs)})()


def test_infra_outcome_writes_no_memory():
    db = _FakeDB()
    assert (
        maybe_remember(
            db,
            "db",
            insight="provider outage",
            outcome="PROVIDER_ERROR",
            user_id="u",
            model_id="m",
        )
        is None
    )
    assert (
        maybe_remember(
            db,
            "db",
            insight="verify crashed",
            outcome="VERIFY_ERROR",
            user_id="u",
            model_id="m",
        )
        is None
    )
    assert db._docs == []


def test_infra_skips_elo_side_effects(monkeypatch):
    from agent_arena.finalization import finalize_battle
    from agent_arena.persistence import service

    battle = {
        "id": "b-infra-elo",
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["model-a", "model-b"],
        "ranked": True,
        "battle_config": {},
    }
    elo_calls: list = []
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle)
    monkeypatch.setattr(service, "format_get", lambda fid: None)
    monkeypatch.setattr(service, "score_upsert", lambda *a, **k: None)
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo_calls.append(a),
    )
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle.update(payload))
    result = finalize_battle(
        "b-infra-elo",
        override_results=[
            {
                "model_id": "model-a",
                "role": "player_a",
                "phase": "race",
                "outcome": "PROVIDER_ERROR",
                "passed": False,
                "steps": 1,
                "artifact_checks": {"present": [], "missing": []},
            },
            {
                "model_id": "model-b",
                "role": "player_b",
                "phase": "race",
                "outcome": "TEST_PASS",
                "passed": True,
                "steps": 2,
                "artifact_checks": {"present": ["solution.py"], "missing": []},
            },
        ],
    )
    assert result["status"] == "completed"
    assert elo_calls == []


def test_unknown_outcome_is_not_learnable():
    assert is_learnable_model_outcome("CUSTOM_WEIRD") is False
    assert is_learnable_model_outcome("") is False
    assert is_learnable_model_outcome(None) is False
    assert is_learnable_model_outcome("WIN") is True
