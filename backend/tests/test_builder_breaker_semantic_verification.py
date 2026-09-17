"""Fail-closed semantic verification for Builder/Breaker Targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_arena.target_library import load_target_bundle
from agent_arena.target_verifier import (
    TrustedBreakerSemanticEvidence,
    verify_builder_breaker_submission,
)
from agent_arena.finalization import _merge_trusted_authority
from tests.eval_fixtures import point_evaluators, write_builder_breaker_reference_target


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    library = tmp_path / "library"
    evaluators = tmp_path / "evaluators"
    target = write_builder_breaker_reference_target(library, evaluators)
    point_evaluators(monkeypatch, evaluators)
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    return load_target_bundle(target)


@pytest.mark.parametrize(
    ("breaker_files", "expected_artifact_status"),
    [
        ({}, "no_breaker_artifact"),
        ({"notes.txt": "no entrypoint"}, "missing_exploit_entrypoint"),
        ({"exploit.py": b"\xff"}, "malformed_breaker_artifact"),
        ({"exploit.py": ""}, "malformed_breaker_artifact"),
        ({"exploit.js": ""}, "malformed_breaker_artifact"),
    ],
)
def test_missing_or_malformed_breaker_artifact_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    breaker_files: dict[str, str | bytes],
    expected_artifact_status: str,
):
    bundle = _bundle(tmp_path, monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle, bundle.reference_files, breaker_files, trusted_host=True
    )

    assert evidence.breaker_passed is False
    assert evidence.breaker_exploit_passed is False
    assert evidence.breaker_semantic_evidence["artifact_status"] == expected_artifact_status
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False


@pytest.mark.parametrize(
    "exploit_source",
    [
        "import sys; sys.exit(0)\n",
        "print('BREAKER_EXPLOIT_SUCCESS')\n",
        "import sys; print('FLAG{attacker-claim}', file=sys.stderr); sys.exit(7)\n",
        "print('{\"success\": true, \"trusted_condition_passed\": true}')\n",
    ],
)
def test_untrusted_process_status_and_markers_are_not_semantic_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exploit_source: str
):
    bundle = _bundle(tmp_path, monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        bundle.reference_files,
        {"exploit.py": exploit_source},
        trusted_host=True,
    )

    assert evidence.breaker_semantic_evidence["execution_started"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is False
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False
    assert evidence.breaker_passed is False


def test_failed_private_harness_marker_cannot_become_breaker_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, monkeypatch)
    harness = (
        tmp_path
        / "evaluators"
        / bundle.id
        / "tests"
        / "breaker_harness.py"
    )
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(
        "def test_private_harness():\n"
        "    assert False, 'FLAG{marker-in-trusted-error-output}'\n",
        encoding="utf-8",
    )
    bundle = load_target_bundle(tmp_path / "library" / bundle.id)

    evidence = verify_builder_breaker_submission(
        bundle, bundle.reference_files, {}, trusted_host=True
    )

    assert evidence.breaker_passed is False
    assert evidence.breaker_exploit_passed is False


def test_trusted_semantic_postcondition_is_the_only_breaker_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        bundle.starter_files,
        {"exploit.py": "import sys; sys.exit(7)\n"},
        trusted_host=True,
        trusted_semantic_evidence=TrustedBreakerSemanticEvidence(
            condition_checked=True,
            condition_passed=True,
            evidence_ids=("trusted:synthetic-bb-reference:postcondition:1",),
            findings=("unauthorized_mutation",),
        ),
    )

    assert evidence.breaker_passed is True
    assert evidence.breaker_exploit_passed is True
    assert evidence.breaker_semantic_evidence["process_return_code"] == 7
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is True
    assert evidence.unauthorized_mutation is True


def test_semantic_evidence_error_is_infrastructure_failure_not_breaker_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        bundle.reference_files,
        {"exploit.py": "print('FLAG{attacker-claim}')\n"},
        trusted_host=True,
        trusted_semantic_evidence=TrustedBreakerSemanticEvidence(
            verifier_error="trusted evaluator unavailable"
        ),
    )

    assert evidence.breaker_passed is False
    assert evidence.builder_passed is False
    assert evidence.verification_status == "infra_failure"
    assert evidence.breaker_semantic_evidence["verifier_error"]


def test_no_breaker_artifact_cannot_be_repaired_by_trusted_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _bundle(tmp_path, monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        bundle.reference_files,
        {},
        trusted_host=True,
        trusted_semantic_evidence=TrustedBreakerSemanticEvidence(
            condition_checked=True,
            condition_passed=True,
            evidence_ids=("trusted:synthetic-bb-reference:postcondition:1",),
            findings=("flag_captured",),
        ),
    )

    assert evidence.breaker_passed is False
    assert evidence.breaker_semantic_evidence["artifact_status"] == "no_breaker_artifact"
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False


def test_finalizer_does_not_promote_breaker_flag_without_semantic_evidence():
    telemetry = [{"phase": "main", "role": "breaker", "model_id": "m1"}]
    forged = [{
        "kind": "builder_breaker",
        "phase": "main",
        "role": "breaker",
        "model_id": "m1",
        "breaker_passed": True,
        "verification_status": "verified_pass",
    }]

    merged = _merge_trusted_authority(telemetry, forged, require_trusted=True)

    assert merged[0]["passed"] is False
    assert merged[0]["verification_status"] == "verified_fail"
