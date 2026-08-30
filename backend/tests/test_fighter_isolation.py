"""Fighter code must never run on a host that can read evaluator material.

`ARENA_EVALUATOR_DIR` being stripped from a child environment is not isolation:
the mount stays readable by its well-known path. These tests pin the runner
*selection* boundary and the Modal storage architecture that backs it.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from agent_arena import mock_runner, sandbox_launcher
from agent_arena.fighter_isolation import (
    FighterIsolationError,
    assert_isolated_fighter_execution,
    battle_target_id,
    isolation_required,
)
from agent_arena import target_library
from agent_arena.target_library import private_evaluator_storage_present
from tests.eval_fixtures import point_evaluators, write_private_evaluator

REPO_ROOT = Path(__file__).resolve().parents[2]
MODAL_ENTRY = REPO_ROOT / "backend" / "modal_entry.py"
EVALUATOR_MOUNT = "/opt/arena-evaluators"


def _hide_production_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    missing = tmp_path / "no-production-evaluators"
    monkeypatch.setattr(target_library, "PRODUCTION_EVALUATOR_MOUNT", missing)
    return missing


def _mount_evaluators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _hide_production_mount(tmp_path, monkeypatch)
    eval_root = tmp_path / "evaluators"
    write_private_evaluator(eval_root, "iso-target")
    point_evaluators(monkeypatch, eval_root)
    return eval_root


def _mount_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _hide_production_mount(tmp_path, monkeypatch)
    eval_root = tmp_path / "empty-evaluators"
    eval_root.mkdir(parents=True, exist_ok=True)
    (eval_root / ".gitkeep").write_text("", encoding="utf-8")
    point_evaluators(monkeypatch, eval_root)
    return eval_root


# ---------------------------------------------------------------------------
# storage detection
# ---------------------------------------------------------------------------


def test_storage_presence_requires_an_actual_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_nothing(tmp_path, monkeypatch)
    assert private_evaluator_storage_present() is False

    _mount_evaluators(tmp_path, monkeypatch)
    assert private_evaluator_storage_present() is True


def test_empty_env_override_cannot_hide_production_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    empty = tmp_path / "empty-override"
    empty.mkdir()
    prod = tmp_path / "opt-arena-evaluators"
    prod.mkdir()
    (prod / "iso-target").mkdir()
    point_evaluators(monkeypatch, empty)
    monkeypatch.setattr(target_library, "PRODUCTION_EVALUATOR_MOUNT", prod)
    assert private_evaluator_storage_present() is True


def test_production_mount_directory_is_present_even_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    empty = tmp_path / "empty-override"
    empty.mkdir()
    prod = tmp_path / "opt-arena-evaluators"
    prod.mkdir()
    point_evaluators(monkeypatch, empty)
    monkeypatch.setattr(target_library, "PRODUCTION_EVALUATOR_MOUNT", prod)
    assert private_evaluator_storage_present() is True


def test_unreadable_configured_evaluator_root_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    locked = tmp_path / "locked-evaluators"
    locked.mkdir()
    point_evaluators(monkeypatch, locked)
    monkeypatch.setattr(
        target_library, "PRODUCTION_EVALUATOR_MOUNT", tmp_path / "no-prod"
    )

    monkeypatch.setattr(
        target_library, "_root_has_evaluator_packages", lambda root: None
    )
    assert private_evaluator_storage_present() is True


def test_battle_target_id_prefers_battle_then_config():
    assert battle_target_id({"target_id": "a"}, {"target_id": "b"}) == "a"
    assert battle_target_id({}, {"target_id": "b"}) == "b"
    assert battle_target_id({}, {}) == ""
    assert battle_target_id(None, None) == ""


def test_isolation_required_only_for_target_battles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_evaluators(tmp_path, monkeypatch)
    assert isolation_required("iso-target") is True
    assert isolation_required("") is False


# ---------------------------------------------------------------------------
# runner selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["in_process", "mock"])
def test_same_host_modes_rejected_when_evaluators_mounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
):
    _mount_evaluators(tmp_path, monkeypatch)
    with pytest.raises(FighterIsolationError):
        assert_isolated_fighter_execution("iso-target", mode=mode)


def test_sandbox_mode_and_non_target_battles_are_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_evaluators(tmp_path, monkeypatch)
    assert assert_isolated_fighter_execution("iso-target", mode="sandbox") is None
    assert assert_isolated_fighter_execution("", mode="in_process") is None


def test_in_process_allowed_without_evaluator_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_nothing(tmp_path, monkeypatch)
    assert assert_isolated_fighter_execution("iso-target", mode="in_process") is None


def test_run_in_process_refuses_target_battle_with_evaluator_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression: a private evaluator mount cannot fall back to in-process."""
    _mount_evaluators(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda battle_id: (None, None, {"target_id": "iso-target"}, {}),
    )
    ran: list = []
    monkeypatch.setattr(
        sandbox_launcher, "run_battle_loop", lambda *a, **k: ran.append("loop")
    )
    failures: list[tuple[str, str]] = []
    monkeypatch.setattr(
        sandbox_launcher,
        "_fail_with_reason",
        lambda battle_id, reason: failures.append((battle_id, reason)),
    )

    sandbox_launcher.run_in_process("battle-iso-1")

    assert ran == []
    assert failures and failures[0][0] == "battle-iso-1"
    assert "private evaluator storage" in failures[0][1]


def test_start_battle_does_not_degrade_to_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_evaluators(tmp_path, monkeypatch)
    monkeypatch.setenv("ARENA_USE_MODAL_SANDBOX", "0")
    monkeypatch.setattr(
        sandbox_launcher,
        "_load_battle",
        lambda battle_id: (None, None, {"target_id": "iso-target"}, {}),
    )
    ran: list[str] = []
    monkeypatch.setattr(
        sandbox_launcher, "run_in_process", lambda battle_id: ran.append(battle_id)
    )
    failures: list[str] = []
    monkeypatch.setattr(
        sandbox_launcher,
        "_fail_with_reason",
        lambda battle_id, reason: failures.append(reason),
    )

    sandbox_launcher.start_battle("battle-iso-2")

    assert ran == []
    assert failures and "isolated sandbox" in failures[0]


def test_mock_runner_refuses_target_battle_with_evaluator_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _mount_evaluators(tmp_path, monkeypatch)
    from agent_arena import custom_battles
    from agent_arena.persistence import service

    battle = {
        "id": "battle-iso-3",
        "status": "queued",
        "format_id": "fmt-1",
        "model_ids": ["model-a"],
        "target_id": "iso-target",
    }
    updates: list[dict] = []
    rounds: list = []
    monkeypatch.setattr(service, "battle_get", lambda *a, **k: dict(battle))
    monkeypatch.setattr(service, "format_get", lambda *a, **k: {"config": {}})
    monkeypatch.setattr(
        service, "battle_update", lambda battle_id, payload: updates.append(payload)
    )
    monkeypatch.setattr(service, "round_create", lambda *a, **k: rounds.append(a))
    monkeypatch.setattr(
        custom_battles,
        "resolve_battle_config",
        lambda *a, **k: {"target_id": "iso-target", "roles": ["fighter"]},
    )

    mock_runner.run_battle("battle-iso-3")

    assert rounds == []
    failed = [u for u in updates if u.get("status") == "failed"]
    assert failed, updates
    assert "private evaluator storage" in str(failed[0].get("failure_reason", ""))


# ---------------------------------------------------------------------------
# Modal storage architecture
# ---------------------------------------------------------------------------


def test_modal_backend_mounts_evaluator_volume_read_only():
    source = MODAL_ENTRY.read_text(encoding="utf-8")

    # No image baking of the deployer's local private evaluator tree.
    assert "_EVALUATORS_DIR" not in source
    for line in source.splitlines():
        if "add_local_dir" in line:
            assert "evaluator" not in line.lower(), line

    assert 'modal.Volume.from_name(' in source
    assert "create_if_missing=False" in source
    assert "volumes={EVALUATOR_MOUNT_PATH: evaluator_volume.read_only()}" in source
    assert f'EVALUATOR_MOUNT_PATH = "{EVALUATOR_MOUNT}"' in source
    assert '"ARENA_EVALUATOR_DIR": EVALUATOR_MOUNT_PATH' in source
    assert "materialize_fighter_visible_library" in source
    assert "add_local_dir(str(_TARGETS_DIR)" not in source
    assert "_PUBLIC_TARGETS_DIR" in source


def test_only_the_trusted_backend_function_receives_the_volume():
    source = MODAL_ENTRY.read_text(encoding="utf-8")
    # One mount, one ARENA_EVALUATOR_DIR assignment: the verification backend.
    assert source.count("evaluator_volume.read_only()") == 1
    assert source.count('"ARENA_EVALUATOR_DIR"') == 1
    # The scheduled reaper must not carry evaluator access.
    reaper = source.split("def reap_stale_battles", 1)[0].rsplit("@app.function", 1)[-1]
    assert "volumes" not in reaper
    assert "ARENA_EVALUATOR_DIR" not in reaper


def test_fighter_sandbox_spawn_has_no_evaluator_mount():
    source = inspect.getsource(sandbox_launcher.try_spawn_modal_sandbox)
    assert "arena-evaluators" not in source
    assert "ARENA_EVALUATOR_DIR" not in source
    assert "volumes" not in source
    # The fighter sandbox receives only the materialized public library
    # and a public-only bootstrap (no hidden_hash / hidden_command).
    assert "materialize_fighter_visible_library" in source
    assert "fighter_visible_battle_config" in source
