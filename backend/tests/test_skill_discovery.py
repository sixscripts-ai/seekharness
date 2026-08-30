"""D2 fighter discovery API tests (hermetic and model-independent)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_arena.sandbox.executors.advanced_executor import ToolSession
from agent_arena.skills import (
    CompactSkillCard,
    DiscoveryErrorView,
    DiscoveryRequestError,
    IndexDiscoveryView,
    RootDiscoveryView,
    SkillDiscoveryView,
    SkillRecord,
    UnknownIndexError,
    UnknownSkillError,
    browse_index,
    browse_roots,
    discover_skills,
    format_discovery_text,
    inspect_skill_card,
    load_skill_graph,
    score_skill_for_query,
    search_skills,
)


def test_skills_root_view_returns_all_13_roots_deterministically():
    graph = load_skill_graph()
    first = browse_roots(graph)
    second = browse_roots(graph)

    assert isinstance(first, RootDiscoveryView)
    assert len(first.roots) == 13
    assert first.roots == second.roots
    assert [root.path for root in first.roots] == list(graph.root_indexes())
    assert first.total_skills == 63
    assert first.total_indexes == 65
    assert all(root.description for root in first.roots)


def test_security_index_view_has_metadata_direct_children_and_compact_cards():
    graph = load_skill_graph()
    view = browse_index("security", graph)

    assert isinstance(view, IndexDiscoveryView)
    assert view.index_path == "security"
    assert view.is_root is True
    assert view.description
    assert view.direct_children == graph.child_indexes("security")
    assert len(view.direct_children) == 10
    assert view.skills
    assert all(isinstance(card, CompactSkillCard) for card in view.skills)
    assert all(
        card.id in {skill.id for skill in graph.skills_in_index("security")}
        for card in view.skills
    )


def test_nested_index_browsing_works():
    view = browse_index("security/authentication")

    assert view.index_path == "security/authentication"
    assert view.is_root is False
    assert view.parent == "security"
    assert view.direct_children == ()
    assert {card.id for card in view.skills} == {
        "auth-flow-debugger",
        "session-replay-attacker",
    }


def test_skill_cards_never_contain_full_skill_body_text():
    graph = load_skill_graph()
    card_view = inspect_skill_card("auth-flow-debugger", graph)
    card = card_view.card

    assert isinstance(card_view, SkillDiscoveryView)
    assert card is not None
    assert card.id == "auth-flow-debugger"
    assert not hasattr(card, "body")
    assert "body" not in card.to_dict()
    assert "path" not in card.to_dict()
    assert graph.require_skill("auth-flow-debugger").body == ""

    serialized = format_discovery_text(card_view)
    assert "SKILL.md" not in serialized
    assert "body" not in serialized.lower()


def test_auth_flow_debugger_returns_expected_canonical_card():
    card = inspect_skill_card("auth-flow-debugger").card

    assert card is not None
    assert card.id == "auth-flow-debugger"
    assert card.summary
    assert card.indexes == (
        "backend/authentication",
        "security/authentication",
        "debugging/state",
    )
    assert card.roles
    assert card.runtimes
    assert card.domains
    assert card.context_cost_class in {"small", "medium", "large"}
    assert isinstance(card.related_skills, tuple)
    assert isinstance(card.suggested_foundations, tuple)
    assert isinstance(card.capability_affinity, tuple)


def test_use_skill_works_without_prior_discovery_call(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "auth-flow-debugger"
    skill_dir.mkdir(parents=True)
    body = "---\nname: auth-flow-debugger\ndescription: test\n---\n# private body\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")

    session = ToolSession(tmp_path)
    result = session.use_skill("auth-flow-debugger")

    assert result.success is True
    assert result.output == body
    assert session.skill_reads == {"auth-flow-debugger"}


def test_search_is_deterministic_and_returns_compact_cards():
    first = search_skills("authentication session token")
    second = search_skills("authentication session token")

    assert first == second
    assert first.query == "authentication session token"
    assert first.results
    assert all(isinstance(card, CompactSkillCard) for card in first.results)
    assert all("body" not in card.to_dict() for card in first.results)


def test_strong_discovery_matches_outrank_normal_matches():
    strong = score_skill_for_query(
        "experiment", load_skill_graph().require_skill("hypothesis-driven-debugging")
    )
    normal = score_skill_for_query(
        "experiment", load_skill_graph().require_skill("minimal-reproduction-builder")
    )

    assert strong > normal
    assert search_skills("experiment").results[0].id == "hypothesis-driven-debugging"


def test_normal_discovery_matches_outrank_weak_matches():
    graph = load_skill_graph()
    normal_skill = SkillRecord(
        id="kata-helper",
        name="kata-helper",
        slug="kata-helper",
        summary="A helper",
        visibility="public",
        discovery={"strong": ["unrelated"], "normal": ["python"], "weak": ["other"]},
    )
    normal = score_skill_for_query("python", normal_skill)
    # Runtime and weak discovery are intentionally low-weight. The search still
    # finds this skill, but a normal signal must dominate a weak-only match.
    weak_only = SkillRecord(
        id="language-helper",
        name="language-helper",
        slug="language-helper",
        summary="Generic helper",
        runtimes=["python"],
        visibility="public",
        discovery={"strong": ["unrelated"], "normal": ["helper"], "weak": ["python"]},
    )
    weak_score = score_skill_for_query("python", weak_only)
    assert normal > weak_score


def test_generic_python_does_not_overpromote_specialist_over_kata_query():
    graph = load_skill_graph()
    python_score = score_skill_for_query(
        "python", graph.require_skill("python-kata-fixer")
    )
    kata_score = score_skill_for_query(
        "python kata", graph.require_skill("python-kata-fixer")
    )

    assert python_score < kata_score
    assert search_skills("python kata").results[0].id == "python-kata-fixer"


def test_kata_specific_search_promotes_python_kata_fixer():
    result = search_skills("algorithm exercise small harness")

    assert result.results
    assert result.results[0].id == "python-kata-fixer"


def test_exact_canonical_skill_id_search_is_first():
    result = search_skills("auth-flow-debugger")

    assert result.results[0].id == "auth-flow-debugger"


def test_public_visibility_filtering_works():
    graph = load_skill_graph()
    public_skill = graph.require_skill("auth-flow-debugger")
    hidden_skill = SkillRecord(
        id="hidden-skill",
        name="hidden-skill",
        slug="hidden-skill",
        summary="must not appear",
        visibility="private",
        discovery={"strong": ["secret"], "normal": ["hidden"], "weak": ["skill"]},
    )

    assert score_skill_for_query("secret", hidden_skill) == 0.0
    assert score_skill_for_query("authentication", public_skill) > 0.0
    assert "must not appear" not in format_discovery_text(search_skills("secret"))


def test_unknown_index_returns_structured_failure():
    with pytest.raises(UnknownIndexError):
        discover_skills(index="not/a/real/index")

    session = ToolSession(Path("."))
    result = session.skills(index="not/a/real/index")
    assert result.success is False
    assert result.error_type == "unknown_index"
    assert "not/a/real/index" in result.output


def test_unknown_skill_returns_structured_failure():
    with pytest.raises(UnknownSkillError):
        discover_skills(skill="not-a-real-skill")

    session = ToolSession(Path("."))
    result = session.skills(skill="not-a-real-skill")
    assert result.success is False
    assert result.error_type == "unknown_skill"
    assert "not-a-real-skill" in result.output


def test_empty_and_invalid_search_behavior_is_explicit():
    empty = search_skills("   ")
    assert empty.query == ""
    assert empty.results == ()
    assert "empty query" in format_discovery_text(empty)

    with pytest.raises(DiscoveryRequestError):
        discover_skills(index="security", search="auth")
    with pytest.raises(DiscoveryRequestError):
        discover_skills(skill="")

    session = ToolSession(Path("."))
    result = session.skills(index="security", search="auth")
    assert result.success is False
    assert result.error_type == "invalid_request"


def test_browsing_and_card_inspection_do_not_mark_skill_loaded(tmp_path: Path):
    session = ToolSession(tmp_path)
    before = set(session.skill_reads)

    browse_result = session.skills(index="security/authentication")
    card_result = session.skills(skill="auth-flow-debugger")

    assert browse_result.success is True
    assert card_result.success is True
    assert session.skill_reads == before == set()


def test_d1_graph_access_remains_unchanged_and_deterministic():
    graph = load_skill_graph()
    assert graph.root_indexes() == (
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
    assert len(graph.all_skills()) == 63
    assert len(graph.all_indexes()) == 65
    assert graph.indexes_for_skill("secure-code-execution") == (
        "runtime/execution",
        "runtime/sandboxes",
        "security/code-execution",
        "security/trust-boundaries",
    )


def test_existing_seven_fighter_skill_loading_still_works():
    versions = {
        "secure-code-execution": "2.0.0",
        "sandbox-runtime-engineer": "2.0.0",
        "artifact-workspace-versioning": "2.0.0",
        "realtime-execution-streaming": "2.0.0",
        "battle-runtime-observability": "2.0.0",
        "terminal-sandbox-ui": "2.0.0",
        "python-kata-fixer": "0.1.0",
    }
    graph = load_skill_graph()
    for skill_id, version in versions.items():
        skill = graph.require_skill(skill_id)
        assert isinstance(skill, SkillRecord)
        assert skill.version == version


def test_no_target_model_history_input_affects_lexical_search():
    import inspect

    signature = inspect.signature(search_skills)
    assert {"target_id", "model_id", "battle_id", "history"}.isdisjoint(
        signature.parameters
    )
    assert search_skills("authentication") == search_skills("authentication")


def test_no_d3_recommendation_behavior_exists():
    import agent_arena.skills.discovery as discovery

    assert not hasattr(discovery, "recommend_skills")
    assert not hasattr(discovery, "suggest_entry_points")
    assert not hasattr(discovery, "deduplicate_context")
    assert not hasattr(discovery, "record_navigation")


def test_tool_protocol_exposes_discovery_arguments_and_preserves_legacy_selection():
    from agent_arena.tool_protocol import TOOL_SCHEMAS, normalize_response

    skills_schema = next(
        item["function"]
        for item in TOOL_SCHEMAS
        if item["function"]["name"] == "skills"
    )
    properties = skills_schema["parameters"]["properties"]
    assert {"index", "search", "skill", "list", "chosen"}.issubset(properties)

    parsed = normalize_response(
        '[{"tool":"skills","arguments":{"index":"security/authentication"}}]'
    )
    assert parsed.calls[0].name == "skills"
    assert parsed.calls[0].arguments == {"index": "security/authentication"}

    session = ToolSession(Path("."))
    legacy = session.skills(chosen=["secure-code-execution"], count_step=False)
    assert legacy.success is True
    assert legacy.output == "SKILLS_CHOSEN secure-code-execution"


def test_error_view_serializes_without_private_data():
    error = DiscoveryErrorView(
        error="unknown skill",
        error_type="unknown_skill",
        requested="private-id",
    )
    data = error.to_dict()
    assert data == {
        "view_type": "error",
        "error": "unknown skill",
        "error_type": "unknown_skill",
        "requested": "private-id",
    }


def test_root_discovery_response_is_compact():
    payload = browse_roots().to_dict()

    assert set(payload) == {
        "view_type",
        "roots",
        "total_skills",
        "total_indexes",
    }
    assert len(payload["roots"]) == 13
    assert all(
        set(root) == {"path", "name", "description", "child_count", "skill_count"}
        for root in payload["roots"]
    )
    assert "skills" not in payload
    assert "body" not in str(payload).lower()


def test_index_discovery_response_is_compact():
    payload = browse_index("security/authentication").to_dict()

    assert set(payload) == {
        "view_type",
        "index_path",
        "name",
        "description",
        "is_root",
        "parent",
        "direct_children",
        "skills",
    }
    assert payload["direct_children"] == []
    assert all("body" not in card and "path" not in card for card in payload["skills"])
    assert "SKILL.md" not in str(payload)


def test_search_response_contains_cap_metadata_and_compact_cards():
    payload = search_skills("debugger").to_dict()

    assert payload["total_matches"] == 16
    assert payload["returned_count"] == 10
    assert payload["truncated"] is True
    assert len(payload["results"]) == 10
    assert all("body" not in card for card in payload["results"])


def test_skill_inspection_response_is_compact():
    payload = inspect_skill_card("auth-flow-debugger").to_dict()

    assert set(payload) == {"view_type", "card"}
    assert payload["card"] is not None
    assert "body" not in payload["card"]
    assert "SKILL.md" not in str(payload)


def test_use_skill_is_the_only_operation_that_exposes_full_body(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "secure-code-execution"
    skill_dir.mkdir(parents=True)
    body = "---\nname: secure-code-execution\ndescription: test\n---\nUNIQUE_FULL_BODY_SENTINEL\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    session = ToolSession(tmp_path)

    loaded = session.use_skill("secure-code-execution")
    root = session.skills(count_step=False)
    index = session.skills(index="security/code-execution", count_step=False)
    search = session.skills(search="secure code", count_step=False)
    card = session.skills(skill="secure-code-execution", count_step=False)

    assert loaded.output == body
    for discovery_result in (root, index, search, card):
        assert "UNIQUE_FULL_BODY_SENTINEL" not in discovery_result.output


def test_repeated_use_skill_does_not_duplicate_body_or_loaded_state(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "secure-code-execution"
    skill_dir.mkdir(parents=True)
    body = "UNIQUE_REPEAT_BODY_SENTINEL"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    session = ToolSession(tmp_path)

    first = session.use_skill("secure-code-execution", count_step=False)
    second = session.use_skill("secure-code-execution", count_step=False)

    assert first.output == body
    assert second.output == "SKILL_ALREADY_LOADED secure-code-execution"
    assert body not in second.output
    assert session.skill_reads == {"secure-code-execution"}


def test_browse_search_and_card_after_loading_do_not_reinject_body(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "secure-code-execution"
    skill_dir.mkdir(parents=True)
    body = "UNIQUE_POST_LOAD_BODY_SENTINEL"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    session = ToolSession(tmp_path)
    session.use_skill("secure-code-execution", count_step=False)

    results = (
        session.skills(index="security/code-execution", count_step=False),
        session.skills(search="secure code", count_step=False),
        session.skills(skill="secure-code-execution", count_step=False),
    )

    assert all(body not in result.output for result in results)
    assert session.skill_reads == {"secure-code-execution"}


def test_two_different_skills_can_both_load(tmp_path: Path):
    for skill_id in ("first-skill", "second-skill"):
        skill_dir = tmp_path / ".agents" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill_id, encoding="utf-8")
    session = ToolSession(tmp_path)

    first = session.use_skill("first-skill", count_step=False)
    second = session.use_skill("second-skill", count_step=False)

    assert first.success is True
    assert second.success is True
    assert session.skill_reads == {"first-skill", "second-skill"}


def test_many_different_skills_are_not_blocked_by_loaded_count(tmp_path: Path):
    skill_ids = [f"skill-{i}" for i in range(8)]
    for skill_id in skill_ids:
        skill_dir = tmp_path / ".agents" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill_id, encoding="utf-8")
    session = ToolSession(tmp_path)

    results = [session.use_skill(skill_id, count_step=False) for skill_id in skill_ids]

    assert all(result.success for result in results)
    assert session.skill_reads == set(skill_ids)


def test_search_cap_is_deterministic_and_reports_total_matches():
    first = search_skills("debugger")
    second = search_skills("debugger")

    assert first == second
    assert first.total_matches == 16
    assert first.returned_count == 10
    assert first.truncated is True
    assert [card.id for card in first.results] == [
        "async-control-flow-debugger",
        "auth-flow-debugger",
        "browser-ui-debugger",
        "build-system-debugger",
        "compiler-linker-debugger",
        "concurrency-race-debugger",
        "database-migration-debugger",
        "frontend-state-debugger",
        "incremental-build-debugger",
        "makefile-debugger",
    ]


def test_search_under_cap_reports_not_truncated():
    result = search_skills("auditor")

    assert result.total_matches == 10
    assert result.returned_count == 10
    assert result.truncated is False


def test_d2_search_ordering_remains_unchanged():
    result = search_skills("python kata")

    assert result.results[0].id == "python-kata-fixer"
    assert result.total_matches == 1
    assert result.returned_count == 1
    assert result.truncated is False
