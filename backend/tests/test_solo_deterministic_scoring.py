"""Tests for solo deterministic scoring behavior."""

from __future__ import annotations

from agent_arena import evidence, scoring


def test_solo_verified_solution_scores_one():
    results = [
        {
            "model_id": "solo-fighter",
            "role": "fighter",
            "phase": "solve",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 5,
            "policy": {"status": "clean", "violations": []},
            "files": {"solution.py": "code"},
            "artifact_checks": {"present": ["solution.py"], "missing": []},
        }
    ]
    summary = evidence.build_battle_evidence("b-solo-1", results, {})
    decision = scoring.decide_winner(summary, {})
    scores = scoring.deterministic_scores(decision, summary)

    assert decision["winner"] == "solo-fighter"
    assert decision["verified_solution"] is True
    assert scores == {"solo-fighter": 1.0}


def test_solo_failed_solution_scores_zero():
    results = [
        {
            "model_id": "solo-fighter",
            "role": "fighter",
            "phase": "solve",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 10,
            "policy": {"status": "clean", "violations": []},
            "files": {},
            "artifact_checks": {"present": [], "missing": ["solution.py"]},
        }
    ]
    summary = evidence.build_battle_evidence("b-solo-2", results, {})
    decision = scoring.decide_winner(summary, {})
    scores = scoring.deterministic_scores(decision, summary)

    assert decision["verified_solution"] is False
    assert scores == {"solo-fighter": 0.0}


def test_multi_fighter_ranking_unaffected():
    results = [
        {
            "model_id": "fighter-a",
            "role": "fighter",
            "phase": "solve",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 5,
            "policy": {"status": "clean", "violations": []},
            "files": {"solution.py": "code"},
            "artifact_checks": {"present": ["solution.py"], "missing": []},
        },
        {
            "model_id": "fighter-b",
            "role": "fighter",
            "phase": "solve",
            "outcome": "TEST_FAIL",
            "passed": False,
            "steps": 10,
            "policy": {"status": "clean", "violations": []},
            "files": {},
            "artifact_checks": {"present": [], "missing": ["solution.py"]},
        },
    ]
    summary = evidence.build_battle_evidence("b-multi", results, {})
    decision = scoring.decide_winner(summary, {})
    scores = scoring.deterministic_scores(decision, summary)

    assert decision["winner"] == "fighter-a"
    assert scores == {"fighter-a": 1.0, "fighter-b": 0.0}
