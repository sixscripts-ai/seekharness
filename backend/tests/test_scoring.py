"""Adversarial tests for deterministic evidence-based scoring (Phase 1).

Guards the invariant: working code beats broken code. The judge never
overrides the correctness tier; policy-invalid fighters cannot win; missing
evidence becomes UNKNOWN instead of fabricated zeros; scoring is
byte-for-byte deterministic.
"""

from __future__ import annotations

from agent_arena import evidence, scoring


def _mk(
    model_id: str,
    outcome: str = "TEST_PASS",
    passed: bool = True,
    steps: int = 10,
    tests: dict | None = None,
    artifact_present: bool = True,
    required: list[str] | None = None,
    policy: str = "clean",
    tool_errors: int = 0,
    parse_errors: int = 0,
    judge_quality: float | None = None,
    phase: str = "race",
) -> dict:
    result = {
        "model_id": model_id,
        "role": "player_a",
        "phase": phase,
        "outcome": outcome,
        "passed": passed,
        "steps": steps,
        "tool_errors": tool_errors,
        "parse_errors": parse_errors,
    }
    if tests is not None:
        result["tests"] = tests
    required = list(required or ["solution.py"])
    files = {"solution.py": "x"} if artifact_present else {}
    result["files"] = files
    result["artifact_checks"] = {
        "present": [r for r in required if r in files],
        "missing": [r for r in required if r not in files],
    }
    if policy != "clean":
        result["policy"] = {"status": policy, "violations": ["tampered-harness"]}
    if judge_quality is not None:
        result["judge_quality"] = judge_quality
    return result


def _decide(results, cfg=None, judge=None):
    judge = judge or {}
    summary = evidence.build_battle_evidence("b1", results, cfg or {}, judge_scores=judge)
    decision = scoring.decide_winner(summary, cfg or {})
    return summary, decision, scoring.deterministic_scores(decision)


def test_case1_correctness_beats_judge():
    a = _mk("A", tests={"passed": 10, "total": 10}, judge_quality=2.0)
    b = _mk("B", tests={"passed": 8, "total": 10}, judge_quality=9.8)
    _, decision, scores = _decide([a, b], judge={"A": 2.0, "B": 9.8})
    assert decision["winner"] == "A"
    assert scores["A"] > scores["B"]


def test_case2_required_artifact_decides():
    a = _mk("A", artifact_present=False)
    b = _mk("B")
    _, decision, scores = _decide([a, b])
    assert decision["winner"] == "B"


def test_case3_reliability_and_efficiency():
    a = _mk("A", steps=5)
    b = _mk("B", steps=20)
    _, decision, _ = _decide([a, b])
    assert decision["winner"] == "A"

    a2 = _mk("A", tool_errors=5)
    b2 = _mk("B")
    _, decision2, _ = _decide([a2, b2])
    assert decision2["winner"] == "B"


def test_case4_judge_breaks_genuine_tie():
    a = _mk("A", judge_quality=4.0)
    b = _mk("B", judge_quality=9.0)
    _, decision, scores = _decide([a, b], judge={"A": 4.0, "B": 9.0})
    assert decision["winner"] == "B"


def test_case5_policy_invalid_cannot_win():
    a = _mk("A", policy="invalid", tests={"passed": 10, "total": 10})
    b = _mk("B", tests={"passed": 8, "total": 10})
    _, decision, scores = _decide([a, b])
    assert decision["winner"] == "B"
    assert "A" in decision["ineligible"]
    assert scores["A"] <= scores["B"]

    aw = _mk("A", policy="warning")
    bw = _mk("B")
    _, decision2, _ = _decide([aw, bw])
    assert decision2["winner"] == "B"


def test_case6_normalized_correctness_different_totals():
    a = _mk("A", tests={"passed": 9, "total": 9})
    b = _mk("B", tests={"passed": 12, "total": 15})
    _, decision, _ = _decide([a, b])
    assert decision["winner"] == "A"


def test_case7_multi_phase_aggregation():
    a_build = _mk("A", phase="build", tests={"passed": 10, "total": 10})
    b_build = _mk("B", phase="build", tests={"passed": 8, "total": 10})
    a_break = _mk("A", phase="break", tests={"passed": 5, "total": 10})
    b_break = _mk("B", phase="break", tests={"passed": 10, "total": 10})
    cfg = {"scoring_weights": {"build": 0.6, "break": 0.4}}
    _, decision, _ = _decide([a_build, b_build, a_break, b_break], cfg=cfg)
    assert decision["winner"] == "A"

    cfg_tie = {"scoring_weights": {"build": 0.5, "break": 0.5}}
    _, decision2, _ = _decide([a_build, b_build, a_break, b_break], cfg=cfg_tie)
    assert decision2["tie"] is True
    assert decision2["winner"] is None


def test_case8_timeout_explicit():
    a = _mk("A", outcome="STEP_BUDGET_EXCEEDED", passed=False)
    b = _mk("B", outcome="TEST_FAIL", passed=False)
    summary, decision, _ = _decide([a, b])
    phases_a = summary["fighters"][0]["phases"]["race"]
    assert phases_a["status"] == "timeout"
    assert decision["winner"] == "B"


def test_case9_missing_evidence_is_unknown():
    a = _mk("A")
    b = {"model_id": "B"}  # no outcome at all
    summary, decision, scores = _decide([a, b])
    assert decision["reason"] == "incomplete_evidence"
    assert decision["winner"] is None
    assert scores is None
    # Never fabricated as 0/1 failed tests.
    pr = summary["fighters"][1]["phases"]["race"]
    assert pr["status"] == "incomplete"
    assert pr["correctness"]["passed"] is None
    assert pr["correctness"]["failed"] is None
    assert pr["correctness"]["total"] is None
    assert pr["correctness"]["pass_ratio"] is None


def test_budget_without_verdict_is_not_a_test_failure():
    # EXECUTOR_RESULT exists but carries no valid test outcome. The explicit
    # STEP_BUDGET_EXCEEDED marker is a known state ("timeout") - richer than
    # collapsing it to "incomplete" - and its correctness is NEVER 0/1.
    b = {"model_id": "B", "outcome": "STEP_BUDGET_EXCEEDED"}
    summary, decision, scores = _decide([_mk("A"), b])
    pr = summary["fighters"][1]["phases"]["race"]
    assert pr["status"] == "timeout"
    assert pr["correctness"]["total"] is None
    assert pr["correctness"]["passed"] is None
    assert pr["correctness"]["pass_ratio"] is None
    assert decision["winner"] == "A"  # completed beats timeout
    assert scores["A"] > scores["B"]


def test_malformed_policy_is_unknown_not_clean():
    a = _mk("A", policy="bananas")
    b = _mk("B")
    summary, decision, _ = _decide([a, b])
    pa = summary["fighters"][0]["phases"]["race"]
    assert pa["policy"]["status"] == "unknown"
    assert decision["winner"] == "B"  # clean beats unknown
    assert "A" not in decision["ineligible"]


def test_warning_policy_ranks_below_clean_but_is_eligible():
    a = _mk("A", policy="warning")
    b = _mk("B")
    summary, decision, _ = _decide([a, b])
    pa = summary["fighters"][0]["phases"]["race"]
    assert pa["policy"]["status"] == "warning"
    assert decision["winner"] == "B"
    assert decision["ineligible"] == []


def test_verified_solution_distinct_from_winner():
    a = _mk("A", outcome="TEST_FAIL", passed=False, steps=5)
    b = _mk("B", outcome="TEST_FAIL", passed=False, steps=12)
    _, decision, _ = _decide([a, b])
    assert decision["winner"] == "A"  # still ranked...
    assert decision["verified_solution"] is False  # ...but nothing works
    assert decision["verified_fighters"] == []
    assert decision["best_attempt"] == "A"

    a2 = _mk("A")
    b2 = _mk("B", outcome="TEST_FAIL", passed=False)
    _, decision2, _ = _decide([a2, b2])
    assert decision2["winner"] == "A"
    assert decision2["verified_solution"] is True
    assert decision2["verified_fighters"] == ["A"]
    assert decision2["best_attempt"] is None


def test_case10_determinism():
    results = [
        _mk("A", tests={"passed": 9, "total": 10}, judge_quality=7.0),
        _mk("B", tests={"passed": 9, "total": 10}, judge_quality=6.0),
    ]
    s1, d1, sc1 = _decide(results, judge={"A": 7.0, "B": 6.0})
    s2, d2, sc2 = _decide(results, judge={"A": 7.0, "B": 6.0})
    assert s1 == s2
    assert d1 == d2
    assert sc1 == sc2
    assert d1["winner"] == "A"


def test_evidence_builds_from_executor_result_shape():
    results = [
        {
            "model_id": "m1",
            "role": "player_a",
            "phase": "race",
            "outcome": "TEST_PASS",
            "passed": True,
            "steps": 7,
            "tool_errors": 1,
            "parse_errors": 0,
            "files": {"solution.py": "x", "THEORY.md": "y"},
            "chosen_skills": ["python-kata-fixer"],
            "theory": "t",
            "skill_read_ok": True,
            "preview_url": "",
            "artifact_checks": {"present": ["solution.py"], "missing": []},
        },
    ]
    cfg = {"artifacts": {"required": ["solution.py", "THEORY.md"]}}
    summary = evidence.build_battle_evidence("b9", results, cfg, judge_scores={"m1": 8.0})
    f = summary["fighters"][0]
    pr = f["phases"]["race"]
    assert summary["schema_version"] == 1
    assert summary["scoring_version"] == "arena-score-v1"
    assert pr["correctness"] == {"passed": 1, "failed": 0, "total": 1, "pass_ratio": 1.0}
    assert pr["execution"]["tool_errors"] == 1
    assert pr["judge"]["quality"] == 8.0
    assert pr["outputs"]["important_files"] == ["THEORY.md", "solution.py"]


def test_fighters_sorted_for_stable_output():
    summary, _, _ = _decide([_mk("B"), _mk("A")])
    assert [f["fighter_id"] for f in summary["fighters"]] == ["A", "B"]


def test_battle_plan_disjoint_phases_not_incomplete():
    builder = _mk(
        "builder",
        phase="build",
        required=["auth.py"],
        tests={"passed": 1, "total": 1},
    )
    builder["role"] = "builder"
    breaker = _mk(
        "breaker",
        phase="break",
        required=["exploit.py"],
        tests={"passed": 1, "total": 1},
    )
    breaker["role"] = "breaker"
    cfg = {"battle_plan": True}
    summary, decision, scores = _decide([builder, breaker], cfg=cfg)
    assert "break" not in summary["fighters"][0]["phases"] or (
        next(f for f in summary["fighters"] if f["fighter_id"] == "builder")["phases"].keys()
        == {"build"}
    )
    bld = next(f for f in summary["fighters"] if f["fighter_id"] == "builder")
    brk = next(f for f in summary["fighters"] if f["fighter_id"] == "breaker")
    assert set(bld["phases"]) == {"build"}
    assert set(brk["phases"]) == {"break"}
    assert decision["reason"] != "incomplete_evidence"
    assert decision["winner"] == "breaker"
    assert decision["verified_solution"] is True
    assert "breaker" in decision["verified_fighters"]
    assert scores is not None
    assert scores["breaker"] > scores["builder"]


def test_battle_plan_only_builder_verified_wins():
    builder = _mk("builder", phase="build", required=["auth.py"])
    builder["role"] = "builder"
    breaker = _mk(
        "breaker",
        phase="break",
        outcome="TEST_FAIL",
        passed=False,
        required=["exploit.py"],
    )
    breaker["role"] = "breaker"
    _, decision, _ = _decide([builder, breaker], cfg={"battle_plan": True})
    assert decision["reason"] == "deterministic"
    assert decision["winner"] == "builder"
    assert decision["verified_fighters"] == ["builder"]


def test_quick_judge_only_never_claims_verification():
    a = _mk("A", outcome="JUDGE_ONLY", passed=True, judge_quality=9.0)
    a["passed"] = None
    b = _mk("B", outcome="JUDGE_ONLY", passed=True, judge_quality=4.0)
    b["passed"] = None
    cfg = {"judge_only": True, "evaluation_mode": "quick"}
    summary, decision, scores = _decide(
        [a, b], cfg=cfg, judge={"A": 9.0, "B": 4.0}
    )
    assert summary["fighters"][0]["phases"]["race"]["correctness"]["total"] is None
    assert decision["verified_solution"] is False
    assert decision["verified_fighters"] == []
    assert decision["winner"] == "A"
    assert scores["A"] > scores["B"]


def test_verified_custom_ranks_test_pass_first():
    a = _mk("A", tests={"passed": 1, "total": 1}, judge_quality=2.0)
    b = _mk("B", outcome="TEST_FAIL", passed=False, tests={"passed": 0, "total": 1}, judge_quality=9.8)
    cfg = {"evaluation_mode": "verified", "custom": True}
    _, decision, scores = _decide([a, b], cfg=cfg, judge={"A": 2.0, "B": 9.8})
    assert decision["winner"] == "A"
    assert decision["verified_solution"] is True
    assert scores["A"] > scores["B"]


def test_fullstack_decoupled_scoring_clean_defense():
    """Builder deploys cleanly and passes tests; Breaker captures 0 exploits."""
    builder = {
        "model_id": "model_builder",
        "role": "builder",
        "phase": "build",
        "outcome": "TEST_PASS",
        "passed": True,
        "deployment_status": "DEPLOY_SUCCESS",
        "deployment_ready": True,
        "tests": {"passed": 5, "total": 5},
    }
    breaker = {
        "model_id": "model_breaker",
        "role": "breaker",
        "phase": "break",
        "outcome": "COMPLETED",
        "passed": False,
        "exploit_evidence": {
            "server_crashed": False,
            "availability_degraded": False,
            "unauthorized_mutation": False,
            "flag_captured": False,
        },
    }
    summary = evidence.build_battle_evidence(
        "b_fs1", [builder, breaker], format_id="fullstack"
    )
    fs_scores = scoring.compute_fullstack_scores(summary)
    assert fs_scores["model_builder"]["total"] == 100.0
    assert fs_scores["model_builder"]["components"]["deployment_readiness"] == 20.0
    assert fs_scores["model_builder"]["components"]["functional_correctness"] == 40.0
    assert fs_scores["model_builder"]["components"]["security_retained"] == 40.0
    assert fs_scores["model_breaker"]["total"] == 0.0

    det_scores = scoring.deterministic_scores(
        {"format_id": "fullstack", "groups": [["model_builder"], ["model_breaker"]]},
        evidence=summary,
    )
    assert det_scores["model_builder"] == 100.0
    assert det_scores["model_breaker"] == 0.0


def test_fullstack_decoupled_scoring_breaker_exploits():
    """Breaker captures flag (35 pts) and crashes server (25 pts) = 60 pts.

    Builder loses 15 (flag) + 10 (crash) from retained security: 40 - 25 = 15 pts.
    Builder total = 20 (deploy) + 40 (correctness) + 15 (retained) = 75 pts.
    """
    builder = {
        "model_id": "model_builder",
        "role": "builder",
        "phase": "build",
        "outcome": "TEST_PASS",
        "passed": True,
        "deployment_status": "REPAIRED_DEPLOY_SUCCESS",
        "deployment_ready": True,
        "tests": {"passed": 10, "total": 10},
    }
    breaker = {
        "model_id": "model_breaker",
        "role": "breaker",
        "phase": "break",
        "outcome": "COMPLETED",
        "passed": True,
        "exploit_evidence": {
            "server_crashed": True,
            "availability_degraded": True,
            "unauthorized_mutation": False,
            "flag_captured": True,
        },
    }
    summary = evidence.build_battle_evidence(
        "b_fs2", [builder, breaker], format_id="fullstack"
    )
    fs_scores = scoring.compute_fullstack_scores(summary)
    assert fs_scores["model_breaker"]["total"] == 60.0
    assert fs_scores["model_breaker"]["components"]["flag_capture"] == 35.0
    assert fs_scores["model_breaker"]["components"]["crash_dos"] == 25.0
    assert fs_scores["model_builder"]["total"] == 75.0
    assert fs_scores["model_builder"]["components"]["security_retained"] == 15.0


def test_fullstack_decoupled_scoring_complete_compromise():
    """Breaker captures all 3 exploit vectors = 100 pts.

    Builder security retained is reduced to 0 (40 - 15 - 10 - 15).
    Builder total = 20 (deploy) + 40 (correctness) + 0 (retained) = 60 pts.
    """
    builder = {
        "model_id": "model_builder",
        "role": "builder",
        "phase": "build",
        "outcome": "TEST_PASS",
        "passed": True,
        "deployment_status": "DEPLOY_SUCCESS",
        "deployment_ready": True,
        "tests": {"passed": 4, "total": 4},
    }
    breaker = {
        "model_id": "model_breaker",
        "role": "breaker",
        "phase": "break",
        "outcome": "COMPLETED",
        "passed": True,
        "exploit_evidence": {
            "server_crashed": True,
            "availability_degraded": True,
            "unauthorized_mutation": True,
            "flag_captured": True,
        },
    }
    summary = evidence.build_battle_evidence(
        "b_fs3", [builder, breaker], format_id="fullstack"
    )
    fs_scores = scoring.compute_fullstack_scores(summary)
    assert fs_scores["model_breaker"]["total"] == 100.0
    assert fs_scores["model_builder"]["total"] == 60.0
    assert fs_scores["model_builder"]["components"]["security_retained"] == 0.0

