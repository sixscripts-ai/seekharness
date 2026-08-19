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
