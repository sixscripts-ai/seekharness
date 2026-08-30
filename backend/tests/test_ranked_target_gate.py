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


def _capture_aw_create(monkeypatch: pytest.MonkeyPatch) -> dict:
    from agent_arena.persistence import service

    captured: dict = {}

    class _Doc:
        id = "battle-persist-1"

    class _DB:
        def create_document(self, _database_id, _collection, _doc_id, payload):
            captured.update(payload)
            return _Doc()

    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "_aw", lambda: (_DB(), "db"))
    return captured


def test_explicit_ranked_false_survives_appwrite_create(monkeypatch: pytest.MonkeyPatch):
    from agent_arena.persistence import service

    captured = _capture_aw_create(monkeypatch)
    monkeypatch.setattr(
        service,
        "format_get",
        lambda _fid: {"config": {"engine": "agent_tool_race", "roles": ["fighter"]}},
    )
    monkeypatch.setattr(service, "battle_count_active", lambda _uid: 0)

    class _Bundle:
        id = "tinyshop"
        version = "1.0.0"
        name = "TinyShop"
        manifest_hash = "mh-tinyshop"

    class _Registry:
        def get_target(self, target_id):
            return _Bundle() if target_id == "tinyshop" else None

    monkeypatch.setattr(
        "agent_arena.target_library.get_target_library", lambda *a, **k: _Registry()
    )
    monkeypatch.setattr(
        "agent_arena.target_library.compile_target_to_battle_config",
        lambda bundle, arena_size=1: {
            "target_id": bundle.id,
            "target_version": bundle.version,
            "ranked": False,
            "roles": ["fighter"],
        },
    )

    created = service.battle_create(
        "user-1",
        format_id="fmt-1",
        model_ids=["host:openrouter-free"],
        arena_size=1,
        timeout_seconds=180,
        round_visibility="isolated",
        save=True,
        target_id="tinyshop",
        target_version="1.0.0",
    )
    assert created["id"] == "battle-persist-1"
    assert "ranked" in captured
    assert captured["ranked"] is False
    assert captured["ranked"] is not None


def test_postgres_create_persists_ranked_false_not_null(
    monkeypatch: pytest.MonkeyPatch,
):
    from contextlib import contextmanager

    from agent_arena.persistence import repositories, service

    captured: dict = {}

    class _Battle:
        id = "pg-battle-1"

    def _pg_create(_session, **kwargs):
        captured.update(kwargs)
        return _Battle()

    @contextmanager
    def _scope():
        yield object()

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "session_scope", _scope)
    monkeypatch.setattr(service, "_dual_write", lambda *_a, **_k: None)
    monkeypatch.setattr(repositories.battles, "battle_create", _pg_create)
    monkeypatch.setattr(
        service,
        "format_get",
        lambda _fid: {"config": {"engine": "agent_tool_race", "roles": ["fighter"]}},
    )
    monkeypatch.setattr(service, "battle_count_active", lambda _uid: 0)

    class _Bundle:
        id = "tinyshop"
        version = "1.0.0"
        name = "TinyShop"
        manifest_hash = "mh-tinyshop"

    class _Registry:
        def get_target(self, target_id):
            return _Bundle() if target_id == "tinyshop" else None

    monkeypatch.setattr(
        "agent_arena.target_library.get_target_library", lambda *a, **k: _Registry()
    )
    monkeypatch.setattr(
        "agent_arena.target_library.compile_target_to_battle_config",
        lambda bundle, arena_size=1: {
            "target_id": bundle.id,
            "target_version": bundle.version,
            "ranked": False,
            "roles": ["fighter"],
        },
    )

    created = service.battle_create(
        "user-1",
        format_id="fmt-1",
        model_ids=["host:openrouter-free"],
        arena_size=1,
        timeout_seconds=180,
        round_visibility="isolated",
        save=True,
        target_id="tinyshop",
        target_version="1.0.0",
    )
    assert created["id"] == "pg-battle-1"
    assert captured["ranked"] is False


def test_explicit_ranked_true_survives_appwrite_create(monkeypatch: pytest.MonkeyPatch):
    from agent_arena.persistence import service

    captured = _capture_aw_create(monkeypatch)
    monkeypatch.setattr(
        service,
        "format_get",
        lambda _fid: {
            "config": {
                "engine": "agent_tool_race",
                "roles": ["player_a", "player_b"],
            }
        },
    )
    monkeypatch.setattr(service, "battle_count_active", lambda _uid: 0)

    created = service.battle_create(
        "user-1",
        format_id="fmt-ranked",
        model_ids=["host:openrouter-free", "host:openrouter-free"],
        arena_size=2,
        timeout_seconds=180,
        round_visibility="isolated",
        save=False,
    )
    assert created["id"] == "battle-persist-1"
    assert captured["ranked"] is True


def test_aw_create_computes_boolean_when_ranked_omitted(monkeypatch: pytest.MonkeyPatch):
    from agent_arena.persistence import service

    captured = _capture_aw_create(monkeypatch)
    service._aw_battle_create(
        {
            "user_id": "user-1",
            "format_id": "fmt-1",
            "model_ids": ["host:openrouter-free"],
            "arena_size": 1,
            "status": "queued",
            "timeout_seconds": 180,
            "round_visibility": "isolated",
            "saved": True,
            "target_id": "tinyshop",
            "target_version": "1.0.0",
            "battle_config": {
                "ranked": False,
                "target_id": "tinyshop",
                "target_version": "1.0.0",
            },
        }
    )
    assert captured["ranked"] is False


def test_caller_ranked_true_cannot_override_frozen_false(monkeypatch: pytest.MonkeyPatch):
    from agent_arena.persistence import service

    captured = _capture_aw_create(monkeypatch)
    service.battle_create_raw(
        "user-1",
        {
            "user_id": "user-1",
            "format_id": "fmt-1",
            "model_ids": ["host:openrouter-free"],
            "arena_size": 1,
            "timeout_seconds": 180,
            "round_visibility": "isolated",
            "saved": False,
            "ranked": True,
            "target_id": "tinyshop",
            "target_version": "1.0.0",
            "battle_config": {
                "ranked": False,
                "target_id": "tinyshop",
                "target_version": "1.0.0",
                "roles": ["fighter"],
            },
        },
    )
    assert captured["ranked"] is False


def test_legacy_missing_ranked_is_not_coerced_to_false():
    from agent_arena.custom_battles import is_ranked_battle

    assert is_ranked_battle({}, {"engine": "agent_tool_race"}) is True
    assert is_ranked_battle({"ranked": None}, {"engine": "agent_tool_race"}) is True
    assert is_ranked_battle({"ranked": False}, {"engine": "agent_tool_race"}) is False


def test_finalize_unranked_frozen_config_does_not_apply_elo(
    monkeypatch: pytest.MonkeyPatch,
):
    from agent_arena.finalization import finalize_battle
    from agent_arena.persistence import service

    battle = {
        "id": "battle-unranked-finalize",
        "user_id": "user-1",
        "format_id": "fmt-1",
        "status": "running",
        "arena_size": 1,
        "model_ids": ["host:openrouter-free"],
        "ranked": True,
        "target_id": "tinyshop",
        "target_version": "1.0.0",
        "battle_config": {
            "ranked": False,
            "target_id": "tinyshop",
            "target_version": "1.0.0",
            "roles": ["fighter"],
        },
    }
    elo: list = []
    stored_scores: dict = {}
    monkeypatch.setattr("agent_arena.finalization.using_postgres", lambda: False)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(service, "battle_get", lambda *a, **k: dict(battle))
    monkeypatch.setattr(service, "format_get", lambda *a, **k: {"config": {}})
    monkeypatch.setattr(service, "scores_exist", lambda *a, **k: False)
    monkeypatch.setattr(service, "scores_list", lambda *a, **k: [])
    monkeypatch.setattr(service, "events_load", lambda *a, **k: [])
    monkeypatch.setattr(service, "rounds_list", lambda *a, **k: [])
    monkeypatch.setattr(
        service,
        "score_upsert",
        lambda bid, mid, score, **kw: stored_scores.__setitem__(mid, score),
    )
    monkeypatch.setattr(service, "battle_update", lambda *a, **k: None)
    monkeypatch.setattr(
        service,
        "leaderboard_apply_result",
        lambda *a, **k: elo.append((a, k)),
    )

    result = finalize_battle(
        "battle-unranked-finalize",
        caller_status="completed",
        caller_scores={"host:openrouter-free": 99.0},
        override_results=[
            {
                "model_id": "host:openrouter-free",
                "role": "fighter",
                "phase": "main",
                "outcome": "TEST_FAIL",
                "passed": False,
                "steps": 1,
                "artifact_checks": {"present": [], "missing": []},
            }
        ],
    )
    assert result.get("ok") is True
    assert result.get("status") == "completed"
    assert elo == []
