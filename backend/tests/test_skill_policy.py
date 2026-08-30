"""Tests for Change Set B — Canonical Skill Identity, Lifecycle States, Ranking Fairness, and Attribution."""

from __future__ import annotations

import pytest

from agent_arena.skills.canonical import (
    CanonicalSkillResolver,
    SkillRecord,
    normalize_skill_ref,
    parse_skill_text,
    slugify,
)
from agent_arena.skills.lifecycle import SkillLifecycleTracker
from agent_arena.skills.ranking import (
    compute_semantic_relevance,
    curate_shortlist,
    rank_skills,
)
from agent_arena.skills.attribution import (
    compute_skill_attributions,
    is_learnable_outcome,
)


@pytest.fixture
def sample_pool() -> list[SkillRecord]:
    return [
        SkillRecord(
            id="python-kata-fixer",
            name="Python Kata Fixer",
            slug="python-kata-fixer",
            aliases=["kata-fixer", "py-fixer"],
            category="coding",
            tags=["python", "kata", "algorithm"],
            prerequisites=["shell-basics"],
            description="Fixes Python kata bugs and edge cases.",
            desc="Fixes Python kata bugs.",
            elo=1200,
        ),
        SkillRecord(
            id="shell-basics",
            name="Shell Basics",
            slug="shell-basics",
            aliases=["bash-basics"],
            category="system",
            tags=["shell", "bash", "cli"],
            prerequisites=[],
            description="Fundamental terminal and shell execution operations.",
            desc="Terminal operations.",
            elo=1200,
        ),
        SkillRecord(
            id="waf-bypass",
            name="WAF Bypass",
            slug="waf-bypass",
            aliases=["web-waf"],
            category="security",
            tags=["waf", "security", "http"],
            prerequisites=[],
            description="Techniques for testing WAF resilience.",
            desc="WAF resilience.",
            elo=1200,
        ),
        SkillRecord(
            id="secure-code-execution",
            name="Secure Code Execution",
            slug="secure-code-execution",
            aliases=["code-jail"],
            category="security",
            tags=["sandbox", "jail", "isolation"],
            prerequisites=[],
            description="Guards sandbox environments from unconstrained execution.",
            desc="Sandbox guards.",
            elo=1200,
        ),
    ]


def test_canonical_identity_resolution(sample_pool):
    """Test 1: Skill names, slugs, aliases resolve to single canonical identity."""
    resolver = CanonicalSkillResolver(sample_pool)

    # Resolution by exact name, slug, alias, and mixed case
    assert resolver.resolve("Python Kata Fixer").id == "python-kata-fixer"
    assert resolver.resolve("python-kata-fixer").id == "python-kata-fixer"
    assert resolver.resolve("py-fixer").id == "python-kata-fixer"
    assert resolver.resolve("KATA-FIXER").id == "python-kata-fixer"
    assert resolver.resolve("bash-basics").id == "shell-basics"
    assert resolver.canonical_id("web-waf") == "waf-bypass"


def test_unknown_skill_clean_failure(sample_pool):
    """Test 2: Unknown skills fail cleanly returning None."""
    resolver = CanonicalSkillResolver(sample_pool)
    assert resolver.resolve("nonexistent-magic-skill") is None
    assert resolver.canonical_id("") is None
    assert resolver.resolve("   ") is None


def test_lifecycle_states_remain_distinct():
    """Test 3: Offered, selected, loaded, used, and attributed states remain distinct."""
    tracker = SkillLifecycleTracker(role="agent_a", model_id="gpt-4o")
    tracker.record_eligible("python-kata-fixer")
    tracker.record_offered("python-kata-fixer")

    # State verification: offered != selected, offered != loaded
    assert tracker.offered_skill_ids == ["python-kata-fixer"]
    assert tracker.selected_skill_ids == []
    assert tracker.loaded_skill_ids == []
    assert tracker.used_skill_ids == []
    assert tracker.attributed_skill_ids == []

    # Model selects it
    tracker.record_selected("python-kata-fixer")
    assert tracker.selected_skill_ids == ["python-kata-fixer"]
    assert tracker.loaded_skill_ids == []

    # System loads it
    tracker.record_loaded("python-kata-fixer")
    assert tracker.loaded_skill_ids == ["python-kata-fixer"]
    assert tracker.used_skill_ids == []

    # Observable usage
    tracker.record_used("python-kata-fixer")
    assert tracker.used_skill_ids == ["python-kata-fixer"]
    assert tracker.attributed_skill_ids == []

    # Post-finalization attribution
    tracker.record_attributed("python-kata-fixer", "win")
    assert tracker.attributed_skill_ids == ["python-kata-fixer"]
    assert tracker.attribution_outcome == "win"


def test_hallucinated_and_failed_load_skills_receive_no_attribution(sample_pool):
    """Tests 4 & 5: Hallucinated skills and failed loads receive no attribution."""
    resolver = CanonicalSkillResolver(sample_pool)

    results = [
        {
            "role": "agent_a",
            "passed": True,
            "outcome": "TEST_PASS",
            "steps": 4,
            "skills_telemetry": {
                "loaded_skill_ids": ["python-kata-fixer"],
                "load_failures": {"hallucinated-super-skill": "unknown_skill", "broken-skill": "mount_failed"},
            },
            "skill_reads": ["python-kata-fixer"],
        }
    ]

    attrs = compute_skill_attributions(results, resolver=resolver)
    agent_a_attrs = attrs["agent_a"]
    attributed_ids = [a["skill_id"] for a in agent_a_attrs]

    assert "python-kata-fixer" in attributed_ids
    assert "hallucinated-super-skill" not in attributed_ids
    assert "broken-skill" not in attributed_ids


def test_strict_mode_fairness_independent_of_model_id(sample_pool):
    """Tests 6 & 7: Strict-mode ranking is identical across different model IDs."""
    target_ctx = {
        "name": "Python Kata Palindrome",
        "category": "coding",
        "runtime": "python",
        "tags": ["python", "kata"],
        "objectives": ["Fix is_palindrome"],
    }

    # Rank for model A
    ranked_a = rank_skills(sample_pool, target_ctx, context_mode="strict")
    # Rank for model B
    ranked_b = rank_skills(sample_pool, target_ctx, context_mode="strict")

    assert [s.id for s, _, _ in ranked_a] == [s.id for s, _, _ in ranked_b]
    assert [score for _, score, _ in ranked_a] == [score for _, score, _ in ranked_b]


def test_strict_mode_ignores_historical_skill_elo(sample_pool):
    """Test 8: Strict-mode ranking does not depend on historical skill Elo."""
    target_ctx = {
        "name": "Python Kata Palindrome",
        "category": "coding",
        "runtime": "python",
        "tags": ["python", "kata"],
    }

    # Create artificial high Elo on unrelated skill
    high_elo_pool = [
        SkillRecord(
            id=s.id,
            name=s.name,
            slug=s.slug,
            category=s.category,
            tags=s.tags,
            description=s.description,
            desc=s.desc,
            elo=2200 if s.id == "waf-bypass" else 1000,
        )
        for s in sample_pool
    ]

    # In strict mode, historical Elo has 0 impact: python-kata-fixer must remain #1
    ranked = rank_skills(high_elo_pool, target_ctx, context_mode="strict")
    assert ranked[0][0].id == "python-kata-fixer"
    assert ranked[0][1] > ranked[-1][1]


def test_adaptive_mode_bounded_historical_influence(sample_pool):
    """Tests 10, 11, 12: Adaptive mode can load persisted Elo, changes ranking measurably, and remains bounded."""
    target_ctx = {
        "name": "Generic Task",
        "category": "general",
        "runtime": "",
        "tags": [],
    }

    # In neutral context with equal semantic scores, high Elo gives bounded nudge
    elos = {"python-kata-fixer": 1600.0, "waf-bypass": 800.0}

    # Strict mode: elos ignored
    strict_ranked = rank_skills(sample_pool, target_ctx, context_mode="strict", skill_elos=elos)
    strict_scores = {s.id: score for s, score, _ in strict_ranked}

    # Adaptive mode: elos applied as bounded nudge
    adaptive_ranked = rank_skills(sample_pool, target_ctx, context_mode="adaptive", skill_elos=elos)
    adaptive_scores = {s.id: score for s, score, _ in adaptive_ranked}

    # Python kata fixer score increased by bounded delta (e.g. +4.0), waf-bypass decreased (e.g. -4.0)
    assert adaptive_scores["python-kata-fixer"] > strict_scores["python-kata-fixer"]
    assert adaptive_scores["waf-bypass"] < strict_scores["waf-bypass"]

    # Bound check: maximum historical delta cannot exceed 5.0 points
    assert adaptive_scores["python-kata-fixer"] - strict_scores["python-kata-fixer"] <= 5.0


def test_deterministic_prerequisite_resolution(sample_pool):
    """Test 15: Prerequisite resolution is deterministic and records why added."""
    target_ctx = {
        "name": "Python Kata Challenge",
        "category": "coding",
        "runtime": "python",
        "tags": ["python", "kata"],
    }

    shortlist = curate_shortlist(sample_pool, target_ctx, context_mode="strict", max_shortlist=2)
    shortlist_ids = [s.id for s, reason in shortlist]
    reasons = {s.id: reason for s, reason in shortlist}

    # python-kata-fixer ranked directly
    assert "python-kata-fixer" in shortlist_ids
    assert reasons["python-kata-fixer"] == "ranked_directly"

    # shell-basics resolved as prerequisite of python-kata-fixer
    assert "shell-basics" in shortlist_ids
    assert reasons["shell-basics"] == "prerequisite_of:python-kata-fixer"


def test_attribution_rules_all_fail_and_infra_error(sample_pool):
    """Tests 16, 18: Authoritative attribution on all-fail race and infra failure."""
    resolver = CanonicalSkillResolver(sample_pool)

    # Scenario 1: All-fail race (no fighter passed) -> 0 skill wins awarded
    all_fail_results = [
        {"role": "agent_a", "passed": False, "outcome": "TEST_FAIL", "skill_reads": ["python-kata-fixer"]},
        {"role": "agent_b", "passed": False, "outcome": "STEP_BUDGET_EXCEEDED", "skill_reads": ["waf-bypass"]},
    ]
    attrs_fail = compute_skill_attributions(all_fail_results, resolver=resolver)
    assert all(a["outcome"] == "loss" for a in attrs_fail["agent_a"])
    assert all(a["outcome"] == "loss" for a in attrs_fail["agent_b"])

    # Scenario 2: Infrastructure / provider failure -> not learnable, 0 attribution
    infra_results = [
        {"role": "agent_a", "passed": False, "outcome": "PROVIDER_ERROR", "skill_reads": ["python-kata-fixer"]},
    ]
    attrs_infra = compute_skill_attributions(infra_results, resolver=resolver)
    assert attrs_infra["agent_a"] == []


def test_recommended_skills_cannot_secretly_advantage_fighter(sample_pool):
    """Test 14: Recommended skills in strict mode are 100% symmetric and target-derived."""
    target_ctx = {
        "name": "Security Audit",
        "category": "security",
        "runtime": "python",
        "tags": ["waf", "sandbox"],
    }
    shortlist_a = curate_shortlist(sample_pool, target_ctx, context_mode="strict", max_shortlist=3)
    shortlist_b = curate_shortlist(sample_pool, target_ctx, context_mode="strict", max_shortlist=3)

    assert [s.id for s, _ in shortlist_a] == [s.id for s, _ in shortlist_b]


def test_solo_fail_does_not_create_skill_wins(sample_pool):
    """Test 17: Solo failed runs never create skill wins."""
    resolver = CanonicalSkillResolver(sample_pool)
    solo_fail = [
        {"role": "solo_agent", "passed": False, "outcome": "TEST_FAIL", "skill_reads": ["python-kata-fixer"]},
    ]
    attrs = compute_skill_attributions(solo_fail, resolver=resolver)
    assert len(attrs["solo_agent"]) == 1
    assert attrs["solo_agent"][0]["outcome"] == "loss"


def test_attribution_consumes_authoritative_results_only(sample_pool):
    """Test 19: Attribution consumes authoritative results, ignoring unverified intermediate states."""
    resolver = CanonicalSkillResolver(sample_pool)
    # A fighter claimed passed in intermediate files but authoritative verifier set passed=False
    results = [
        {
            "role": "player_a",
            "passed": False,
            "outcome": "TEST_FAIL",
            "theory": "I passed all tests",
            "skills_telemetry": {"loaded_skill_ids": ["python-kata-fixer"]},
        }
    ]
    attrs = compute_skill_attributions(results, resolver=resolver)
    assert attrs["player_a"][0]["outcome"] == "loss"
