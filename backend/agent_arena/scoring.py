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
        if pa is None or pb is None:
            continue
        total += w * (-compare_phase_result(pa, pb))
    return total


def _fighter_ineligible(fighter: dict) -> bool:
    return any(_is_ineligible(pr) for pr in (fighter.get("phases") or {}).values())


def _fighter_verified(fighter: dict) -> bool:
    prs = list((fighter.get("phases") or {}).values())
    if not prs:
        return False
    for p in prs:
        if p.get("status") != "completed" or _is_ineligible(p):
            return False
        c = p.get("correctness") or {}
        if not c.get("total") or c.get("passed") != c.get("total"):
            return False
    return True


def _phase_sets_disjoint(fighters: list) -> bool:
    if len(fighters) < 2:
        return False
    seen: list[set] = []
    for f in fighters:
        keys = set((f.get("phases") or {}))
        for other in seen:
            if keys & other:
                return False
        seen.append(keys)
    return True


def _battle_plan_rank_key(fighter: dict, phase_order: list[str]) -> tuple:
    phases = fighter.get("phases") or {}
    idxs = [phase_order.index(p) for p in phases if p in phase_order]
    latest = max(idxs) if idxs else -1
    earliest_completed = min(
        (
            phase_order.index(p)
            for p, pr in phases.items()
            if p in phase_order and pr.get("status") == "completed"
        ),
        default=999,
    )
    if _fighter_verified(fighter):
        return (2, latest)
    if earliest_completed < 999:
        return (1, -earliest_completed)
    return (0, latest)


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
    phase_order = list(evidence.get("phases") or [])
    use_plan_rank = bool(cfg.get("battle_plan")) and _phase_sets_disjoint(fighters)

    def cmp_fighters(x, y):
        if use_plan_rank:
            kx = _battle_plan_rank_key(x, phase_order)
            ky = _battle_plan_rank_key(y, phase_order)
            if kx != ky:
                return -1 if kx > ky else 1
            return 0
        adv = _fighter_advantage(x, y, weights)
        return -1 if adv > 0 else (1 if adv < 0 else 0)

    ordered = sorted(eligible, key=functools.cmp_to_key(cmp_fighters))
    groups: list[list[dict]] = []
    for f in ordered:
        tied = False
        if groups:
            if use_plan_rank:
                tied = _battle_plan_rank_key(groups[-1][0], phase_order) == (
                    _battle_plan_rank_key(f, phase_order)
                )
            else:
                tied = _fighter_advantage(groups[-1][0], f, weights) == 0
        if tied:
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

    verified = [f["fighter_id"] for f in fighters if _fighter_verified(f)]
    if cfg.get("judge_only") or cfg.get("evaluation_mode") == "quick":
        verified = []
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


def deterministic_scores(decision: dict, evidence: dict | None = None) -> dict | None:
    """Map a decision to numeric scores (higher = better; ties share value).

    For Full-Stack Builder vs. Breaker battles, evaluates the decoupled 100-pt
    scoring matrices directly.

    If det_scores:
        return det_scores
    Returns None when the decision carries no usable evidence. Callers must
    not fall back to sandbox/judge scores.
    """
    if evidence and (
        evidence.get("format_id") in ("fullstack", "builder_breaker", "fullstack_arena")
        or decision.get("format_id") in ("fullstack", "builder_breaker")
    ):
        fs_scores = compute_fullstack_scores(evidence)
        if fs_scores:
            return {fid: fs["total"] for fid, fs in fs_scores.items()}

    groups = decision.get("groups") or []
    if not groups:
        return None
    scores: dict[str, float] = {}
    for gi, group in enumerate(groups):
        below = sum(len(g) for g in groups[gi + 1:])
        for mid in group:
            scores[str(mid)] = float(below)
    return scores


def compute_fullstack_scores(evidence: dict) -> dict[str, dict]:
    """Compute decoupled 100-point scoring matrices for Full-Stack Builder vs. Breaker battles.

    Explicit components:
    Builder (100 pts total):
      - Deployment readiness: 20 pts (20 for clean deployment or successful repair, 0 if deploy failed)
      - Functional correctness: 40 pts (pass_ratio * 40; 0 if missing tests or 0% pass)
      - Security retained: 40 pts minus verified deductions:
          * flag_captured: -15 pts
          * server_crashed: -10 pts
          * unauthorized_mutation: -15 pts
          (Floor at 0 pts)
      Total Builder = deployment + correctness + security_retained

    Breaker (100 pts total):
      - Flag capture: 35 pts (if canary/flag captured)
      - Crash / DoS: 25 pts (if server_crashed, or 15 pts if availability_degraded)
      - Unauthorized mutation: 40 pts (if prohibited state change verified)
      Total Breaker = sum of verified exploit points
    """
    scores: dict[str, dict] = {}
    fighters = evidence.get("fighters") or []

    # Identify breaker exploit facts across phases
    breaker_exploits = {
        "flag_captured": False,
        "server_crashed": False,
        "availability_degraded": False,
        "unauthorized_mutation": False,
    }
    for f in fighters:
        if str(f.get("role") or "").lower() in ("breaker", "attacker", "red_team"):
            for pr in (f.get("phases") or {}).values():
                ev = pr.get("exploit_evidence") or {}
                for k in breaker_exploits:
                    if ev.get(k):
                        breaker_exploits[k] = True

    for f in fighters:
        fid = f.get("fighter_id")
        role = str(f.get("role") or "").lower()
        if role in ("builder", "defender", "blue_team"):
            deploy_points = 0.0
            correctness_points = 0.0
            has_completed = False
            for pr in (f.get("phases") or {}).values():
                dep = pr.get("deployment") or {}
                if dep.get("ready") or dep.get("status") in ("DEPLOY_SUCCESS", "REPAIRED_DEPLOY_SUCCESS"):
                    deploy_points = max(deploy_points, 20.0)
                corr = pr.get("correctness") or {}
                ratio = corr.get("pass_ratio")
                if ratio is not None:
                    correctness_points = max(correctness_points, round(ratio * 40.0, 2))
                elif pr.get("status") == "completed":
                    has_completed = True

            if correctness_points == 0.0 and has_completed:
                correctness_points = 40.0

            # Deductions from security retained (40 pts max)
            deductions = 0.0
            if breaker_exploits["flag_captured"]:
                deductions += 15.0
            if breaker_exploits["server_crashed"]:
                deductions += 10.0
            elif breaker_exploits["availability_degraded"]:
                deductions += 5.0
            if breaker_exploits["unauthorized_mutation"]:
                deductions += 15.0

            security_retained = max(0.0, 40.0 - deductions)
            total_builder = round(deploy_points + correctness_points + security_retained, 2)
            scores[fid] = {
                "role": "builder",
                "total": total_builder,
                "components": {
                    "deployment_readiness": deploy_points,
                    "functional_correctness": correctness_points,
                    "security_retained": security_retained,
                    "exploit_deductions": deductions,
                },
            }
        elif role in ("breaker", "attacker", "red_team"):
            flag_pts = 35.0 if breaker_exploits["flag_captured"] else 0.0
            crash_pts = 25.0 if breaker_exploits["server_crashed"] else (
                15.0 if breaker_exploits["availability_degraded"] else 0.0
            )
            mutation_pts = 40.0 if breaker_exploits["unauthorized_mutation"] else 0.0
            total_breaker = round(flag_pts + crash_pts + mutation_pts, 2)
            scores[fid] = {
                "role": "breaker",
                "total": total_breaker,
                "components": {
                    "flag_capture": flag_pts,
                    "crash_dos": crash_pts,
                    "unauthorized_mutation": mutation_pts,
                },
            }
    return scores
