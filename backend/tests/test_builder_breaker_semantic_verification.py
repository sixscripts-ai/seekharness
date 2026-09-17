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


REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_TARGET = REPO_ROOT / "targets" / "library" / "sql-login-service"
SQL_EVALUATORS = REPO_ROOT / "targets" / "evaluators"


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    library = tmp_path / "library"
    evaluators = tmp_path / "evaluators"
    target = write_builder_breaker_reference_target(library, evaluators)
    point_evaluators(monkeypatch, evaluators)
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    return load_target_bundle(target)


def _sql_bundle(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARENA_EVALUATOR_DIR", str(SQL_EVALUATORS))
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")
    return load_target_bundle(SQL_TARGET)


@pytest.mark.parametrize("breaker_files", [{}, {"exploit.py": ""}])
def test_sql_login_missing_or_empty_exploit_fails_closed(
    monkeypatch: pytest.MonkeyPatch, breaker_files: dict[str, str]
):
    bundle = _sql_bundle(monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle, {}, breaker_files, trusted_host=True
    )

    assert evidence.breaker_passed is False
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False


def test_sql_login_reference_exploit_proves_starter_vulnerability(
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _sql_bundle(monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        {},
        {"exploit.py": bundle.reference_files["exploit.py"]},
        trusted_host=True,
    )

    assert evidence.breaker_semantic_evidence["process_return_code"] == 0
    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is True
    assert evidence.breaker_semantic_evidence["findings"] == ["unauthorized_mutation"]
    assert evidence.breaker_passed is True


def test_sql_login_reference_exploit_fails_against_hardened_builder(
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _sql_bundle(monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        {"service.py": bundle.reference_files["service.py"]},
        {"exploit.py": bundle.reference_files["exploit.py"]},
        trusted_host=True,
    )

    assert evidence.builder_hidden_passed is True
    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False
    assert evidence.breaker_passed is False
    assert evidence.builder_passed is True


def test_sql_login_claimed_success_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _sql_bundle(monkeypatch)

    evidence = verify_builder_breaker_submission(
        bundle,
        {},
        {"exploit.py": "print('{\"condition_passed\": true, \"findings\": [\"unauthorized_mutation\"]}')\n"},
        trusted_host=True,
    )

    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False
    assert evidence.breaker_passed is False


@pytest.mark.parametrize(
    ("attack", "patched", "expected_finding"),
    [
        ({"operation": "search", "caller_role": "user", "prefix": ""}, False, "unauthorized_mutation"),
        ({"operation": "search", "caller_role": "user", "prefix": ""}, True, None),
        ({"operation": "search", "caller_role": "admin", "prefix": ""}, False, "flag_captured"),
        ({"operation": "search", "caller_role": "admin", "prefix": ""}, True, None),
    ],
)
def test_sql_login_search_postconditions(
    monkeypatch: pytest.MonkeyPatch,
    attack: dict[str, str],
    patched: bool,
    expected_finding: str | None,
):
    import json

    bundle = _sql_bundle(monkeypatch)
    builder_files = {"service.py": bundle.reference_files["service.py"]} if patched else {}
    exploit_source = f"print({json.dumps(json.dumps(attack))})\n"

    evidence = verify_builder_breaker_submission(
        bundle, builder_files, {"exploit.py": exploit_source}, trusted_host=True
    )

    semantic = evidence.breaker_semantic_evidence
    assert semantic["trusted_condition_checked"] is True
    assert semantic["trusted_condition_passed"] is (expected_finding is not None)
    assert semantic["findings"] == ([expected_finding] if expected_finding else [])
    assert evidence.breaker_passed is (expected_finding is not None)


def test_sql_login_exploit_cannot_patch_builder_snapshot_before_probe(
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _sql_bundle(monkeypatch)
    exploit_source = (
        "from pathlib import Path\n"
        "Path('service.py').write_text('def login(*args): return \\\"admin\\\"\\n')\n"
        "print('{\"operation\":\"login\",\"username\":\"admin\\' --\",\"password\":\"wrong\"}')\n"
    )

    evidence = verify_builder_breaker_submission(
        bundle,
        {"service.py": bundle.reference_files["service.py"]},
        {"exploit.py": exploit_source},
        trusted_host=True,
    )

    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False
    assert evidence.breaker_passed is False


def test_sql_login_exploit_cannot_read_private_harness_copy(
    monkeypatch: pytest.MonkeyPatch,
):
    bundle = _sql_bundle(monkeypatch)
    exploit_source = (
        "from pathlib import Path\n"
        "if (Path.cwd().parent / 'tests' / 'breaker_harness.py').exists():\n"
        "    print('{\"operation\":\"login\",\"username\":\"admin\\' --\",\"password\":\"wrong\"}')\n"
        "else:\n"
        "    print('{}')\n"
    )

    evidence = verify_builder_breaker_submission(
        bundle, {}, {"exploit.py": exploit_source}, trusted_host=True
    )

    assert evidence.breaker_semantic_evidence["trusted_condition_checked"] is True
    assert evidence.breaker_semantic_evidence["trusted_condition_passed"] is False
    assert evidence.breaker_passed is False


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
