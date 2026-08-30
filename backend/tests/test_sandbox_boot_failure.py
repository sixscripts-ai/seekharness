"""Sandbox bootstrap death must fail immediately as infrastructure, not hang on running."""

from __future__ import annotations

import json

from agent_arena import event_bus, sandbox_launcher, target_verifier
from agent_arena.battle_public import public_battle_payload, public_winner
from agent_arena.persistence import service
from agent_arena.results import is_infra_outcome, is_learnable_model_outcome


class _DeadSandbox:
    def poll(self):
        return 1


class _LiveSandbox:
    def poll(self):
        return None


def _queued_target_battle(battle_id: str) -> dict:
    return {
        "id": battle_id,
        "user_id": "u1",
        "format_id": "fast-code",
        "status": "queued",
        "arena_size": 1,
        "model_ids": ["host:modal-kimi"],
        "ranked": False,
        "target_id": "tinyshop",
        "battle_config": {},
    }


def _wire_finalize(monkeypatch, battle: dict, *, updates: list, elo_calls: list, events: list) -> None:
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

    def _update(bid, payload):
        updates.append(dict(payload))
        battle.update(payload)

    monkeypatch.setattr(service, "battle_update", _update)
    monkeypatch.setattr(event_bus, "publish", lambda bid, ev: events.append(ev))


def test_sandbox_boot_outcome_is_infrastructure():
    assert is_infra_outcome("SANDBOX_BOOT_FAILURE") is True
    assert is_learnable_model_outcome("SANDBOX_BOOT_FAILURE") is False


def test_await_bootstrap_fails_on_immediate_exit():
    try:
        sandbox_launcher.await_sandbox_bootstrap(_DeadSandbox(), timeout_seconds=0)
    except sandbox_launcher.SandboxBootError:
        return
    raise AssertionError("expected SandboxBootError")


def test_await_bootstrap_accepts_live_process():
    sandbox_launcher.await_sandbox_bootstrap(_LiveSandbox(), timeout_seconds=0)


def test_dead_sandbox_never_stays_running(monkeypatch):
    battle = _queued_target_battle("b-boot-dead")
    updates: list[dict] = []
    elo_calls: list = []
    events: list = []
    verify_calls: list = []
    _wire_finalize(monkeypatch, battle, updates=updates, elo_calls=elo_calls, events=events)
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "1")
    monkeypatch.setenv("ARENA_SANDBOX_BOOT_WAIT_SECONDS", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "try_spawn_modal_sandbox",
        lambda battle_id: ("sb-dead", _DeadSandbox()),
    )
    monkeypatch.setattr(sandbox_launcher, "stop_sandbox", lambda sid: None)
    monkeypatch.setattr(
        target_verifier,
        "verify_target_submission",
        lambda *a, **k: verify_calls.append((a, k)),
    )

    sandbox_launcher.start_battle("b-boot-dead")

    assert battle["status"] == "failed"
    assert battle.get("failure_reason") == "SANDBOX_BOOT_FAILURE"
    assert all(item.get("status") != "running" for item in updates)
    assert elo_calls == []
    assert verify_calls == []
    dumped = json.dumps(events)
    assert "SANDBOX_BOOT_FAILURE" in dumped
    assert "ModuleNotFoundError" not in dumped
    assert "Traceback" not in dumped
    assert "hidden_command" not in dumped
    assert "hidden_hash" not in dumped


def test_spawn_exception_is_coarse_public_boot_failure(monkeypatch):
    battle = _queued_target_battle("b-boot-exc")
    updates: list[dict] = []
    elo_calls: list = []
    events: list = []
    _wire_finalize(monkeypatch, battle, updates=updates, elo_calls=elo_calls, events=events)
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "1")

    def _boom(battle_id: str):
        raise ModuleNotFoundError("No module named 'yaml'")

    monkeypatch.setattr(sandbox_launcher, "try_spawn_modal_sandbox", _boom)

    sandbox_launcher.start_battle("b-boot-exc")

    assert battle["status"] == "failed"
    assert battle.get("failure_reason") == "SANDBOX_BOOT_FAILURE"
    dumped = json.dumps(events)
    assert "SANDBOX_BOOT_FAILURE" in dumped
    assert "ModuleNotFoundError" not in dumped
    assert "yaml" not in dumped
    assert elo_calls == []
    payload = public_battle_payload(
        battle,
        results=[
            {
                "model_id": "host:modal-kimi",
                "passed": False,
                "score": 0.0,
                "verification_status": "infra_failure",
                "termination_reason": "SANDBOX_BOOT_FAILURE",
            }
        ],
        score_rows=[{"model_id": "host:modal-kimi", "score": 0.0}],
    )
    assert payload["winner"] is None
    assert payload["verified_solution"] is False
    assert payload["verification_status"] == "infra_failure"
    assert public_winner(verified_solution=False, results=payload.get("results")) is None


def test_live_sandbox_reaches_running(monkeypatch):
    battle = _queued_target_battle("b-boot-live")
    updates: list[dict] = []
    elo_calls: list = []
    events: list = []
    _wire_finalize(monkeypatch, battle, updates=updates, elo_calls=elo_calls, events=events)
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "1")
    monkeypatch.setenv("ARENA_SANDBOX_BOOT_WAIT_SECONDS", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "try_spawn_modal_sandbox",
        lambda battle_id: ("sb-live", _LiveSandbox()),
    )

    sandbox_launcher.start_battle("b-boot-live")

    assert any(item.get("status") == "running" for item in updates)
    assert battle["status"] == "running"
    assert battle.get("failure_reason") is None
    assert elo_calls == []
