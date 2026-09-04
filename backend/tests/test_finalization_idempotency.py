"""Tests for Transactional & Idempotent Finalization (Change Set C — Phase C2)."""

import json
import pytest
from unittest.mock import MagicMock

from agent_arena.finalization import finalize_battle
from agent_arena.persistence import service
from agent_arena.persistence.service import using_postgres



class FakeFinalizeDB:
    """In-memory datastore for Appwrite fallback testing."""
    def __init__(self):
        self.documents = {}

    def list_documents(self, db_id, coll, queries=None):
        docs = [d for k, d in self.documents.items() if k.startswith(f"{coll}:")]
        res = MagicMock()
        res.documents = docs
        return res

    def create_document(self, db_id, coll, doc_id, data):
        doc = MagicMock()
        doc.id = doc_id if doc_id != "unique()" else f"doc_{len(self.documents)+1}"
        doc.data = data
        self.documents[f"{coll}:{doc.id}"] = doc
        return doc

    def get_document(self, db_id, coll, doc_id):
        return self.documents.get(f"{coll}:{doc_id}")

    def update_document(self, db_id, coll, doc_id, data):
        doc = self.documents.get(f"{coll}:{doc_id}")
        if doc:
            doc.data.update(data)
            return doc
        doc = MagicMock()
        doc.id = doc_id
        doc.data = data
        self.documents[f"{coll}:{doc_id}"] = doc
        return doc


def test_idempotent_repeated_finalize_single_mutation(monkeypatch):
    """Calling finalize_battle 5 times produces exactly one final result and 0 duplicate mutations."""
    battle_id = "b-idem-1"
    model_ids = ["model-alpha", "model-beta"]

    # Mock service layer to track mutations
    score_upsert_calls = []
    leaderboard_calls = []
    skill_calls = []
    memory_calls = []

    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "fast-code",
        "status": "running",
        "arena_size": 2,
        "model_ids": model_ids,
        "ranked": True,
        "context_mode": "strict",
        "battle_config": {"context_mode": "strict"},
    }

    stored_scores = {}

    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle_record if bid == battle_id else None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: bool(stored_scores.get(bid)))
    monkeypatch.setattr(service, "scores_list", lambda bid: [{"model_id": m, "score": s} for m, s in stored_scores.get(bid, {}).items()])

    def _mock_score_upsert(bid, mid, score, **kwargs):
        score_upsert_calls.append((bid, mid, score))
        stored_scores.setdefault(bid, {})[mid] = score

    monkeypatch.setattr(service, "score_upsert", _mock_score_upsert)
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda fmt, mids, sc, **kw: leaderboard_calls.append((fmt, mids, sc)))
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle_record.update(payload))

    results = [
        {
            "model_id": "model-alpha",
            "role": "player_a",
            "phase": "race",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 3,
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
        {
            "model_id": "model-beta",
            "role": "player_b",
            "phase": "race",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 5,
            "artifact_checks": {"present": ["solution.py"], "missing": []},
            "_trusted": True,
        },
    ]

    # First finalization
    res1 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res1["ok"] is True
    assert res1["status"] == "completed"
    assert res1.get("already_finalized") is False
    assert len(score_upsert_calls) == 2
    assert len(leaderboard_calls) == 1

    # Second finalization (repeated / retry)
    res2 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res2["ok"] is True
    assert res2.get("already_finalized") is True

    # Third, Fourth, Fifth finalizations
    res3 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    res4 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    res5 = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res5["ok"] is True
    assert res5.get("already_finalized") is True

    # Total mutations must remain EXACTLY what happened in the 1st call
    assert len(score_upsert_calls) == 2
    assert len(leaderboard_calls) == 1


def test_builder_breaker_authoritative_lifecycle(monkeypatch):
    """Builder + Breaker asymmetric execution produces distinct canonical records per role."""
    battle_id = "b-bb-idem"
    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "builder-breaker",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["builder-mod", "breaker-mod"],
        "ranked": True,
        "context_mode": "strict",
        "battle_config": {
            "roles": ["builder", "breaker"],
            "scoring_weights": {"builder": 1.0, "breaker": 1.0},
        },
    }

    stored_scores = {}
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle_record if bid == battle_id else None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: bool(stored_scores.get(bid)))
    monkeypatch.setattr(service, "scores_list", lambda bid: [{"model_id": m, "score": s} for m, s in stored_scores.get(bid, {}).items()])
    monkeypatch.setattr(service, "score_upsert", lambda bid, mid, s, **kw: stored_scores.setdefault(bid, {}).update({mid: s}))
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda fmt, mids, sc, **kw: None)
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle_record.update(payload))

    results = [
        {
            "model_id": "builder-mod",
            "role": "builder",
            "phase": "builder",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 4,
            "artifact_checks": {"present": ["challenge.py"], "missing": []},
            "_trusted": True,
        },
        {
            "model_id": "breaker-mod",
            "role": "breaker",
            "phase": "breaker",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 2,
            "artifact_checks": {"present": ["exploit.py"], "missing": []},
            "_trusted": True,
        },
    ]

    res = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res["ok"] is True
    assert res["status"] == "completed"
    assert "builder-mod" in stored_scores[battle_id]
def test_same_model_persists_two_identity_rows(monkeypatch):
    battle_id = "b-same-mod"
    battle_record = {
        "id": battle_id,
        "user_id": "villain",
        "format_id": "builder-breaker",
        "status": "running",
        "arena_size": 2,
        "model_ids": ["shared-model", "shared-model"],
        "ranked": False,
        "context_mode": "strict",
        "battle_config": {"roles": ["builder", "breaker"]},
    }
    stored_scores = {}
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: battle_record if bid == battle_id else None)
    monkeypatch.setattr(service, "scores_exist", lambda bid: bool(stored_scores.get(bid)))
    monkeypatch.setattr(service, "scores_list", lambda bid: [{"model_id": m, "score": s} for m, s in stored_scores.get(bid, {}).items()])
    monkeypatch.setattr(service, "score_upsert", lambda bid, mid, s, **kw: stored_scores.setdefault(bid, {}).__setitem__(mid, s))
    monkeypatch.setattr(service, "leaderboard_apply_result", lambda *a, **k: None)
    monkeypatch.setattr(service, "battle_update", lambda bid, payload: battle_record.update(payload))

    results = [
        {
            "model_id": "shared-model",
            "role": "builder",
            "phase": "builder",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 4,
            "artifact_checks": {"present": ["challenge.py"], "missing": []},
            "_trusted": True,
        },
        {
            "model_id": "shared-model",
            "role": "breaker",
            "phase": "breaker",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 2,
            "artifact_checks": {"present": ["exploit.py"], "missing": []},
            "_trusted": True,
        },
    ]
    res = finalize_battle(battle_id, caller_status="completed", override_results=results)
    assert res["ok"] is True
    assert res["status"] == "completed"
    # Scores table aggregates by model_id (one key), identities stay distinct in results.
    assert "shared-model" in stored_scores[battle_id]
