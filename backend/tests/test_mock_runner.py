"""Tests for the in-process mock runner's config normalization.

The mock runner previously crashed with KeyError("phases") for target-library
battles whose config carries a nested `battle_plan.phases` instead of a
legacy top-level `phases` list. These tests cover the normalization helper
without touching Appwrite.
"""

from __future__ import annotations

from agent_arena.mock_runner import _iter_phases, _mock_score


def test_iter_phases_legacy_top_level():
    cfg = {
        "phases": [
            {"name": "duel", "participants": ["a", "b", "judge"]},
            {"name": "judge", "participants": ["judge"]},
        ]
    }
    assert _iter_phases(cfg) == [("duel", ["a", "b"])]


def test_iter_phases_battle_plan_target():
    cfg = {
        "roles": ["builder", "breaker"],
        "battle_plan": {
            "plan_id": "target-plan-x",
            "phases": [
                {"phase_id": "build", "phase_type": "build", "actor": "builder"},
                {"phase_id": "break", "phase_type": "break", "actor": "breaker"},
            ],
        },
    }
    assert _iter_phases(cfg) == [
        ("build", ["builder"]),
        ("break", ["breaker"]),
    ]


def test_iter_phases_roles_fallback():
    cfg = {"roles": ["fighter_1", "fighter_2", "judge"]}
    assert _iter_phases(cfg) == [("race", ["fighter_1", "fighter_2"])]


def test_iter_phases_empty_config_no_crash():
    assert _iter_phases({}) == []
    assert _iter_phases(None) == []


def test_mock_score_is_deterministic():
    a = _mock_score("battle-1", "model-1")
    b = _mock_score("battle-1", "model-1")
    assert a == b
    assert 0.0 <= a <= 100.0
