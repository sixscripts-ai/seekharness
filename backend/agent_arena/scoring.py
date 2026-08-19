"""Deterministic lexicographic battle scoring.

The model does not decide who won. The executor does not decide who won.
The judge does not decide who won. Evidence produces facts; this module
applies the format rules to those facts; the rating engine records the result.

Tier order (first difference decides):
  1. policy eligibility (invalid => cannot win)
  2. completion status (completed > timeout > crashed > policy_violation > incomplete)
  3. correctness (pass ratio, compared exactly via cross-multiplication)
  4. required-artifact completeness
  5. execution reliability (tool_errors + parse_errors)
  6. efficiency (fewer steps)
  7. judge quality (tie-break only)

Multi-phase formats aggregate phase comparisons with the format scoring_weights
(phase weights multiply phase outcomes only - never prose).
Pure functions: identical input => byte-identical output.
"""

from __future__ import annotations

import functools

_STATUS_RANK = {
    "completed": 0,
    "timeout": 1,
    "crashed": 2,
    "policy_violation": 3,
    "incomplete": 4,
}
_POLICY_RANK = {"clean": 0, "unknown": 1, "warning": 2, "invalid": 3}


def _policy_rank(phase: dict) -> int:
    status = ((phase.get("policy") or {}).get("status") or "clean")
    return _POLICY_RANK.get(status, 0)


def _is_ineligible(phase: dict) -> bool:
    return _policy_rank(phase) >= 3


def _ratio_cmp(a: dict, b: dict) -> int:
    """-1 if a ratio is better, +1 if b, 0 if equal. Exact, no floats."""
    pa, ta = a.get("passed"), a.get("total")
    pb, tb = b.get("passed"), b.get("total")
    if pa is None or ta is None or pb is None or tb is None:
        return 0  # no trustworthy correctness evidence on one side: skip tier
    lhs = pa * tb
    rhs = pb * ta
    return -1 if lhs > rhs else (1 if lhs < rhs else 0)


def compare_phase_result(a: dict, b: dict) -> int:
    """Lexicographic per-phase comparison. -1: a better; +1: b better; 0: tie."""
    a_in = _is_ineligible(a)
    b_in = _is_ineligible(b)
    if a_in or b_in:
        if a_in != b_in:
            return 1 if a_in else -1
    pa, pb = _policy_rank(a), _policy_rank(b)
    if pa != pb:
        return -1 if pa < pb else 1
    ra = _STATUS_RANK.get(a.get("status"), 4)
    rb = _STATUS_RANK.get(b.get("status"), 4)
    if ra != rb:
        return -1 if ra < rb else 1
    c = _ratio_cmp(a.get("correctness") or {}, b.get("correctness") or {})
    if c:
        return c
    ma = len((a.get("artifacts") or {}).get("missing") or [])
    mb = len((b.get("artifacts") or {}).get("missing") or [])
    if ma != mb:
        return -1 if ma < mb else 1
    ea = a.get("execution") or {}
    eb = b.get("execution") or {}
    err_a = ea.get("tool_errors", 0) + ea.get("parse_errors", 0)
    err_b = eb.get("tool_errors", 0) + eb.get("parse_errors", 0)
    if err_a != err_b:
        return -1 if err_a < err_b else 1
    sa, sb = ea.get("steps", 0), eb.get("steps", 0)
    if sa != sb:
        return -1 if sa < sb else 1
    qa = (a.get("judge") or {}).get("quality")
    qb = (b.get("judge") or {}).get("quality")
    if qa is not None and qb is not None and qa != qb:
        return -1 if qa > qb else 1
    return 0


def _fighter_advantage(fa: dict, fb: dict, weights: dict) -> float:
    """Aggregate advantage of fa over fb: sum of phase_weight * phase_sign."""
    total = 0.0
    phases = sorted(set((fa.get("phases") or {})) | set((fb.get("phases") or {})))
    for p in phases:
        pa = (fa.get("phases") or {}).get(p)
        pb = (fb.get("phases") or {}).get(p)
        try:
            w = float(weights.get(p, 1.0))
        except (TypeError, ValueError):
            w = 1.0
        if pa is None and pb is None:
            continue
        if pa is None:
            total -= w
            continue
        if pb is None:
            total += w
            continue
        # compare returns -1 when pa is better; flip so advantage is positive.
        total += w * (-compare_phase_result(pa, pb))
    return total


def _fighter_ineligible(fighter: dict) -> bool:
    return any(_is_ineligible(pr) for pr in (fighter.get("phases") or {}).values())


def decide_winner(evidence: dict, format_config: dict | None = None) -> dict:
    """Deterministically rank fighters from evidence. Never raises."""
    cfg = format_config or {}
    fighters = list(evidence.get("fighters") or [])
    if not fighters:
        return {
            "winner": None, "tie": True, "ineligible": [], "ranking": [],
            "groups": [], "reason": "no_fighters",
        }
    missing = [
        f
        for f in fighters
        if any(
            (pr.get("status") == "incomplete")
            for pr in (f.get("phases") or {}).values()
        )
    ]
    if missing:
        return {
            "winner": None, "tie": True, "ineligible": [],
            "ranking": [], "groups": [],
            "reason": "incomplete_evidence",
            "fighters_missing_evidence": [f["fighter_id"] for f in missing],
        }
    inel = [f for f in fighters if _fighter_ineligible(f)]
    inel_ids = [f["fighter_id"] for f in inel]
    eligible = [f for f in fighters if f["fighter_id"] not in inel_ids]
    weights = cfg.get("scoring_weights") or {}
    if not isinstance(weights, dict):
        weights = {}

    def cmp_fighters(x, y):
        adv = _fighter_advantage(x, y, weights)
        return -1 if adv > 0 else (1 if adv < 0 else 0)

    ordered = sorted(eligible, key=functools.cmp_to_key(cmp_fighters))
    groups: list[list[dict]] = []
    for f in ordered:
        if groups and _fighter_advantage(groups[-1][0], f, weights) == 0:
            groups[-1].append(f)
        else:
            groups.append([f])
    if inel:
        groups.append(list(inel))
    winner = None
    tie = False
    if groups:
        if len(groups[0]) == 1:
            winner = groups[0][0]["fighter_id"]
        else:
            tie = True

    # "A winner" and "a verified successful solution" are different facts.
    # Ranking still happens when nobody passed; the verified flag must not.
    def _verified(f):
        prs = list((f.get("phases") or {}).values())
        if not prs:
            return False
        for p in prs:
            if p.get("status") != "completed" or _is_ineligible(p):
                return False
            c = p.get("correctness") or {}
            if not c.get("total") or c.get("passed") != c.get("total"):
                return False
        return True

    verified = [f["fighter_id"] for f in fighters if _verified(f)]
    return {
        "winner": winner,
        "tie": tie,
        "ineligible": inel_ids,
        "ranking": [f["fighter_id"] for g in groups for f in g],
        "groups": [[f["fighter_id"] for f in g] for g in groups],
        "reason": "deterministic",
        "verified_solution": bool(verified),
        "verified_fighters": verified,
        "best_attempt": None if verified else winner,
    }


def deterministic_scores(decision: dict) -> dict | None:
    """Map a decision to numeric scores (higher = better; ties share value).

    Returns None when the decision carries no usable evidence - callers must
    then keep their fallback (judge scores), never fabricate zeros.
    """
    groups = decision.get("groups") or []
    if not groups:
        return None
    scores: dict[str, float] = {}
    for gi, group in enumerate(groups):
        below = sum(len(g) for g in groups[gi + 1:])
        for mid in group:
            scores[str(mid)] = float(below)
    return scores
