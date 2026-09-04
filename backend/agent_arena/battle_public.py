"""Owner/browser-safe battle payloads.

Trusted-backend fields (hidden_command, hidden_hash, hidden test output)
stay on the host. GET /battles and SSE must never echo them.
"""

from __future__ import annotations

import copy
from typing import Any

from .target_library import fighter_visible_battle_config

EVALUATOR_PRIVATE_KEYS = frozenset(
    {
        "hidden_command",
        "hidden_hash",
        "hidden_test_files",
        "hidden_output",
        "hidden_passed",
        "hidden_exit_code",
        "reference_files",
        "private_fixture_files",
    }
)

VERIFIED_PASS = "verified_pass"
VERIFIED_FAIL = "verified_fail"
NOT_ATTEMPTED = "not_attempted"
INFRA_FAILURE = "infra_failure"
UNVERIFIED = "unverified"


def scrub_evaluator_private(value: Any) -> Any:
    """Recursively drop evaluator-private keys and never invent replacements."""
    if isinstance(value, dict):
        return {
            key: scrub_evaluator_private(item)
            for key, item in value.items()
            if key not in EVALUATOR_PRIVATE_KEYS
        }
    if isinstance(value, list):
        return [scrub_evaluator_private(item) for item in value]
    return value


def public_sse_payload(event: dict) -> dict:
    """Scrubbed SSE data plus envelope ids needed for reconnect dedupe.

    `event_id`, `created_at`, and `ts` are telemetry metadata, not evaluator
    private material. Hidden evaluator fields stay stripped.
    """
    raw = event.get("data", {})
    payload = scrub_evaluator_private(raw)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    else:
        payload = dict(payload)
    for key in ("event_id", "created_at", "ts"):
        value = event.get(key)
        if value is not None and value != "":
            payload[key] = value
    return payload


def owner_visible_battle_config(cfg: dict | None) -> dict:
    """Public mission config for owner/browser clients."""
    return scrub_evaluator_private(fighter_visible_battle_config(cfg))


def aggregate_verification_status(results: list[dict] | None) -> str:
    statuses = [
        str(row.get("verification_status") or UNVERIFIED)
        for row in (results or [])
    ]
    if not statuses:
        return UNVERIFIED
    if any(status == INFRA_FAILURE for status in statuses):
        return INFRA_FAILURE
    if any(status == VERIFIED_PASS for status in statuses):
        return VERIFIED_PASS
    if any(status == VERIFIED_FAIL for status in statuses):
        return VERIFIED_FAIL
    if all(status == NOT_ATTEMPTED for status in statuses):
        return NOT_ATTEMPTED
    if any(status == NOT_ATTEMPTED for status in statuses):
        return NOT_ATTEMPTED
    return UNVERIFIED


def verified_solution_from_results(results: list[dict] | None) -> bool:
    return any(
        str(row.get("verification_status") or "") == VERIFIED_PASS
        and bool(row.get("passed"))
        for row in (results or [])
    )


def public_winner(*, verified_solution: bool, results: list[dict] | None) -> str | None:
    """Competitive winner only when trusted verification produced a pass."""
    if not verified_solution:
        return None
    passed = [
        row
        for row in (results or [])
        if str(row.get("verification_status") or "") == VERIFIED_PASS
        and bool(row.get("passed"))
        and str(row.get("model_id") or "")
    ]
    if len(passed) == 1:
        return str(passed[0]["model_id"])
    if not passed:
        return None
    return str(
        max(passed, key=lambda row: float(row.get("score") or 0.0))["model_id"]
    )


def public_scores(score_rows: list[dict] | None, results: list[dict] | None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in score_rows or []:
        mid = str(row.get("model_id") or "")
        if mid:
            scores[mid] = float(row.get("score") or 0.0)
    if scores:
        return scores
    for row in results or []:
        mid = str(row.get("model_id") or "")
        if mid:
            scores[mid] = float(row.get("score") or 0.0)
    return scores


def public_termination_reason(results: list[dict] | None) -> str | None:
    for row in results or []:
        hint = (
            row.get("executor_outcome")
            or row.get("termination_reason")
            or row.get("terminal_reason")
            or row.get("outcome")
        )
        if hint:
            return str(hint)
    return None


def public_battle_payload(
    battle: dict,
    *,
    results: list[dict] | None = None,
    score_rows: list[dict] | None = None,
) -> dict:
    """Owner/browser GET view: sanitized config plus authoritative result fields."""
    payload = scrub_evaluator_private(copy.deepcopy(battle or {}))
    payload.pop("encrypted_key", None)
    cfg = payload.get("battle_config")
    if isinstance(cfg, dict):
        payload["battle_config"] = owner_visible_battle_config(cfg)

    result_rows = list(results or [])
    scores = public_scores(score_rows, result_rows)
    verified = verified_solution_from_results(result_rows)
    status = aggregate_verification_status(result_rows) if result_rows else UNVERIFIED
    if result_rows or scores:
        payload["scores"] = scores
        payload["verified_solution"] = verified
        payload["verification_status"] = status
        payload["winner"] = public_winner(
            verified_solution=verified, results=result_rows
        )
        term = public_termination_reason(result_rows)
        if term:
            payload["termination_reason"] = term
            payload["outcome"] = term
        payload["results"] = [
            {
                "model_id": str(row.get("model_id") or ""),
                "phase": str(row.get("phase") or ""),
                "role": str(row.get("role") or ""),
                "passed": bool(row.get("passed")),
                "score": float(row.get("score") or 0.0),
                "verification_status": str(row.get("verification_status") or UNVERIFIED),
                "termination_reason": row.get("termination_reason")
                or row.get("executor_outcome")
                or row.get("outcome"),
            }
            for row in result_rows
            if str(row.get("model_id") or "")
        ]
    return payload


def public_verification_event_data(record: dict) -> dict:
    """SSE payload for owners: status only, no hidden command/output."""
    status = str(record.get("verification_status") or "")
    if not status:
        if record.get("attempted") is False:
            status = NOT_ATTEMPTED
        elif record.get("passed"):
            status = VERIFIED_PASS
        else:
            status = VERIFIED_FAIL
    data = {
        "authoritative": True,
        "source": "trusted_verifier",
        "verification_status": status,
        "attempted": status not in {NOT_ATTEMPTED, UNVERIFIED},
        "passed": bool(record.get("passed")) and status == VERIFIED_PASS,
        "outcome": str(record.get("outcome") or ""),
        "model_id": str(record.get("model_id") or ""),
        "role": str(record.get("role") or ""),
        "phase": str(record.get("phase") or ""),
        "target_id": str(record.get("target_id") or ""),
    }
    if record.get("executor_outcome"):
        data["executor_outcome"] = str(record.get("executor_outcome"))
    if record.get("visible_passed") is not None:
        data["visible_passed"] = bool(record.get("visible_passed"))
    return scrub_evaluator_private(data)
