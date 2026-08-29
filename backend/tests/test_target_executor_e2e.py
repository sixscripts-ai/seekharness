"""End-to-end executor integration tests for Target Library bundles, fail-closed policy, asymmetric scoring, and API creation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

# Verifier runs in-process in unit tests; see test_target_security.py.
os.environ.setdefault("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
from fastapi.testclient import TestClient

from agent_arena.custom_battles import is_ranked_battle
from agent_arena.main import app
from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.target_library import compile_target_to_battle_config, get_target_library
from agent_arena.target_verifier import verify_builder_breaker_submission, verify_target_submission

LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "targets" / "library"


def test_executor_runs_target_bundle_with_trusted_verifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("broken-package-recovery")
    assert bundle is not None

    cfg = compile_target_to_battle_config(bundle, arena_size=1)
    assert cfg["target_id"] == "broken-package-recovery"
    assert "battle_plan" in cfg

    transport = FakeTransport()
    # Mock LLM response that writes the reference fix
    package_json_fixed = bundle.reference_files["package.json"].decode("utf-8")
    transport.model_canned = (
        'THOUGHT: Fixing package.json syntax error and test scripts\n'
        'SKILL: test-skill\n'
        'THEORY: Syntax error in package.json trailing comma and missing test script\n'
        f'TOOL write package.json\n{package_json_fixed}\n'
        'TOOL test\n'
    )

    transport.judge_result = {
        "scores": {"test-model-a": 100.0},
        "justifications": {"test-model-a": "pass"},
        "judge_model": "mock",
    }

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-target-battle-1",
        format_config=cfg,
        model_ids=["test-model-a"],
        round_visibility="isolated",
        client=client,
        role_to_model={"fighter": "test-model-a"},
        timeout_seconds=60,
    )

    artifacts = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "TEST_PASS" in artifacts
    assert "broken-package-recovery" in artifacts


def test_executor_fail_closed_on_missing_target(monkeypatch: pytest.MonkeyPatch):
    """When target_id is not in target library, executor MUST fail closed with VERIFY_ERROR."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    cfg = {
        "target_id": "nonexistent-target-library-id",
        "roles": ["fighter"],
        "target_code": "# test task",
    }

    transport = FakeTransport()
    transport.model_canned = "THOUGHT: solving\nTOOL test\n"
    transport.judge_result = {"scores": {"model-a": 0.0}}

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-missing-target",
        format_config=cfg,
        model_ids=["model-a"],
        round_visibility="isolated",
        client=client,
        role_to_model={"fighter": "model-a"},
        timeout_seconds=60,
    )

    artifacts = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "VERIFY_ERROR" in artifacts
    assert "target-verifier-error" in artifacts


def test_executor_fail_closed_on_hash_mismatch(monkeypatch: pytest.MonkeyPatch):
    """When frozen manifest_hash mismatches loaded bundle on disk, fail closed with VERIFY_ERROR."""
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("broken-package-recovery")
    assert bundle is not None

    cfg = compile_target_to_battle_config(bundle, arena_size=1)
    # Corrupt the frozen manifest hash
    cfg["manifest_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"

    transport = FakeTransport()
    transport.model_canned = "THOUGHT: solving\nTOOL test\n"
    transport.judge_result = {"scores": {"model-a": 0.0}}

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-hash-mismatch",
        format_config=cfg,
        model_ids=["model-a"],
        round_visibility="isolated",
        client=client,
        role_to_model={"fighter": "model-a"},
        timeout_seconds=60,
    )

    artifacts = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "VERIFY_ERROR" in artifacts
    assert "target-verifier-error" in artifacts


def test_builder_breaker_asymmetric_scoring():
    """Test asymmetric evaluation of Builder vs Breaker."""
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("authentication-gate")
    assert bundle is not None

    # Case A: Builder writes reference solution, Breaker fails to exploit
    builder_clean_files = bundle.reference_files
    breaker_empty_files = {"exploit.py": "import sys; sys.exit(1)"}

    ev_a = verify_builder_breaker_submission(
        bundle,
        builder_files=builder_clean_files,
        breaker_files=breaker_empty_files,
    )
    assert ev_a.builder_passed is True
    assert ev_a.breaker_passed is False
    assert ev_a.breaker_exploit_passed is False

    # Case B: Builder keeps vulnerable starter app, Breaker writes valid exploit
    builder_vulnerable_files = bundle.starter_files
    breaker_valid_exploit = {
        "exploit.py": (
            "import os, sys\n"
            "# Simulate breaker exploit\n"
            "print('BREAKER_EXPLOIT_SUCCESS')\n"
            "sys.exit(0)\n"
        )
    }
    ev_b = verify_builder_breaker_submission(
        bundle,
        builder_files=builder_vulnerable_files,
        breaker_files=breaker_valid_exploit,
    )
    assert ev_b.breaker_passed is True
    assert ev_b.breaker_exploit_passed is True
    assert ev_b.builder_passed is False


def test_ranking_eligibility_for_target_library():
    """Verified target library battles are ranked eligible, whereas custom unverified drafts are not."""
    # Target battle
    assert is_ranked_battle({"target_id": "broken-package-recovery", "spec_hash": "abc"}) is True
    assert is_ranked_battle({}, {"target_id": "broken-package-recovery"}) is True

    # User custom draft (unverified)
    assert is_ranked_battle({"draft_id": "custom-123", "spec_hash": "xyz"}) is False
    assert is_ranked_battle({"spec_hash": "xyz"}) is False


def _executor_results(rounds):
    found = []
    marker = "EXECUTOR_RESULT:"
    for r in rounds:
        art = r.get("artifact") or ""
        if marker not in art:
            continue
        payload = art.split(marker, 1)[1].strip()
        found.append(json.loads(payload))
    return found


def test_builder_breaker_executor_runs_asymmetric_phases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A builder/breaker battle plan must run two distinct phases and invoke
    verify_builder_breaker_submission (recorded as evidence) rather than the
    single-phase target path.
    """
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    registry = get_target_library(LIBRARY_ROOT)
    bundle = registry.get_target("authentication-gate")
    assert bundle is not None

    cfg = compile_target_to_battle_config(bundle, arena_size=2)
    assert cfg["format"] == "builder_breaker"
    assert [p["actor"] for p in cfg["battle_plan"]["phases"]] == ["builder", "breaker"]

    # Builder writes the reference app.py (passes visible + hidden tests).
    builder_reply = (
        'TOOL write path=app.py\n'
        + bundle.reference_files["app.py"].decode("utf-8")
        + '\nEND_TOOL\nDONE\n'
    )
    # Breaker writes a benign exploit that exits non-zero (fails to exploit).
    breaker_reply = (
        'TOOL write path=exploit.py\n'
        'import sys\nsys.exit(1)\n'
        'END_TOOL\nDONE\n'
    )

    transport = FakeTransport()
    transport.model_replies = {"builder": builder_reply, "breaker": breaker_reply}
    transport.judge_result = {
        "scores": {"builder": 100.0, "breaker": 0.0},
        "justifications": {"builder": "hardened", "breaker": "no exploit"},
        "judge_model": "mock",
    }
    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-bb-battle",
        format_config=cfg,
        model_ids=["builder", "breaker"],
        round_visibility="isolated",
        client=client,
        role_to_model={"builder": "builder", "breaker": "breaker"},
        timeout_seconds=60,
    )

    results = _executor_results(transport.rounds)
    phases = {r.get("phase"): r for r in results}
    assert "build" in phases and "break" in phases
    assert phases["build"]["role"] == "builder"
    assert phases["break"]["role"] == "breaker"

    # Distinct phase artifacts: builder produced app.py, breaker produced
    # exploit.py against the handed-off app.py.
    builder_artifacts = [
        r for r in transport.rounds
        if r.get("event_type") == "artifact" and r.get("model_id") == "builder"
    ]
    breaker_artifacts = [
        r for r in transport.rounds
        if r.get("event_type") == "artifact" and r.get("model_id") == "breaker"
    ]
    assert builder_artifacts and breaker_artifacts
    builder_files = None
    breaker_files = None
    for r in builder_artifacts:
        art = r.get("artifact") or ""
        if not art.strip().startswith("{"):
            continue
        try:
            payload = json.loads(art)
        except Exception:
            continue
        if "files" in payload and "app.py" in payload["files"]:
            builder_files = payload["files"]
            break
    for r in breaker_artifacts:
        art = r.get("artifact") or ""
        if not art.strip().startswith("{"):
            continue
        try:
            payload = json.loads(art)
        except Exception:
            continue
        if "files" in payload and "exploit.py" in payload["files"]:
            breaker_files = payload["files"]
            break
    assert builder_files is not None
    assert breaker_files is not None
    assert "exploit.py" not in (builder_files or {})
    assert "exploit.py" in breaker_files
    # The breaker received the builder's hardened app.py via handoff.
    assert "app.py" in breaker_files

    # verify_builder_breaker_submission must have been invoked and recorded:
    # each phase result carries the asymmetric evidence and the per-role verdict.
    build_result = phases["build"]
    break_result = phases["break"]
    assert "builder_breaker_verification" in build_result
    assert "builder_breaker_verification" in break_result
    bb_evidence = build_result["builder_breaker_verification"]
    assert bb_evidence is not None
    assert bb_evidence["builder_passed"] is True
    assert bb_evidence["breaker_passed"] is False
    assert bb_evidence["breaker_exploit_passed"] is False
    # The per-role outcomes reflect the asymmetric verdict.
    assert build_result["passed"] is True
    assert break_result["passed"] is False
