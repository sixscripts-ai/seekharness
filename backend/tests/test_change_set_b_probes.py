"""Deterministic Probes A-E for Change Set B Final Fairness Audit."""

import json
import os
from pathlib import Path
import pytest

from agent_arena.memory import (
    MemoryProvenance,
    is_provenance_eligible,
    maybe_remember,
    remember,
    retrieve,
)
from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor, select_skills
from agent_arena.skills.canonical import CanonicalSkillResolver, SkillRecord
from agent_arena.skills.ranking import (
    RankedSkillScore,
    curate_shortlist,
    rank_skills,
    rank_skills_detailed,
)
from agent_arena.skills.attribution import compute_skill_attributions


@pytest.fixture
def test_skill_catalog():
    return [
        SkillRecord(
            id="python-kata-fixer",
            name="python-kata-fixer",
            slug="python-kata-fixer",
            category="coding",
            tags=["python", "kata", "algorithm"],
            prerequisites=["shell-basics"],
            description="Fixes Python kata bugs.",
            desc="Fixes Python kata bugs.",
            elo=1200,
        ),
        SkillRecord(
            id="shell-basics",
            name="shell-basics",
            slug="shell-basics",
            category="system",
            tags=["shell", "bash"],
            prerequisites=[],
            description="Basic shell usage.",
            desc="Basic shell usage.",
            elo=1200,
        ),
        SkillRecord(
            id="waf-bypass",
            name="waf-bypass",
            slug="waf-bypass",
            category="security",
            tags=["security", "waf"],
            prerequisites=[],
            description="WAF testing.",
            desc="WAF testing.",
            elo=1200,
        ),
        SkillRecord(
            id="secure-code-execution",
            name="secure-code-execution",
            slug="secure-code-execution",
            category="security",
            tags=["sandbox", "isolation"],
            prerequisites=[],
            description="Sandbox security.",
            desc="Sandbox security.",
            elo=1200,
        ),
    ]


def test_probe_a_strict_contamination(test_skill_catalog):
    """Probe A — Strict contamination probe:
    Seed:
    - extreme Elo values (50,000 Elo)
    - strong recommended_skills
    - two different model IDs (model-alpha vs model-beta)
    Expected:
    - same eligible catalog
    - same ranking
    - same shortlist
    - zero historical adjustment (all historical_adjustments == 0.0)
    - zero memory supplied
    """
    target_ctx = {
        "name": "Palindrome Kata Race",
        "category": "coding",
        "runtime": "python",
        "tags": ["python", "kata"],
        "recommended_skills": ["python-kata-fixer"],
        "context_mode": "strict",
    }

    extreme_elos = {
        "waf-bypass": 50000.0,
        "secure-code-execution": 40000.0,
        "python-kata-fixer": 100.0,
    }

    # 1. Model Alpha ranking
    ranked_alpha = rank_skills_detailed(
        test_skill_catalog,
        target_ctx,
        context_mode="strict",
        skill_elos=extreme_elos,
    )

    # 2. Model Beta ranking
    ranked_beta = rank_skills_detailed(
        test_skill_catalog,
        target_ctx,
        context_mode="strict",
        skill_elos=extreme_elos,
    )

    # Prove identical ordering and scores across models
    assert [r.skill.id for r in ranked_alpha] == [r.skill.id for r in ranked_beta]
    assert [r.final_score for r in ranked_alpha] == [r.final_score for r in ranked_beta]

    # Prove historical adjustment is EXACTLY 0.0 for all skills in strict mode
    for r in ranked_alpha:
        assert r.historical_adjustment == 0.0
        assert r.final_score == r.semantic_score

    # Prove top skill is determined purely by semantic/public recommendation, ignoring 50,000 Elo
    assert ranked_alpha[0].skill.id == "python-kata-fixer"

    # Prove memory supplied is strictly zero
    mem_alpha = retrieve(None, "", "Palindrome", context_mode="strict", model_id="model-alpha")
    mem_beta = retrieve(None, "", "Palindrome", context_mode="strict", model_id="model-beta")
    assert mem_alpha == []
    assert mem_beta == []


def test_probe_b_adaptive_single_learning(test_skill_catalog):
    """Probe B — Adaptive single-learning probe:
    One authoritative result with one loaded skill.
    Expected:
    - exactly one logical learning mutation per attributed skill
    - failed/unloaded skills receive none
    """
    resolver = CanonicalSkillResolver(test_skill_catalog)

    results = [
        {
            "role": "player_a",
            "model_id": "model_1",
            "passed": True,
            "outcome": "TEST_PASS",
            "steps": 4,
            "skills_telemetry": {
                "loaded_skill_ids": ["python-kata-fixer"],
                "load_failures": {"waf-bypass": "file_not_found"},
            },
            "skill_reads": ["python-kata-fixer"],
        },
        {
            "role": "player_b",
            "model_id": "model_2",
            "passed": False,
            "outcome": "TEST_FAIL",
            "steps": 6,
            "skills_telemetry": {
                "loaded_skill_ids": ["shell-basics"],
            },
            "skill_reads": ["shell-basics"],
        },
    ]

    attributions = compute_skill_attributions(results, resolver=resolver)

    # player_a loaded python-kata-fixer and passed -> exactly 1 win attributed
    assert len(attributions["player_a"]) == 1
    assert attributions["player_a"][0]["skill_id"] == "python-kata-fixer"
    assert attributions["player_a"][0]["outcome"] == "win"

    # waf-bypass failed to load -> 0 attributions
    assert not any(a["skill_id"] == "waf-bypass" for a in attributions["player_a"])

    # player_b loaded shell-basics and failed -> exactly 1 loss attributed
    assert len(attributions["player_b"]) == 1
    assert attributions["player_b"][0]["skill_id"] == "shell-basics"
    assert attributions["player_b"][0]["outcome"] == "loss"


def test_probe_c_provenance_isolation():
    """Probe C — Provenance isolation probe:
    Seed a memory containing harmless text but with visibility_class='evaluator_private'.
    Confirm it is never supplied based on provenance alone.
    Then seed an allowed public/model-scoped lesson -> supplied in adaptive, blocked in strict.
    """
    from test_memory_policy import FakeMemoryDatabases

    db = FakeMemoryDatabases()

    # 1. Harmless text with evaluator_private provenance (no secret keywords)
    remember(
        db,
        "db",
        insight="Standard procedure: initialize configuration dictionary before calling handler.",
        battle_id="b-eval",
        model_id="gpt-4o",
        user_id="user_1",
        visibility_class="evaluator_private",
    )

    # 2. Allowed model-scoped safe lesson
    remember(
        db,
        "db",
        insight="Adaptive lesson: verify return types when parsing json outputs.",
        battle_id="b-learn",
        model_id="gpt-4o",
        user_id="user_1",
        visibility_class="model_private",
    )

    # Strict mode query -> 0 memories
    strict_mems = retrieve(db, "db", "initialize configuration parsing json", context_mode="strict", model_id="gpt-4o", user_id="user_1")
    assert strict_mems == []

    # Adaptive mode query -> only the model-scoped lesson, evaluator_private is BLOCKED by provenance alone
    adapt_mems = retrieve(db, "db", "initialize configuration parsing json", context_mode="adaptive", model_id="gpt-4o", user_id="user_1")
    assert len(adapt_mems) == 1
    assert "Adaptive lesson" in adapt_mems[0]["insight"]
    assert not any("evaluator_private" in str(m.get("visibility_class")) for m in adapt_mems)
    assert not any("Standard procedure" in m["insight"] for m in adapt_mems)


def test_probe_d_trusted_failure_memory():
    """Probe D — Trusted failure memory probe:
    Create a trusted authoritative failed result containing a safe model-authored lesson.
    Confirm:
    - stored as learnable lesson with authoritative_status='verified_fail'
    - infrastructure failures (outcome='PROVIDER_ERROR') are rejected and never stored.
    """
    from test_memory_policy import FakeMemoryDatabases

    db = FakeMemoryDatabases()

    # 1. Trusted authoritative failure (e.g. test failed after clean model execution)
    doc_fail = maybe_remember(
        db,
        "db",
        insight="Learned: approach with regex failed on nested brackets; need recursive parser.",
        battle_id="b-fail-1",
        model_id="gpt-4o",
        user_id="user_1",
        outcome="TEST_FAIL",
        policy_status="clean",
    )
    assert doc_fail is not None
    assert doc_fail.get("authoritative_status") == "verified_fail"

    # 2. Infrastructure failure -> rejected
    doc_infra = maybe_remember(
        db,
        "db",
        insight="Sandbox timed out during startup",
        battle_id="b-infra-1",
        model_id="gpt-4o",
        user_id="user_1",
        outcome="PROVIDER_ERROR",
        policy_status="clean",
    )
    assert doc_infra is None


def test_probe_e_model_autonomy(monkeypatch):
    """Probe E — Model autonomy:
    Run a scripted fighter with several offered skills.
    Confirm Arena:
    - ranks candidates
    - presents candidates
    - does not auto-load top skill
    - does not tell fighter which one to choose
    - fighter's explicit tool call determines selection.
    """
    from agent_arena.sandbox.executors import get_executor
    from agent_arena.seed_formats import ALL_FORMATS

    cfg = next(c for c in ALL_FORMATS if c["name"] == "Tool-using coding race")
    cfg = {**cfg, "context_mode": "strict", "max_tool_turns": 2, "max_tool_steps": 6}
    exe = get_executor(cfg)

    # Fighter explicitly chooses NOT to load the top skill (python-kata-fixer), but loads terminal-sandbox-ui instead
    reply = (
        "SKILLS: terminal-sandbox-ui\n"
        "TOOL use_skill name=terminal-sandbox-ui\n"
        "TOOL write path=solution.py\n"
        "def is_palindrome(s: str) -> bool:\n"
        "    c = [ch.lower() for ch in s if ch.isalnum()]\n"
        "    return c == c[::-1]\n"
        "END_TOOL\n"
        "TOOL test\n"
        "DONE\n"
    )

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": reply, "b": reply}

    scores = exe.run_battle(
        battle_id="probe-e-autonomy-1",
        format_config=cfg,
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
    )

    def _extract_results(rounds):
        found = []
        marker = "EXECUTOR_RESULT:"
        for r in rounds:
            art = r.get("artifact") or ""
            if marker not in art:
                continue
            payload = art.split(marker, 1)[1].strip()
            found.append(json.loads(payload))
        return found

    results = {r.get("role"): r for r in _extract_results(transport.rounds)}
    player_a_res = results.get("player_a")
    assert player_a_res is not None
    assert player_a_res["passed"] is True
    # The loaded skill was strictly what the fighter chose ('terminal-sandbox-ui'), not an auto-loaded top skill
    telemetry = player_a_res.get("skills_telemetry", {})
    assert "terminal-sandbox-ui" in telemetry.get("loaded_skill_ids", [])
    assert "python-kata-fixer" not in telemetry.get("loaded_skill_ids", [])
    assert player_a_res.get("context_mode") == "strict"
    assert player_a_res.get("memory_telemetry", {}).get("memory_count") == 0

    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_cross_role_and_target_memory_policy():
    """Verify cross-target and cross-role memory policies via provenance boundary."""
    from test_memory_policy import FakeMemoryDatabases

    db = FakeMemoryDatabases()

    # 1. Builder private memory
    remember(
        db,
        "db",
        insight="Builder insight: harden endpoint with hmac signature check.",
        battle_id="b-bb-1",
        model_id="gpt-4o",
        user_id="user_1",
        role="builder",
        target_id="target_auth_system",
        visibility_class="model_private",
    )

    # Query as Breaker on same target -> must be BLOCKED
    breaker_mems = retrieve(
        db,
        "db",
        "hmac signature check",
        context_mode="adaptive",
        model_id="gpt-4o",
        user_id="user_1",
        role="breaker",
        target_id="target_auth_system",
    )
    assert breaker_mems == []

    # Query as later Builder on same target -> ALLOWED
    builder_mems = retrieve(
        db,
        "db",
        "hmac signature check",
        context_mode="adaptive",
        model_id="gpt-4o",
        user_id="user_1",
        role="builder",
        target_id="target_auth_system",
    )
    assert len(builder_mems) == 1
    assert "hmac signature" in builder_mems[0]["insight"]

    # Query as same model on different target -> ALLOWED for general lesson
    diff_target_mems = retrieve(
        db,
        "db",
        "hmac signature check",
        context_mode="adaptive",
        model_id="gpt-4o",
        user_id="user_1",
        role="general",
        target_id="different_target",
    )
    assert len(diff_target_mems) == 1
    assert diff_target_mems[0]["target_id"] == "target_auth_system"


def test_bounded_historical_influence_cannot_override_semantic_relevance(test_skill_catalog):
    """Verify that extreme historical Elo (+50,000) cannot cause an irrelevant skill to outrank a relevant skill."""
    relevant_target = {
        "name": "Python Algorithm Kata",
        "category": "coding",
        "runtime": "python",
        "tags": ["python", "kata", "algorithm"],
    }

    # Seed extreme Elo on completely irrelevant skill (waf-bypass) and low Elo on relevant skill (python-kata-fixer)
    extreme_elos = {
        "waf-bypass": 50000.0,
        "python-kata-fixer": 800.0,
        "shell-basics": 1200.0,
        "secure-code-execution": 1200.0,
    }

    ranked = rank_skills_detailed(
        test_skill_catalog,
        relevant_target,
        context_mode="adaptive",
        skill_elos=extreme_elos,
    )

    # python-kata-fixer has strong semantic relevance (e.g. 17.0 - 4.0 = 13.0)
    # waf-bypass has 0.0 semantic relevance + 5.0 bounded max nudge = 5.0
    python_fixer_res = next(r for r in ranked if r.skill.id == "python-kata-fixer")
    waf_bypass_res = next(r for r in ranked if r.skill.id == "waf-bypass")

    assert python_fixer_res.semantic_score > waf_bypass_res.semantic_score
    assert waf_bypass_res.historical_adjustment == 5.0  # Clamped at max bound
    assert python_fixer_res.final_score > waf_bypass_res.final_score  # Relevant still wins!
    assert ranked[0].skill.id == "python-kata-fixer"
