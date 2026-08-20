"""Versioned battle evidence: structured facts derived from EXECUTOR_RESULT records.

Sits between the raw event journal (battle_events/rounds) and the deterministic
scorer. This module only derives facts - it never interprets quality. Missing
evidence yields status "incomplete"; consumers must never fabricate zeros.

The schema is versioned from day one so historical battles can be re-scored
after a scoring bug fix without rerunning them.
"""

from __future__ import annotations

EVIDENCE_SCHEMA_VERSION = 1
SCORING_VERSION = "arena-score-v1"

POLICY_CLEAN = "clean"
POLICY_WARNING = "warning"
POLICY_INVALID = "invalid"

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


def phase_status(outcome: str | None) -> str:
    """Map an executor outcome marker to a lifecycle status."""
    out = (outcome or "").upper()
    if out in ("TEST_PASS", "TEST_FAIL"):
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
    if isinstance(tests, dict) and "total" in tests:
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

    return {
        "phase_id": str(result.get("phase") or _DEFAULT_PHASE),
        "phase_type": str(result.get("phase_type") or "race"),
        "actor": result.get("role"),
        "status": status,
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
