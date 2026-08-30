"""D1 Skill Graph and Catalog Access Layer tests (hermetic)."""

from __future__ import annotations

import inspect
from pathlib import Path
import pytest

from agent_arena.skills import (
    SkillGraph,
    SkillGraphIndex,
    SkillRecord,
    UnknownIndexError,
    UnknownSkillError,
    all_indexes,
    all_skills,
    child_indexes,
    get_index,
    get_skill,
    indexes_for_skill,
    load_skill_graph,
    related_skills,
    require_index,
    require_skill,
    root_indexes,
    skills_in_index,
    suggested_foundations,
)

ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / ".agents" / "skills"

_EXISTING_FIGHTER_VERSIONS = {
    "secure-code-execution": "2.0.0",
    "sandbox-runtime-engineer": "2.0.0",
    "artifact-workspace-versioning": "2.0.0",
    "realtime-execution-streaming": "2.0.0",
    "battle-runtime-observability": "2.0.0",
    "terminal-sandbox-ui": "2.0.0",
    "python-kata-fixer": "0.1.0",
}

_EXPECTED_ROOTS = (
    "strategy",
    "investigation",
    "debugging",
    "testing",
    "runtime",
    "build",
    "backend",
    "data",
    "security",
    "artifacts",
    "observability",
    "interface",
    "roles",
)


def test_graph_loads_from_real_frozen_d0_assets():
    graph = load_skill_graph()
    assert isinstance(graph, SkillGraph)
    assert graph.catalog is not None
    assert len(graph.roots) == 13
    assert len(graph.indexes) == 78  # 13 roots + 65 sub-indexes
    assert len(graph.all_indexes()) == 65
    assert len(graph.all_skills()) == 63


def test_exactly_63_skills_accessible():
    graph = load_skill_graph()
    skills = graph.all_skills()
    assert len(skills) == 63
    assert len(graph.skills) == 63
    assert len(all_skills()) == 63
    assert all(isinstance(s, SkillRecord) for s in skills)
    unique_ids = {s.id for s in skills}
    assert len(unique_ids) == 63


def test_exactly_65_indexes_accessible():
    graph = load_skill_graph()
    indexes = graph.all_indexes()
    assert len(indexes) == 65
    assert len(all_indexes()) == 65
    assert len(set(indexes)) == 65
    for idx_path in indexes:
        idx = graph.get_index(idx_path)
        assert idx is not None
        assert isinstance(idx, SkillGraphIndex)
        assert idx.path == idx_path
        assert idx.is_root is False
        assert idx.parent is not None


def test_expected_root_indexes_resolve():
    graph = load_skill_graph()
    roots = graph.root_indexes()
    assert roots == _EXPECTED_ROOTS
    assert root_indexes() == _EXPECTED_ROOTS
    assert len(roots) == 13

    for root_name in roots:
        root_idx = graph.get_index(root_name)
        assert root_idx is not None
        assert isinstance(root_idx, SkillGraphIndex)
        assert root_idx.id == root_name
        assert root_idx.name == root_name
        assert root_idx.path == root_name
        assert root_idx.is_root is True
        assert root_idx.parent is None
        assert root_idx.description != ""
        assert len(root_idx.children) > 0
        assert len(root_idx.skills) > 0


def test_security_direct_children_resolve_correctly():
    graph = load_skill_graph()
    sec_children = graph.child_indexes("security")
    assert sec_children == (
        "security/adversarial-instructions",
        "security/attack-surface",
        "security/authentication",
        "security/authorization",
        "security/code-execution",
        "security/filesystem",
        "security/injection",
        "security/input-validation",
        "security/replay",
        "security/trust-boundaries",
    )
    assert child_indexes("security") == sec_children
    assert len(sec_children) == 10

    # Leaf index has no children
    assert graph.child_indexes("security/authentication") == ()
    assert child_indexes("security/authentication") == ()


def test_overlapping_skill_memberships_work():
    graph = load_skill_graph()

    # artifact-workspace-versioning belongs to multiple indexes
    awv_indexes = graph.indexes_for_skill("artifact-workspace-versioning")
    assert "artifacts/handoffs" in awv_indexes
    assert "artifacts/versioning" in awv_indexes
    assert "artifacts/workspaces" in awv_indexes
    assert "runtime/workspaces" in awv_indexes
    assert len(awv_indexes) == 4

    # Both indexes return this skill
    handoffs_skills = [s.id for s in graph.skills_in_index("artifacts/handoffs")]
    versioning_skills = [s.id for s in graph.skills_in_index("artifacts/versioning")]
    assert "artifact-workspace-versioning" in handoffs_skills
    assert "artifact-workspace-versioning" in versioning_skills


def test_auth_flow_debugger_memberships_work():
    graph = load_skill_graph()
    memberships = graph.indexes_for_skill("auth-flow-debugger")
    assert memberships == (
        "backend/authentication",
        "security/authentication",
        "debugging/state",
    )
    assert set(memberships) == {
        "backend/authentication",
        "security/authentication",
        "debugging/state",
    }
    assert indexes_for_skill("auth-flow-debugger") == memberships

    # Verify skill appears in skills_in_index for each
    for idx_path in memberships:
        skills = [s.id for s in graph.skills_in_index(idx_path)]
        assert "auth-flow-debugger" in skills


def test_secure_code_execution_memberships_work():
    graph = load_skill_graph()
    memberships = graph.indexes_for_skill("secure-code-execution")
    assert memberships == (
        "runtime/execution",
        "runtime/sandboxes",
        "security/code-execution",
        "security/trust-boundaries",
    )
    assert indexes_for_skill("secure-code-execution") == memberships

    for idx_path in memberships:
        skills = [s.id for s in graph.skills_in_index(idx_path)]
        assert "secure-code-execution" in skills


def test_indexes_for_skill_returns_complete_canonical_memberships():
    graph = load_skill_graph()
    for skill in graph.all_skills():
        memberships = graph.indexes_for_skill(skill.id)
        assert isinstance(memberships, tuple)
        assert len(memberships) > 0
        assert memberships == tuple(skill.indexes)
        for idx_path in memberships:
            assert graph.get_index(idx_path) is not None
            assert idx_path in graph.all_indexes()


def test_related_skills_resolves_skill_records():
    graph = load_skill_graph()
    for skill in graph.all_skills():
        rel = graph.related_skills(skill.id)
        assert isinstance(rel, tuple)
        assert all(isinstance(r, SkillRecord) for r in rel)
        assert [r.id for r in rel] == list(skill.related_skills)
        assert skill.id not in [r.id for r in rel]

    # Specific check
    rel_auth = related_skills("auth-flow-debugger")
    assert isinstance(rel_auth, tuple)
    assert len(rel_auth) > 0
    assert all(isinstance(s, SkillRecord) for s in rel_auth)


def test_suggested_foundations_resolves_skill_records():
    graph = load_skill_graph()
    for skill in graph.all_skills():
        foundations = graph.suggested_foundations(skill.id)
        assert isinstance(foundations, tuple)
        assert all(isinstance(f, SkillRecord) for f in foundations)
        assert [f.id for f in foundations] == list(skill.suggested_foundations)
        assert skill.id not in [f.id for f in foundations]

    # Specific check for skill with foundation
    skill_with_fnd = next(s for s in graph.all_skills() if s.suggested_foundations)
    fnds = suggested_foundations(skill_with_fnd.id)
    assert len(fnds) == len(skill_with_fnd.suggested_foundations)
    assert all(isinstance(s, SkillRecord) for s in fnds)


def test_foundations_do_not_gate_skill_lookup():
    graph = load_skill_graph()
    # Find all skills with foundations
    skills_with_foundations = [s for s in graph.all_skills() if s.suggested_foundations]
    assert len(skills_with_foundations) > 0

    for skill in skills_with_foundations:
        # get_skill directly resolves without needing foundations loaded/resolved first
        resolved = graph.get_skill(skill.id)
        assert resolved is not None
        assert resolved.id == skill.id
        assert resolved.name == skill.name
        # require_skill works directly
        required = graph.require_skill(skill.id)
        assert required.id == skill.id


def test_unknown_skill_behavior():
    graph = load_skill_graph()

    assert graph.get_skill("unknown-skill-xyz") is None
    assert get_skill("unknown-skill-xyz") is None
    assert get_skill("") is None

    with pytest.raises(UnknownSkillError) as exc_info:
        graph.require_skill("unknown-skill-xyz")
    assert "unknown-skill-xyz" in str(exc_info.value)

    with pytest.raises(KeyError):
        require_skill("unknown-skill-xyz")

    with pytest.raises(UnknownSkillError):
        graph.indexes_for_skill("unknown-skill-xyz")

    with pytest.raises(UnknownSkillError):
        graph.related_skills("unknown-skill-xyz")

    with pytest.raises(UnknownSkillError):
        graph.suggested_foundations("unknown-skill-xyz")


def test_unknown_index_behavior():
    graph = load_skill_graph()

    assert graph.get_index("unknown/index/path") is None
    assert get_index("unknown/index/path") is None
    assert get_index("") is None

    with pytest.raises(UnknownIndexError) as exc_info:
        graph.require_index("unknown/index/path")
    assert "unknown/index/path" in str(exc_info.value)

    with pytest.raises(KeyError):
        require_index("unknown/index/path")

    with pytest.raises(UnknownIndexError):
        graph.child_indexes("unknown/index/path")

    with pytest.raises(UnknownIndexError):
        graph.skills_in_index("unknown/index/path")


def test_ordering_is_deterministic():
    graph1 = load_skill_graph()
    graph2 = load_skill_graph()

    assert graph1.root_indexes() == graph2.root_indexes()
    assert graph1.all_indexes() == graph2.all_indexes()
    assert [s.id for s in graph1.all_skills()] == [s.id for s in graph2.all_skills()]

    for idx_path in graph1.all_indexes():
        assert graph1.child_indexes(idx_path) == graph2.child_indexes(idx_path)
        assert [s.id for s in graph1.skills_in_index(idx_path)] == [
            s.id for s in graph2.skills_in_index(idx_path)
        ]

    for skill in graph1.all_skills():
        assert graph1.indexes_for_skill(skill.id) == graph2.indexes_for_skill(skill.id)
        assert [s.id for s in graph1.related_skills(skill.id)] == [
            s.id for s in graph2.related_skills(skill.id)
        ]
        assert [s.id for s in graph1.suggested_foundations(skill.id)] == [
            s.id for s in graph2.suggested_foundations(skill.id)
        ]


def test_returned_collections_cannot_mutate_shared_graph_state():
    graph = load_skill_graph()

    roots = graph.root_indexes()
    assert isinstance(roots, tuple)
    with pytest.raises(TypeError):
        roots[0] = "corrupted"  # type: ignore

    children = graph.child_indexes("security")
    assert isinstance(children, tuple)
    with pytest.raises(TypeError):
        children[0] = "corrupted"  # type: ignore

    skills = graph.skills_in_index("security/authentication")
    assert isinstance(skills, tuple)
    with pytest.raises(TypeError):
        skills[0] = None  # type: ignore

    indexes = graph.indexes_for_skill("auth-flow-debugger")
    assert isinstance(indexes, tuple)
    with pytest.raises(TypeError):
        indexes[0] = "corrupted"  # type: ignore

    # Mappings cannot be mutated
    with pytest.raises(TypeError):
        graph.roots["new_root"] = "desc"  # type: ignore

    with pytest.raises(TypeError):
        graph.indexes["new_index"] = None  # type: ignore


def test_graph_has_no_target_model_battle_history_dependency():
    sig = inspect.signature(load_skill_graph)
    params = list(sig.parameters.keys())
    assert "battle_id" not in params
    assert "model_id" not in params
    assert "target_id" not in params
    assert "history" not in params

    # Inspect all method signatures on SkillGraph
    for method_name in [
        "get_skill",
        "require_skill",
        "root_indexes",
        "get_index",
        "require_index",
        "child_indexes",
        "skills_in_index",
        "indexes_for_skill",
        "related_skills",
        "suggested_foundations",
    ]:
        method = getattr(SkillGraph, method_name)
        m_params = list(inspect.signature(method).parameters.keys())
        for forbidden in ("battle_id", "model_id", "target_id", "history", "telemetry"):
            assert forbidden not in m_params


def test_all_existing_seven_fighter_skills_still_use_skill_record():
    graph = load_skill_graph()
    for skill_id, expected_version in _EXISTING_FIGHTER_VERSIONS.items():
        skill = graph.get_skill(skill_id)
        assert skill is not None
        assert isinstance(skill, SkillRecord)
        assert skill.id == skill_id
        assert skill.version == expected_version
        assert skill.schema_version == 2
        assert len(skill.indexes) > 0
        assert len(graph.indexes_for_skill(skill_id)) > 0


def test_no_d3_fighter_tool_is_introduced():
    import agent_arena.skills as skills_module

    # D2 discovery is present; D3 recommendations and adaptive behaviors are not.
    exported = dir(skills_module)
    assert "skills" not in exported
    assert "recommend_skills" not in exported
    assert "progressive_disclosure" not in exported
    assert "telemetry" not in exported
    assert "strategy_signature" not in exported


def test_module_level_functions_match_graph_methods():
    graph = load_skill_graph()
    assert get_skill("auth-flow-debugger") == graph.get_skill("auth-flow-debugger")
    assert require_skill("auth-flow-debugger") == graph.require_skill(
        "auth-flow-debugger"
    )
    assert root_indexes() == graph.root_indexes()
    assert get_index("security") == graph.get_index("security")
    assert require_index("security") == graph.require_index("security")
    assert child_indexes("security") == graph.child_indexes("security")
    assert skills_in_index("security/authentication") == graph.skills_in_index(
        "security/authentication"
    )
    assert indexes_for_skill("auth-flow-debugger") == graph.indexes_for_skill(
        "auth-flow-debugger"
    )
    assert related_skills("auth-flow-debugger") == graph.related_skills(
        "auth-flow-debugger"
    )
    assert suggested_foundations("auth-flow-debugger") == graph.suggested_foundations(
        "auth-flow-debugger"
    )
