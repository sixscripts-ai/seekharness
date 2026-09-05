"""Findings ingest at the Evidence seam.

Findings are Evidence, never Official Result. Severity must not change
passed, score, or winner. Missing findings.v1.json is absent, not incomplete.
Tests put findings.v1.json in EXECUTOR_RESULT files — the existing ingest path.
"""

from __future__ import annotations

import json

from agent_arena import evidence, scoring

FINDINGS_FILE = "findings.v1.json"
SECRET_MARKER = "sk-abcdefghijklmnopqrstuvwxyz012345"


def _finding(**overrides) -> dict:
    item = {
        "id": "f-001",
        "domain": "auth",
        "severity": "high",
        "title": "Admin route skips session gate",
        "witness": "GET /admin returns 200 without a session cookie",
        "affected_files": ["src/admin.py"],
        "confidence": 0.8,
        "remediation": "Require an authenticated session before /admin.",
    }
    item.update(overrides)
    return item


def _envelope(findings: list[dict]) -> dict:
    return {"schema": "arena-finding-v1", "findings": findings}


def _executor_result(
    *,
    model_id: str = "m1",
    findings_raw: object | None = ...,
    extra_files: dict | None = None,
    exploit_evidence: dict | None = None,
) -> dict:
    files = {"solution.py": "print('ok')"}
    if extra_files:
        files.update(extra_files)
    if findings_raw is not ...:
        if isinstance(findings_raw, (dict, list)):
            files[FINDINGS_FILE] = json.dumps(findings_raw)
        else:
            files[FINDINGS_FILE] = findings_raw
    result = {
        "model_id": model_id,
        "role": "player_a",
        "phase": "race",
        "outcome": "TEST_PASS",
        "passed": True,
        "steps": 4,
        "tests": {"passed": 3, "total": 3},
        "files": files,
        "artifact_checks": {"present": ["solution.py"], "missing": []},
    }
    if exploit_evidence is not None:
        result["exploit_evidence"] = exploit_evidence
    return result


def _phase(result: dict) -> dict:
    return evidence.build_phase_result(result, {})


def _battle(*results: dict):
    summary = evidence.build_battle_evidence("b-findings", list(results), {})
    decision = scoring.decide_winner(summary, {})
    return summary, decision, scoring.deterministic_scores(decision)


def test_valid_findings_file_attaches_projected_facts():
    result = _executor_result(findings_raw=_envelope([_finding()]))
    phase = _phase(result)

    assert phase["findings_ingest"] == "valid"
    assert len(phase["findings"]) == 1
    finding = phase["findings"][0]
    assert finding["id"] == "f-001"
    assert finding["domain"] == "auth"
    assert finding["severity"] == "high"
    assert finding["title"] == "Admin route skips session gate"
    assert finding["witness"]
    assert finding["affected_files"] == ["src/admin.py"]
    assert finding["confidence"] == 0.8
    assert finding["remediation"]
    assert evidence.EVIDENCE_SCHEMA_VERSION == 1


def test_missing_findings_file_is_absent_not_incomplete():
    a = _executor_result(model_id="A")
    b = _executor_result(model_id="B")
    assert FINDINGS_FILE not in a["files"]

    summary, decision, scores = _battle(a, b)
    phase = summary["fighters"][0]["phases"]["race"]

    assert phase["findings_ingest"] == "absent"
    assert phase["findings"] == []
    assert phase["status"] == "completed"
    assert decision["reason"] != "incomplete_evidence"
    assert decision["winner"] in {"A", "B"} or decision["tie"] is True
    assert scores is not None


def test_invalid_json_unknown_severity_and_missing_witness_are_invalid():
    complete = _executor_result()
    baseline = _phase(complete)

    cases = (
        "{not-json",
        _envelope([_finding(severity="urgent")]),
        _envelope([_finding(witness="")]),
        _envelope([_finding(witness=None)]),
    )
    for raw in cases:
        phase = _phase(_executor_result(findings_raw=raw))
        assert phase["findings_ingest"] == "invalid"
        assert phase["findings"] == []
        assert phase["status"] == baseline["status"]
        assert phase["correctness"] == baseline["correctness"]
        assert phase["execution"]["steps"] == baseline["execution"]["steps"]
        assert phase["policy"] == baseline["policy"]
        assert phase["exploit_evidence"] == baseline["exploit_evidence"]


def test_hidden_evaluator_paths_are_stripped_from_projected_files():
    result = _executor_result(
        findings_raw=_envelope(
            [
                _finding(
                    affected_files=[
                        "src/admin.py",
                        "tests/hidden/test_flag.py",
                        "evaluators/hidden_eval.py",
                        "targets/evaluators/demo/tests/hidden/x.py",
                        "reference/SECRET_REF.txt",
                        "targets/library/tinyshop/reference/solver.py",
                        "docs/reference/overview.md",
                    ]
                )
            ]
        )
    )
    finding = _phase(result)["findings"][0]
    assert finding["affected_files"] == ["src/admin.py"]
    joined = " ".join(finding["affected_files"])
    assert "tests/hidden" not in joined
    assert "evaluators/" not in joined
    assert "reference/" not in joined
    assert "targets/library/tinyshop/reference/solver.py" not in finding["affected_files"]
    assert "docs/reference/overview.md" not in finding["affected_files"]


def test_secret_like_values_in_witness_and_remediation_are_redacted():
    result = _executor_result(
        findings_raw=_envelope(
            [
                _finding(
                    witness=f"token leaked as {SECRET_MARKER}",
                    remediation=f"rotate {SECRET_MARKER} and store in the backend vault",
                )
            ]
        )
    )
    finding = _phase(result)["findings"][0]
    assert SECRET_MARKER not in finding["witness"]
    assert SECRET_MARKER not in finding["remediation"]
    assert "[REDACTED]" in finding["witness"]
    assert "[REDACTED]" in finding["remediation"]


def test_official_result_keys_are_dropped_from_projected_finding():
    raw = _finding()
    raw["passed"] = True
    raw["score"] = 99
    raw["winner"] = "m1"
    raw["official_result"] = {"winner": "m1"}
    phase = _phase(_executor_result(findings_raw=_envelope([raw])))
    finding = phase["findings"][0]
    assert "passed" not in finding
    assert "score" not in finding
    assert "winner" not in finding
    assert "official_result" not in finding


def test_critical_finding_does_not_change_winner_or_scores():
    clean = _executor_result(model_id="A")
    dirty = _executor_result(
        model_id="A",
        findings_raw=_envelope(
            [_finding(severity="critical", title="Critical auth bypass")]
        ),
    )
    opponent = _executor_result(model_id="B", findings_raw=...)

    clean_summary, clean_decision, clean_scores = _battle(clean, opponent)
    dirty_summary, dirty_decision, dirty_scores = _battle(dirty, opponent)

    dirty_phase = dirty_summary["fighters"][0]["phases"]["race"]
    clean_phase = clean_summary["fighters"][0]["phases"]["race"]
    assert dirty_phase["findings_ingest"] == "valid"
    assert dirty_phase["findings"][0]["severity"] == "critical"
    assert clean_phase["findings_ingest"] == "absent"
    assert scoring.compare_phase_result(clean_phase, dirty_phase) == 0
    assert clean_decision["winner"] == dirty_decision["winner"]
    assert clean_decision["reason"] == dirty_decision["reason"]
    assert clean_scores == dirty_scores
    assert dirty_phase["correctness"] == clean_phase["correctness"]


def test_findings_do_not_populate_exploit_evidence():
    result = _executor_result(
        findings_raw=_envelope(
            [
                _finding(
                    domain="sandbox",
                    severity="critical",
                    title="Sandbox crash claim",
                    witness="process exited after a synthetic marker",
                    remediation="Harden the sandbox boundary.",
                )
            ]
        )
    )
    phase = _phase(result)
    assert phase["findings_ingest"] == "valid"
    assert phase["exploit_evidence"] == {
        "server_crashed": False,
        "availability_degraded": False,
        "unauthorized_mutation": False,
        "flag_captured": False,
    }

    already = _executor_result(
        findings_raw=_envelope([_finding()]),
        exploit_evidence={"flag_captured": True},
    )
    already_phase = _phase(already)
    assert already_phase["exploit_evidence"]["flag_captured"] is True
    assert already_phase["findings_ingest"] == "valid"
