"""Compromised library revisions cannot update Elo, ranking, or skill learning."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_arena import mock_runner
from agent_arena.custom_battles import is_ranked_battle
from agent_arena.target_library import (
    COMPROMISED_LIBRARY_TARGET_IDS,
    RANKED_TARGET_ALLOWLIST,
    compile_target_to_battle_config,
    get_target_library,
    target_ranked_eligible,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = REPO_ROOT / "targets" / "library"


def test_ranked_allowlist_does_not_enable_current_targets():
    assert RANKED_TARGET_ALLOWLIST == frozenset()
    assert len(COMPROMISED_LIBRARY_TARGET_IDS) == 10
    for tid in COMPROMISED_LIBRARY_TARGET_IDS:
        assert target_ranked_eligible(tid, "1.0.0") is False
        assert target_ranked_eligible(tid) is False
        assert is_ranked_battle({"target_id": tid, "target_version": "1.0.0"}) is False
        assert is_ranked_battle({"target_id": tid}) is False
        assert is_ranked_battle({}, {"target_id": tid, "target_version": "1.0.0"}) is False


def test_compiled_compromised_targets_default_ranked_false():
    registry = get_target_library(LIBRARY_ROOT)
    for tid in COMPROMISED_LIBRARY_TARGET_IDS:
        bundle = registry.get_target(tid)
        assert bundle is not None, tid
        cfg = compile_target_to_battle_config(bundle, arena_size=1)
        assert cfg["ranked"] is False
        assert is_ranked_battle({"target_id": tid, "target_version": bundle.version}, cfg) is False


def test_allowlist_gate_admits_only_explicit_rotated_pairs(monkeypatch: pytest.MonkeyPatch):
    import agent_arena.target_library as target_library

    monkeypatch.setattr(
        target_library,
        "RANKED_TARGET_ALLOWLIST",
        frozenset({("future-rotated-target", "2.0.0")}),
    )
    assert target_library.target_ranked_eligible("future-rotated-target", "2.0.0") is True
    assert target_library.target_ranked_eligible("tinyshop", "1.0.0") is False
    assert is_ranked_battle(
        {"target_id": "future-rotated-target", "target_version": "2.0.0"}
    ) is True
    assert is_ranked_battle({"target_id": "tinyshop", "target_version": "1.0.0"}) is False


def test_compromised_target_battle_does_not_update_elo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agent_arena import custom_battles, target_library
    from agent_arena.persistence import service

    monkeypatch.setattr(
        target_library, "PRODUCTION_EVALUATOR_MOUNT", tmp_path / "no-prod"
    )
    empty = tmp_path / "empty-evaluators"
    empty.mkdir()
    monkeypatch.setenv("ARENA_EVALUATOR_DIR", str(empty))

    battle = {
        "id": "battle-unranked-1",
        "status": "queued",
        "format_id": "fmt-1",
        "model_ids": ["model-a", "model-b"],
        "target_id": "tinyshop",
        "target_version": "1.0.0",
        "ranked": False,
    }
    updates: list[dict] = []
    elo: list = []
    monkeypatch.setattr(service, "battle_get", lambda *a, **k: dict(battle))
    monkeypatch.setattr(service, "format_get", lambda *a, **k: {"config": {}})
    monkeypatch.setattr(
        service, "battle_update", lambda battle_id, payload: updates.append(payload)
    )
    monkeypatch.setattr(service, "round_create", lambda *a, **k: None)
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo.append((a, k)),
    )
    monkeypatch.setattr(
        custom_battles,
        "resolve_battle_config",
        lambda *a, **k: {
            "target_id": "tinyshop",
            "target_version": "1.0.0",
            "ranked": False,
            "roles": ["fighter"],
        },
    )

    mock_runner.run_battle("battle-unranked-1")

    assert elo == []
    completed = [u for u in updates if u.get("status") == "completed"]
    assert completed, updates
