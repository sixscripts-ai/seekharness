"""Battle-scoped database provisioning and cleanup lifecycle tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from agent_arena import sandbox_launcher
from agent_arena.battle_public import public_battle_payload
from agent_arena.neon_branch_manager import BranchResult
from agent_arena.persistence import service
from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors.advanced_executor import ToolSession
from agent_arena.sandbox.runner import run_battle_loop
from agent_arena.target_library import (
    compile_target_to_battle_config,
    get_target_library,
    target_requires_battle_database,
)

TARGET_LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "targets" / "library"


def test_start_battle_owns_database_lease_around_runner(monkeypatch):
    battle_id = "battle-db-lifecycle"
    battle = {
        "id": battle_id,
        "status": "queued",
        "target_id": "",
        "model_ids": ["model-a"],
        "round_visibility": "isolated",
        "timeout_seconds": 30,
    }
    branch = BranchResult(
        branch_id="br-battle-db-lifecycle",
        name="battle-db-lifecycle",
        database_url="postgresql://rw.invalid/db",
        read_only_database_url="postgresql://ro.invalid/db",
        parent_id="main",
        is_mock=True,
    )
    calls: list[tuple] = []

    class FakeManager:
        def create_ephemeral_branch(self, battle_id: str):
            calls.append(("provision", battle_id))
            return branch

        def initialize_battle_database(self, branch, *, database_config=None):
            calls.append(("initialize", branch.branch_id, dict(database_config or {})))

        def delete_branch(self, branch_id: str):
            calls.append(("cleanup", branch_id))
            return True

    def update(bid: str, fields: dict):
        calls.append(("update", bid, dict(fields)))
        battle.update(fields)

    def run(bid: str, **kwargs):
        calls.append(
            (
                "run",
                bid,
                kwargs["battle_db_lease"].read_only_database_url,
                kwargs["battle_db_lease"].branch.branch_id,
            )
        )

    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda bid: (
            None,
            None,
            battle,
            {
                "database": {
                    "required": True,
                    "engine": "postgresql",
                    "application_write": True,
                }
            },
        ),
    )
    monkeypatch.setattr(sandbox_launcher, "NeonBranchManager", FakeManager, raising=False)
    monkeypatch.setattr(sandbox_launcher, "run_in_process", run)
    monkeypatch.setattr(service, "battle_get", lambda _uid, _bid: battle)
    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "battle_update", update)

    sandbox_launcher.start_battle(battle_id)

    assert calls[0] == ("provision", battle_id)
    assert calls[1] == (
        "initialize",
        branch.branch_id,
        {
            "required": True,
            "engine": "postgresql",
            "application_write": True,
        },
    )
    assert calls[2][0] == "update"
    assert calls[2][2]["battle_db_branch_id"] == branch.branch_id
    assert calls[3] == (
        "run",
        battle_id,
        branch.read_only_database_url,
        branch.branch_id,
    )
    assert calls[4] == ("cleanup", branch.branch_id)


def test_database_provisioning_is_gated_by_the_frozen_target_contract():
    registry = get_target_library(TARGET_LIBRARY_ROOT)
    bank = registry.get_target("fullstack-bank-vault")
    non_database_fullstack = registry.get_target("fullstack-ssrf-portal")
    assert bank is not None
    assert non_database_fullstack is not None

    bank_cfg = compile_target_to_battle_config(bank)
    non_database_cfg = compile_target_to_battle_config(non_database_fullstack)

    assert target_requires_battle_database(bank_cfg) is True
    assert bank_cfg["database"] == {
        "required": True,
        "engine": "postgresql",
        "application_write": True,
    }
    assert target_requires_battle_database(non_database_cfg) is False


def test_malformed_frozen_database_policy_fails_closed():
    for cfg in ([], {"database": []}, {"database": {"required": "true"}}):
        try:
            target_requires_battle_database(cfg)
        except ValueError:
            continue
        raise AssertionError("malformed frozen database policy was accepted")


def test_start_battle_does_not_provision_for_a_non_database_target(monkeypatch):
    battle_id = "battle-no-database-target"
    runs: list[str] = []
    provisions: list[str] = []
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda _bid: (
            None,
            None,
            {"id": battle_id, "target_id": "", "model_ids": []},
            {"database": {"required": False, "engine": "", "application_write": False}},
        ),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "provision_battle_database",
        lambda bid, **_kwargs: provisions.append(bid),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "run_in_process",
        lambda bid, **_kwargs: runs.append(bid),
    )

    sandbox_launcher.start_battle(battle_id)

    assert provisions == []
    assert runs == [battle_id]


def test_cleanup_rejects_a_branch_handle_from_another_battle(monkeypatch):
    battle_id = "battle-cleanup-identity"
    deleted: list[str] = []

    class FakeManager:
        def delete_branch(self, branch_id: str):
            deleted.append(branch_id)
            return True

    monkeypatch.setattr(sandbox_launcher, "NeonBranchManager", FakeManager)
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(
        service,
        "battle_get",
        lambda _uid, _bid: {"id": battle_id, "battle_db_branch_id": "br-owned"},
    )

    assert (
        sandbox_launcher.cleanup_battle_database(
            battle_id,
            branch_id="br-from-another-battle",
        )
        is False
    )
    assert deleted == []


def test_run_battle_loop_passes_database_capability_to_executor(monkeypatch):
    seen: dict = {}

    class CaptureExecutor:
        def run_battle(self, **kwargs):
            seen.update(kwargs)
            return {}

    monkeypatch.setattr(
        "agent_arena.sandbox.runner.get_executor",
        lambda _cfg: CaptureExecutor(),
    )
    run_battle_loop(
        battle_id="battle-db-runner",
        format_config={
            "engine": "scripted",
            "roles": ["fighter", "judge"],
            "phases": [],
        },
        model_ids=["model-a"],
        timeout_seconds=30,
        client=InternalClient(FakeTransport()),
        battle_ro_database_url="postgresql://battle-ro.invalid/db",
    )

    assert seen["battle_ro_database_url"] == "postgresql://battle-ro.invalid/db"


def test_database_capability_is_tool_bound_but_not_child_inherited(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", "postgresql://control.invalid/db")
    monkeypatch.setenv("BATTLE_DATABASE_URL", "postgresql://battle-rw.invalid/db")
    monkeypatch.setenv("BATTLE_TOKEN", "battle-token")
    session = ToolSession(
        tmp_path,
        battle_ro_database_url="postgresql://battle-ro.invalid/db",
    )

    try:
        assert (
            session.fighter_environment["BATTLE_RO_DATABASE_URL"]
            == "postgresql://battle-ro.invalid/db"
        )
        assert "DATABASE_URL" not in session.fighter_environment
        assert "BATTLE_DATABASE_URL" not in session.fighter_environment
        child_env = session._fighter_process_env()
        assert "BATTLE_RO_DATABASE_URL" not in child_env
        assert "DATABASE_URL" not in child_env
        assert "BATTLE_DATABASE_URL" not in child_env
        assert "BATTLE_TOKEN" not in child_env
    finally:
        session.close()


def test_neon_provisioning_without_scoped_credentials_fails_closed(monkeypatch):
    monkeypatch.setenv("ARENA_HERMETIC", "0")
    monkeypatch.setenv("ARENA_USE_MOCK", "0")
    monkeypatch.delenv("BATTLE_NEON_API_KEY", raising=False)
    monkeypatch.delenv("NEON_API_KEY", raising=False)

    manager = sandbox_launcher.NeonBranchManager(api_key=None)

    try:
        manager.create_ephemeral_branch("battle-no-neon-credentials")
    except sandbox_launcher.NeonProvisioningError as exc:
        assert "ARENA_INFRA_FAILURE" in str(exc)
    else:
        raise AssertionError("expected missing Battle Neon credentials to fail closed")


def test_malformed_database_capability_fails_closed(monkeypatch):
    battle_id = "battle-db-malformed-capability"

    class Manager:
        def create_ephemeral_branch(self, _battle_id):
            return None

    monkeypatch.setenv("ARENA_USE_MOCK", "1")
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(sandbox_launcher, "NeonBranchManager", Manager)

    try:
        sandbox_launcher.provision_battle_database(battle_id)
    except sandbox_launcher.NeonProvisioningError as exc:
        assert "ARENA_INFRA_FAILURE" in str(exc)
    else:
        raise AssertionError("expected malformed database capability to fail closed")


def test_neon_branch_delete_treats_missing_branch_as_idempotent(monkeypatch):
    from unittest.mock import MagicMock, patch

    manager = sandbox_launcher.NeonBranchManager(
        api_key="neon-test-key", project_id="ep-project"
    )
    manager.use_mock = False
    response = MagicMock(status_code=404)
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.delete.return_value = response
        client_cls.return_value = client

        assert manager.delete_branch("br-already-gone") is True


def test_cleanup_failure_is_observable_and_retry_is_idempotent(monkeypatch):
    battle_id = "battle-db-cleanup"
    branch = BranchResult(
        branch_id="br-battle-db-cleanup",
        name="battle-db-cleanup",
        database_url="postgresql://rw.invalid/db",
        read_only_database_url="postgresql://ro.invalid/db",
        parent_id="main",
        is_mock=True,
    )
    calls: list[str] = []
    events: list[dict] = []

    class FlakyManager:
        def create_ephemeral_branch(self, _battle_id):
            return branch

        def delete_branch(self, branch_id):
            calls.append(branch_id)
            return len(calls) > 1

    monkeypatch.setenv("ARENA_USE_MOCK", "1")
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(sandbox_launcher, "NeonBranchManager", FlakyManager)
    monkeypatch.setattr(
        sandbox_launcher.event_bus,
        "publish",
        lambda _bid, event: events.append(event),
    )

    sandbox_launcher.provision_battle_database(battle_id)
    assert sandbox_launcher.cleanup_battle_database(battle_id) is False
    assert events[-1]["data"] == {
        "status": "failed",
        "authoritative": True,
        "reason": "branch_revoke_failed",
    }
    assert sandbox_launcher.cleanup_battle_database(battle_id) is True
    assert sandbox_launcher.cleanup_battle_database(battle_id) is True
    assert calls == [branch.branch_id, branch.branch_id]
    assert events[-1]["data"] == {"status": "completed", "authoritative": True}


def test_partial_provisioning_revokes_branch_when_handle_persist_fails(monkeypatch):
    battle_id = "battle-db-partial"
    branch = BranchResult(
        branch_id="br-battle-db-partial",
        name="battle-db-partial",
        database_url="postgresql://rw.invalid/db",
        read_only_database_url="postgresql://ro.invalid/db",
        parent_id="main",
        is_mock=True,
    )
    deleted: list[str] = []

    class Manager:
        def create_ephemeral_branch(self, _battle_id):
            return branch

        def delete_branch(self, branch_id):
            deleted.append(branch_id)
            return True

    monkeypatch.setenv("ARENA_USE_MOCK", "1")
    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(
        service,
        "battle_update",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )
    monkeypatch.setattr(sandbox_launcher, "NeonBranchManager", Manager)

    try:
        sandbox_launcher.provision_battle_database(battle_id)
    except sandbox_launcher.NeonProvisioningError as exc:
        assert "ARENA_INFRA_FAILURE" in str(exc)
    else:
        raise AssertionError("expected branch handle persistence failure")
    assert deleted == [branch.branch_id]


def test_cancel_path_requests_database_cleanup(monkeypatch):
    from agent_arena import battles, event_bus

    battle_id = "battle-db-cancel"
    battle = {
        "id": battle_id,
        "user_id": "user-a",
        "status": "running",
        "sandbox_id": "sandbox-a",
        "battle_db_branch_id": "br-battle-db-cancel",
    }
    calls: list[tuple] = []
    monkeypatch.setattr(battles, "_require_owned_battle", lambda *_args: battle)
    monkeypatch.setattr(
        service,
        "battle_cancel",
        lambda user_id, bid: calls.append(("cancel", user_id, bid)),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "stop_sandbox",
        lambda sid: calls.append(("stop", sid)),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "cleanup_battle_database",
        lambda bid, **kwargs: calls.append(("cleanup", bid, kwargs)) or True,
    )
    monkeypatch.setattr(event_bus, "publish", lambda *_args: None)

    result = battles.cancel_battle(battle_id, "user-a")

    assert result["status"] == "cancelled"
    assert calls == [
        ("cancel", "user-a", battle_id),
        ("stop", "sandbox-a"),
        ("cleanup", battle_id, {"branch_id": "br-battle-db-cancel"}),
    ]


def test_terminal_internal_finalize_requests_database_cleanup(monkeypatch):
    from agent_arena.internal_router import FinalizeBody, internal_finalize

    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "agent_arena.internal_router._require_battle_token",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "agent_arena.internal_router._rate_limit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "agent_arena.finalization.sandbox_end_finalize",
        lambda *_args, **_kwargs: {
            "ok": True,
            "status": "completed",
            "already_finalized": False,
            "authoritative": True,
        },
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "cleanup_battle_database",
        lambda bid, **_kwargs: cleanup_calls.append(bid) or True,
    )

    result = internal_finalize(
        FinalizeBody(battle_id="battle-db-finalize", status="completed"),
        x_sandbox_token="token",
    )

    assert result["status"] == "completed"
    assert cleanup_calls == ["battle-db-finalize"]


def test_reaper_cleans_persisted_branch_after_timeout(monkeypatch):
    from agent_arena.reaper import _reap_pg

    stale = SimpleNamespace(
        id="battle-db-timeout",
        status="running",
        started_at=datetime.fromtimestamp(100, tz=timezone.utc),
        created_at=datetime.fromtimestamp(100, tz=timezone.utc),
        timeout_seconds=1,
        sandbox_id="sandbox-timeout",
        battle_db_branch_id="br-battle-db-timeout",
    )
    cleanup_calls: list[tuple] = []

    @contextmanager
    def fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr("agent_arena.persistence.session.session_scope", fake_scope)
    monkeypatch.setattr(
        "agent_arena.persistence.repositories.battles.battle_list_active",
        lambda _session, **_kwargs: [stale],
    )
    monkeypatch.setattr(
        "agent_arena.finalization.fail_closed_incomplete",
        lambda *_args, **_kwargs: {
            "ok": True,
            "status": "failed",
            "already_finalized": False,
        },
    )
    monkeypatch.setattr("agent_arena.reaper._stop_sandbox", lambda _sid: None)
    monkeypatch.setattr(
        sandbox_launcher,
        "cleanup_battle_database",
        lambda bid, **kwargs: cleanup_calls.append((bid, kwargs)) or True,
    )

    assert _reap_pg(1_000, 0) == [stale.id]
    assert cleanup_calls == [
        (stale.id, {"branch_id": stale.battle_db_branch_id})
    ]


def test_branch_handle_never_enters_public_battle_payload():
    payload = public_battle_payload(
        {
            "id": "battle-db-public",
            "status": "running",
            "battle_db_branch_id": "br-private",
            "battle_config": {},
        }
    )

    assert "battle_db_branch_id" not in payload


def test_start_battle_fails_closed_before_runner_when_provisioning_fails(
    monkeypatch,
):
    from agent_arena.neon_branch_manager import NeonProvisioningError

    battle_id = "battle-db-provision-failure"
    failures: list[str] = []
    runs: list[str] = []
    cleanups: list[str] = []
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda _bid: (
            None,
            None,
            {"id": battle_id, "target_id": "", "model_ids": []},
            {
                "database": {
                    "required": True,
                    "engine": "postgresql",
                    "application_write": True,
                }
            },
        ),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "provision_battle_database",
        lambda _bid, **_kwargs: (_ for _ in ()).throw(
            NeonProvisioningError("ARENA_INFRA_FAILURE: unavailable")
        ),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "_fail_database_provisioning",
        lambda bid: failures.append(bid),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "run_in_process",
        lambda bid, **_kwargs: runs.append(bid),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "cleanup_battle_database",
        lambda bid, **_kwargs: cleanups.append(bid) or True,
    )

    sandbox_launcher.start_battle(battle_id)

    assert failures == [battle_id]
    assert runs == []
    assert cleanups == []


def test_start_battle_does_not_provision_when_battle_load_fails(monkeypatch):
    battle_id = "battle-db-load-failure"
    provisioned: list[str] = []
    failures: list[tuple[str, str]] = []

    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda _bid: (_ for _ in ()).throw(RuntimeError("missing battle")),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "_fail_with_reason",
        lambda bid, reason: failures.append((bid, reason)),
    )
    monkeypatch.setattr(
        sandbox_launcher,
        "provision_battle_database",
        lambda bid: provisioned.append(bid),
    )

    sandbox_launcher.start_battle(battle_id)

    assert provisioned == []
    assert failures == [(battle_id, sandbox_launcher.BATTLE_LOAD_FAILURE)]
