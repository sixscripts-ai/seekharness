"""Versioned battle evidence: structured facts derived from EXECUTOR_RESULT records.

Sits between the raw event journal (battle_events/rounds) and the deterministic
scorer. This module only derives facts - it never interprets quality. Missing
evidence yields status "incomplete"; consumers must never fabricate zeros.

The schema is versioned from day one so historical battles can be re-scored
after a scoring bug fix without rerunning them.
"""

from __future__ import annotations

import json

from .redact import redact

EVIDENCE_SCHEMA_VERSION = 1
SCORING_VERSION = "arena-score-v1"

POLICY_CLEAN = "clean"
POLICY_WARNING = "warning"
POLICY_INVALID = "invalid"

FINDINGS_ARTIFACT = "findings.v1.json"
FINDINGS_SCHEMA = "arena-finding-v1"
FINDINGS_INGEST_ABSENT = "absent"
FINDINGS_INGEST_VALID = "valid"
FINDINGS_INGEST_INVALID = "invalid"
FINDING_DOMAINS = frozenset(
    {"auth", "authz", "secrets", "http_api", "sandbox", "dependency"}
)
FINDING_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
FINDING_PUBLIC_FIELDS = (
    "id",
    "domain",
    "severity",
    "title",
    "witness",
    "affected_files",
    "confidence",
    "remediation",
)

_DEFAULT_PHASE = "race"


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float | None = None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_hidden_evaluator_path(path: str) -> bool:
    """True when a path names Hidden Evaluator / reference overlay material."""
    norm = str(path or "").replace("\\", "/").strip()
    while norm.startswith("./"):
        norm = norm[2:]
    lowered = norm.lower()
    parts = [p for p in lowered.split("/") if p]
    if "tests/hidden" in lowered:
        return True
    if "evaluators" in parts:
        return True
    if "reference" in parts:
        return True
    if "hidden_eval" in lowered:
        return True
    return False


def _parse_findings_raw(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _validate_finding(item) -> bool:
    if not isinstance(item, dict):
        return False
    ident = item.get("id")
    if not isinstance(ident, str) or not ident.strip():
        return False
    if item.get("domain") not in FINDING_DOMAINS:
        return False
    if item.get("severity") not in FINDING_SEVERITIES:
        return False
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return False
    witness = item.get("witness")
    if not isinstance(witness, str) or not witness.strip():
        return False
    files = item.get("affected_files")
    if not isinstance(files, list) or not all(isinstance(p, str) for p in files):
        return False
    confidence = item.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return False
    if confidence < 0 or confidence > 1:
        return False
    if not isinstance(item.get("remediation"), str):
        return False
    return True


def _project_finding(item: dict) -> dict:
    affected = [
        path
        for path in item.get("affected_files") or []
        if isinstance(path, str) and not _is_hidden_evaluator_path(path)
    ]
    return {
        "id": str(item["id"]),
        "domain": str(item["domain"]),
        "severity": str(item["severity"]),
        "title": redact(str(item["title"])),
        "witness": redact(str(item["witness"])),
        "affected_files": affected,
        "confidence": float(item["confidence"]),
        "remediation": redact(str(item["remediation"])),
    }


def _attach_findings(result: dict) -> tuple[str, list]:
    """Parse/validate/project findings.v1.json from EXECUTOR_RESULT files."""
    files = result.get("files")
    if not isinstance(files, dict) or FINDINGS_ARTIFACT not in files:
        return FINDINGS_INGEST_ABSENT, []
    parsed = _parse_findings_raw(files.get(FINDINGS_ARTIFACT))
    if not isinstance(parsed, dict):
        return FINDINGS_INGEST_INVALID, []
    if parsed.get("schema") != FINDINGS_SCHEMA:
        return FINDINGS_INGEST_INVALID, []
    items = parsed.get("findings")
    if not isinstance(items, list):
        return FINDINGS_INGEST_INVALID, []
    projected: list[dict] = []
    for item in items:
        if not _validate_finding(item):
            return FINDINGS_INGEST_INVALID, []
        projected.append(_project_finding(item))
    return FINDINGS_INGEST_VALID, projected


def phase_status(outcome: str | None) -> str:
    """Map an executor outcome marker to a lifecycle status."""
    out = (outcome or "").upper()
    if out in (
        "TEST_PASS",
        "TEST_FAIL",
        "JUDGE_ONLY",
        "UNTRUSTED_EXECUTION",
        "COMPLETED",
        "VERIFICATION_NOT_ATTEMPTED",
    ):
        return "completed"
    if "BUDGET" in out or "TIMEOUT" in out:
        return "timeout"
    if "POLICY" in out:
        return "policy_violation"
    if "CRASH" in out or "ERROR" in out:
        return "crashed"
    return "incomplete"


def build_phase_result(result: dict | None, format_config: dict | None = None) -> dict:
    """Derive one fighter per-phase facts from a single EXECUTOR_RESULT record."""
    result = result or {}
    cfg = format_config or {}
    outcome = str(result.get("outcome") or "")
    status = phase_status(outcome) if outcome else "incomplete"

    tests = result.get("tests")
    passed_value = result.get("passed")
    judge_only = (
        outcome == "JUDGE_ONLY"
        or bool(cfg.get("judge_only"))
        or cfg.get("evaluation_mode") == "quick"
    )
    if judge_only:
        total = None
        passed = None
        failed = None
    elif isinstance(tests, dict) and "total" in tests:
        total = max(_as_int(tests.get("total")), 0)
        passed = min(max(_as_int(tests.get("passed")), 0), total)
        failed = total - passed
    elif isinstance(passed_value, bool) or outcome in ("TEST_PASS", "TEST_FAIL"):
        total = 1
        if isinstance(passed_value, bool):
            passed = 1 if passed_value else 0
        else:
            passed = 1 if outcome == "TEST_PASS" else 0
        failed = total - passed
    else:
        # No trustworthy record that tests actually ran: NEVER fabricate 0/1.
        total = None
        passed = None
        failed = None

    required = list(((cfg.get("artifacts") or {}).get("required")) or [])
    checks = result.get("artifact_checks") or {}
    if isinstance(checks, dict):
        present = [str(r) for r in (checks.get("present") or [])]
        missing = [str(r) for r in (checks.get("missing") or [])]
        check_required = [str(r) for r in (checks.get("required") or [])]
        if check_required:
            required = check_required
    else:
        files = result.get("files") or {}
        fkeys = set(files.keys()) if isinstance(files, dict) else set()
        present = [r for r in required if r in fkeys]
        missing = [r for r in required if r not in fkeys]

    policy = result.get("policy")
    if isinstance(policy, str):
        policy = {"status": policy}
    if not isinstance(policy, dict):
        policy = {}
    if policy:
        pstatus = str(policy.get("status") or "").lower()
        if pstatus not in (POLICY_CLEAN, POLICY_WARNING, POLICY_INVALID):
            # Malformed policy evidence must not read as a verified clean check.
            pstatus = "unknown"
    else:
        # No policy record: boundaries are enforced structurally (path
        # containment, symlink checks, env scrubbing, network gating), so
        # absence is "clean", not "unknown".
        pstatus = POLICY_CLEAN

    exploit_ev = result.get("exploit_evidence") or {}
    if not isinstance(exploit_ev, dict):
        exploit_ev = {}

    server_crashed = bool(exploit_ev.get("server_crashed", result.get("server_crashed", False)))
    availability_degraded = bool(exploit_ev.get("availability_degraded", result.get("availability_degraded", False)))
    unauthorized_mutation = bool(exploit_ev.get("unauthorized_mutation", result.get("unauthorized_mutation", False)))
    flag_captured = bool(exploit_ev.get("flag_captured", result.get("flag_captured", False)))

    deploy_ready = result.get("deployment_ready")
    if deploy_ready is None:
        deploy_ready = True if outcome in ("TEST_PASS", "COMPLETED") else False

    findings_ingest, findings = _attach_findings(result)

    return {
        "phase_id": str(result.get("phase") or _DEFAULT_PHASE),
        "phase_type": str(result.get("phase_type") or "race"),
        "actor": result.get("role"),
        "status": status,
        "deployment": {
            "status": str(result.get("deployment_status") or ("DEPLOY_SUCCESS" if deploy_ready else "DEPLOY_FAILED")),
            "ready": bool(deploy_ready),
            "repaired": bool(result.get("deployment_repaired", False)),
        },
        "exploit_evidence": {
            "server_crashed": server_crashed,
            "availability_degraded": availability_degraded,
            "unauthorized_mutation": unauthorized_mutation,
            "flag_captured": flag_captured,
        },
        "correctness": {
            "passed": passed,
            "failed": failed,
            "total": total,
            "pass_ratio": (round(passed / total, 6) if total else 0.0)
            if total is not None
            else None,
        },
        "artifacts": {"required": required, "present": present, "missing": missing},
        "execution": {
            "turns": _as_int(result.get("turns")),
            "steps": _as_int(result.get("steps")),
            "successful_tools": _as_int(result.get("successful_tools")),
            "tool_errors": _as_int(result.get("tool_errors")),
            "parse_errors": _as_int(result.get("parse_errors")),
            "timeouts": _as_int(result.get("timeouts")),
            "duration_ms": _as_int(result.get("duration_ms")),
        },
        "policy": {
            "status": pstatus,
            "violations": list(policy.get("violations") or [])
            if isinstance(policy.get("violations"), list)
            else [],
        },
        "judge": {
            "quality": _as_float(result.get("judge_quality")),
            "reasoning": str(result.get("judge_reasoning") or ""),
        },
        "outputs": {
            "artifact_refs": list(present),
            "important_files": sorted(
                set(present)
                | set(str(k) for k in ((result.get("files") or {}).keys()))
            ),
        },
        "findings": findings,
        "findings_ingest": findings_ingest,
    }


def build_battle_evidence(
    battle_id: str,
    results: list[dict],
    format_config: dict | None = None,
    judge_scores: dict | None = None,
    judge_justifications: dict | None = None,
    format_id: str = "",
) -> dict:
    """Group raw EXECUTOR_RESULT records into a versioned per-fighter summary."""
    cfg = format_config or {}
    judge_scores = judge_scores or {}
    judge_justifications = judge_justifications or {}
    by_model: dict[str, dict] = {}
    phases_order: list[str] = []
    for r in results or []:
        mid = str(r.get("model_id") or "")
        if not mid:
            continue
        r2 = dict(r)
        r2["judge_quality"] = _as_float(judge_scores.get(mid))
        r2["judge_reasoning"] = judge_justifications.get(mid)
        ph = str(r.get("phase") or _DEFAULT_PHASE)
        if ph not in phases_order:
            phases_order.append(ph)
        slot = by_model.setdefault(mid, {"role": None, "results": {}, "skills": []})
        slot["role"] = r.get("role")
        slot["results"][ph] = r2
        slot["skills"] = list(r.get("chosen_skills") or [])
        slot["skill_read_ok"] = bool(r.get("skill_read_ok"))
    fighters = []
    for mid in sorted(by_model):
        slot = by_model[mid]
        phases = {
            ph: build_phase_result(res, cfg)
            for ph, res in (slot.get("results") or {}).items()
        }
        fighters.append(
            {
                "fighter_id": mid,
                "role": slot.get("role"),
                "phases": phases,
                "telemetry": {
                    "chosen_skills": slot.get("skills") or [],
                    "skill_read_ok": slot.get("skill_read_ok", False),
                },
            }
        )
    executor_versions = {
        _as_int(r.get("executor_version"))
        for r in results or []
        if isinstance(r, dict) and r.get("executor_version") is not None
    }
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scoring_version": SCORING_VERSION,
        "battle_id": battle_id,
        "format_id": format_id,
        # Formats carry no version field today (live docs are seeded
        # out-of-band); recorded as absent rather than invented.
        "format_version": None,
        "executor_version": sorted(executor_versions)[-1] if executor_versions else None,
        "phases": phases_order,
        "fighters": fighters,
    }
