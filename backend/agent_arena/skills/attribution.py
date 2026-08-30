"""Authoritative skill outcome attribution.

Consumes final authoritative battle results and assigns outcome credit to
successfully loaded skills under valid competitive benchmark conditions.
"""

from __future__ import annotations

from typing import Any

from .canonical import CanonicalSkillResolver

# Terminal outcomes that qualify for competitive learning attribution
LEARNABLE_OUTCOMES = {
    "TEST_PASS",
    "COMPLETED",
    "PASSED",
    "TEST_FAIL",
    "FAILED",
    "STEP_BUDGET_EXCEEDED",
    "MAX_TURNS_EXCEEDED",
    "PARSE_RECOVERY_EXHAUSTED",
}

# Non-learnable failure modes (infrastructure/environment/outage errors)
NON_LEARNABLE_OUTCOMES = {
    "PROVIDER_ERROR",
    "PROVIDER_TIMEOUT",
    "EXECUTOR_CRASH",
    "SANDBOX_ERROR",
    "CANCELLED",
    "INFRASTRUCTURE_FAILURE",
    "VERIFICATION_ERROR",
}


def is_learnable_outcome(outcome: str) -> bool:
    """Determine whether an execution outcome represents valid model performance."""
    norm = str(outcome or "").strip().upper()
    if norm in NON_LEARNABLE_OUTCOMES:
        return False
    if any(err in norm for err in ("PROVIDER", "CRASH", "CANCEL", "SANDBOX", "INFRA")):
        return False
    return True


def compute_skill_attributions(
    results: list[dict[str, Any]],
    *,
    resolver: CanonicalSkillResolver | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Compute per-fighter skill attributions based on authoritative battle results.

    Returns:
        Mapping of role -> list of attribution records:
        [{"skill_id": str, "outcome": "win" | "loss" | "draw", "reason": str}]
    """
    attributions_by_role: dict[str, list[dict[str, Any]]] = {}

    if not results:
        return attributions_by_role

    # Filter for valid learnable results
    learnable_results = [r for r in results if is_learnable_outcome(str(r.get("outcome") or ""))]
    if not learnable_results:
        # Entire battle was infrastructure/unlearnable error -> 0 attribution
        for r in results:
            attributions_by_role[str(r.get("role") or "")] = []
        return attributions_by_role

    # Identify declared winner among passing fighters
    passing_results = [
        r for r in learnable_results
        if r.get("passed") is True and (r.get("policy") or {}).get("status") != "invalid"
    ]

    winner_role: str | None = None
    if passing_results:
        # Declared winner has lowest steps (or first declared pass)
        best = min(passing_results, key=lambda x: int(x.get("steps") or 999))
        winner_role = str(best.get("role") or "")

    for r in results:
        role = str(r.get("role") or "")
        role_outcome = str(r.get("outcome") or "").upper()

        if not is_learnable_outcome(role_outcome):
            attributions_by_role[role] = []
            continue

        is_winner = (winner_role is not None and role == winner_role)
        is_pass = (r.get("passed") is True)

        # Attribute only to skills that were successfully loaded
        # Telemetry / result may store loaded_skill_ids or skill_reads
        loaded_skills = list(
            (r.get("skills_telemetry") or {}).get("loaded_skill_ids")
            or r.get("skill_reads")
            or []
        )
        # Filter out hallucinated or unknown skills
        valid_loaded_ids: list[str] = []
        for s_ref in loaded_skills:
            if resolver:
                canon = resolver.resolve(str(s_ref))
                if canon:
                    valid_loaded_ids.append(canon.id)
            else:
                valid_loaded_ids.append(str(s_ref).strip())

        role_attrs: list[dict[str, Any]] = []
        for skill_id in set(valid_loaded_ids):
            if is_winner:
                attr_outcome = "win"
                reason = "winner_passed"
            elif passing_results and not is_winner:
                attr_outcome = "loss"
                reason = "competitor_won"
            elif not passing_results and not is_pass:
                # All fail race or failed solo
                attr_outcome = "loss"
                reason = "failed_target"
            else:
                attr_outcome = "draw"
                reason = "tied_outcome"

            role_attrs.append({
                "skill_id": skill_id,
                "outcome": attr_outcome,
                "reason": reason,
            })

        attributions_by_role[role] = role_attrs

    return attributions_by_role
