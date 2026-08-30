"""Unit tests for Target Library v1 loader, registry, API, and verification."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

# Verifier runs in-process in unit tests; see test_target_security.py.
os.environ.setdefault("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
from fastapi.testclient import TestClient

from agent_arena.main import app
from agent_arena.target_library import (
    TargetBundle,
    TargetManifestError,
    TargetSecurityError,
    compile_target_to_battle_config,
    get_target_library,
    load_target_bundle,
)
from agent_arena.target_verifier import verify_target_submission

LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "targets" / "library"

EXPECTED_TARGET_IDS = [
    "authentication-gate",
    "broken-package-recovery",
    "makefile-from-hell",
    "migration-disaster",
    "poisoned-instructions",
    "readme-lied",
    "red-herring-repository",
    "session-replay-defense",
    "sql-login-service",
    "tinyshop",
]


def test_registry_discovers_all_ten_targets():
    registry = get_target_library(LIBRARY_ROOT)
    targets = registry.list_targets()
    found_ids = sorted(t.id for t in targets)
    assert found_ids == sorted(EXPECTED_TARGET_IDS), f"Mismatch in loaded targets: {found_ids}"


@pytest.mark.parametrize("target_id", EXPECTED_TARGET_IDS)
def test_target_bundle_integrity(target_id: str):
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target(target_id)
    assert bundle is not None, f"Target '{target_id}' not found"

    assert bundle.id == target_id
    assert bundle.name
    assert bundle.category
    assert bundle.difficulty in ("novice", "general", "advanced", "expert")
    assert bundle.format in ("solo", "builder_breaker", "ctf", "adversarial_agent")
    assert bundle.runtime
    assert bundle.description
    assert bundle.manifest_hash and len(bundle.manifest_hash) == 64
    assert bundle.starter_hash and len(bundle.starter_hash) == 64
    assert bundle.hidden_hash and len(bundle.hidden_hash) == 64

    # Evaluator separation guarantee: starter_files must NEVER contain hidden tests or reference
    for path in bundle.starter_files:
        assert not path.startswith("tests/hidden"), f"Hidden test leaked in starter: {path}"
        assert not path.startswith("reference"), f"Reference leaked in starter: {path}"

    # Builder/Breaker targets must declare handoff_allowlist
    if bundle.format == "builder_breaker":
        assert len(bundle.workspace.handoff_allowlist) > 0, (
            f"Builder/breaker target '{target_id}' must declare handoff_allowlist"
        )


def test_catalog_api_list():
    client = TestClient(app)
    res = client.get("/targets")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 10
    ids = [d["id"] for d in data]
    for exp in EXPECTED_TARGET_IDS:
        assert exp in ids

    # Check public fields
    item = next(d for d in data if d["id"] == "broken-package-recovery")
    assert item["name"] == "Broken Package Recovery"
    assert item["difficulty"] == "novice"
    assert "manifest_hash" in item
    assert "hidden_test_files" not in item
    assert "reference_files" not in item


def test_catalog_api_detail():
    client = TestClient(app)
    res = client.get("/targets/broken-package-recovery")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "broken-package-recovery"
    assert "starter_files" in data
    assert "visible_tests" in data
    assert "objectives" in data
    # Anonymous callers get the public brief only: evaluator-internal fields
    # are present but nulled behind the optional-auth gate.
    assert data["starter_files"] is None
    assert data["visible_tests"] is None
    assert data["protected_paths"] is None
    assert data["handoff_allowlist"] is None
    assert data["limits"] is None
    assert data["safety"] is None
    # Zero evaluator files
    assert "hidden_test_files" not in data
    assert "reference_files" not in data


def test_catalog_api_detail_authenticated_gets_internals():
    from agent_arena.formats import get_optional_user

    client = TestClient(app)
    app.dependency_overrides[get_optional_user] = lambda: "user-test-123"
    try:
        res = client.get("/targets/broken-package-recovery")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["starter_files"], list) and len(data["starter_files"]) > 0
    assert isinstance(data["visible_tests"], list)
    assert isinstance(data["protected_paths"], list)
    assert isinstance(data["handoff_allowlist"], list)
    assert isinstance(data["limits"], dict)
    assert isinstance(data["safety"], dict)


def test_catalog_api_404_for_unknown():
    client = TestClient(app)
    res = client.get("/targets/nonexistent-target-xyz")
    assert res.status_code == 404


def test_compile_target_to_battle_config():
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("authentication-gate")
    assert bundle is not None
    cfg = compile_target_to_battle_config(bundle, arena_size=2)
    assert cfg["id"] == "authentication-gate"
    assert cfg["target_id"] == "authentication-gate"
    assert cfg["target_version"] == "1.0.0"
    assert cfg["manifest_hash"] == bundle.manifest_hash
    assert cfg["roles"] == ["builder", "breaker"]
    assert "builder" in cfg["role_missions"]
    assert "breaker" in cfg["role_missions"]
    assert "TARGET: Authentication Gate" in cfg["target_code"]
    assert "Run visible tests using `TOOL test`" in cfg["target_code"]

    assert "battle_plan" in cfg
    phases = cfg["battle_plan"]["phases"]
    assert len(phases) == 2
    assert phases[0]["actor"] == "builder"
    assert phases[1]["actor"] == "breaker"
    assert phases[1]["handoff_from"] == ["build"]

    # Test solo 1-model and 2-model race compilation
    solo_bundle = registry.get_target("broken-package-recovery")
    assert solo_bundle is not None
    solo_1_cfg = compile_target_to_battle_config(solo_bundle, arena_size=1)
    assert solo_1_cfg["roles"] == ["fighter"]
    assert "fighter" in solo_1_cfg["role_missions"]

    solo_2_cfg = compile_target_to_battle_config(solo_bundle, arena_size=2)
    assert solo_2_cfg["roles"] == ["fighter_1", "fighter_2"]
    assert "fighter_1" in solo_2_cfg["role_missions"]
    assert "fighter_2" in solo_2_cfg["role_missions"]


def test_trusted_verifier_on_reference_solution():
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("readme-lied")
    assert bundle is not None

    # Verifying reference solution passes
    evidence = verify_target_submission(
        bundle,
        bundle.reference_files,
        run_visible=True,
        run_hidden=True,
    )
    assert evidence.passed is True
    assert evidence.visible_passed is True
    assert evidence.hidden_passed is True
    assert evidence.visible_exit_code == 0
    assert evidence.hidden_exit_code == 0


@pytest.mark.integration
def test_target_battle_creation_solo_and_builder_breaker_contracts(client):
    from agent_arena.auth import get_current_user
    from tests.conftest import make_user_id, playable_format_id

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    fmt_id = playable_format_id()
    try:
        # 1. Solo-compatible target with 1 model (Solo mode) -> 201 Created
        resp_solo = client.post("/battles", json={
            "format_id": fmt_id,
            "target_id": "broken-package-recovery",
            "model_ids": ["host:openrouter-free"],
            "arena_size": 1,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp_solo.status_code == 201
        battle_solo = client.get(f"/battles/{resp_solo.json()['id']}").json()
        assert battle_solo["target_id"] == "broken-package-recovery"
        assert len(battle_solo["model_ids"]) == 1

        # 2. Solo-compatible target with 2 models (Race mode) -> 201 Created
        resp_race = client.post("/battles", json={
            "format_id": fmt_id,
            "target_id": "broken-package-recovery",
            "model_ids": ["host:openrouter-free", "host:deepseek-chat"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp_race.status_code == 201
        battle_race = client.get(f"/battles/{resp_race.json()['id']}").json()
        assert battle_race["target_id"] == "broken-package-recovery"
        assert len(battle_race["model_ids"]) == 2

        # 3. Builder/Breaker target with 1 model -> 400 Bad Request (strictly requires 2)
        resp_bb_1 = client.post("/battles", json={
            "format_id": fmt_id,
            "target_id": "authentication-gate",
            "model_ids": ["host:openrouter-free"],
            "arena_size": 1,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp_bb_1.status_code == 400
        assert "must match non-judge roles (2 required, got 1)" in resp_bb_1.json()["detail"]

        # 4. Builder/Breaker target with 2 models -> 201 Created
        resp_bb_2 = client.post("/battles", json={
            "format_id": fmt_id,
            "target_id": "authentication-gate",
            "model_ids": ["host:openrouter-free", "host:deepseek-chat"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp_bb_2.status_code == 201
        battle_bb = client.get(f"/battles/{resp_bb_2.json()['id']}").json()
        assert battle_bb["target_id"] == "authentication-gate"
        assert len(battle_bb["model_ids"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)

