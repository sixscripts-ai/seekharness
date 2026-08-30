"""D3 capability-separation tests.

These tests verify that Skill Graph affinity is advisory metadata and does not
grant or change Arena capability/tool policy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_arena.sandbox.executors.advanced_executor import ToolSession
from agent_arena.skills.discovery import (
    skill_capability_affinity,
    search_skills,
    inspect_skill_card,
)
from agent_arena.skills import SkillRecord, load_skill_graph
from agent_arena.skills.canonical_metadata import canonical_catalog_path


def test_technical_web_researcher_exposes_advisory_web_research_affinity():
    assert skill_capability_affinity("technical-web-researcher") == ("web_research",)


def test_skill_without_affinity_exposes_empty_tuple():
    graph = load_skill_graph()
    skill = next(skill for skill in graph.all_skills() if not skill.capability_affinity)

    assert skill_capability_affinity(skill.id) == ()


def test_affinity_metadata_cannot_mutate_arena_capabilities():
    session = ToolSession(Path("."), allow_network=False)
    before = session.allow_network

    affinity = skill_capability_affinity("technical-web-researcher")

    assert affinity == ("web_research",)
    assert session.allow_network is before is False
    assert not hasattr(session, "capabilities")


def test_discovery_works_when_associated_capability_is_disabled():
    session = ToolSession(Path("."), allow_network=False)

    result = search_skills("web research")
    card = inspect_skill_card("technical-web-researcher")

    assert result.results
    assert any(item.id == "technical-web-researcher" for item in result.results)
    assert card.card is not None
    assert card.card.capability_affinity == ("web_research",)
    assert session.allow_network is False


def test_direct_skill_inspection_succeeds_when_capability_is_disabled():
    card = inspect_skill_card("technical-web-researcher")

    assert card.card is not None
    assert card.card.id == "technical-web-researcher"
    assert card.card.capability_affinity == ("web_research",)


def test_skill_loading_succeeds_when_capability_is_disabled(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "technical-web-researcher"
    skill_dir.mkdir(parents=True)
    body = "---\nname: technical-web-researcher\ndescription: test\n---\nbody\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")

    session = ToolSession(tmp_path, allow_network=False)
    result = session.use_skill("technical-web-researcher")

    assert result.success is True
    assert result.output == body
    assert session.allow_network is False


def test_actual_network_capability_remains_denied_by_existing_arena_policy(
    tmp_path: Path,
):
    session = ToolSession(tmp_path, allow_network=False)

    result = session.shell("curl https://example.com", count_step=False)

    assert result.success is False
    assert result.policy_rejected is True
    assert result.error_type == "policy_rejection"
    assert (
        "network" in result.output.lower() or "network" in (result.error or "").lower()
    )


def test_unavailable_capability_does_not_hide_skill_from_discovery():
    result = search_skills("web research")

    assert any(item.id == "technical-web-researcher" for item in result.results)


def test_d3_uses_no_network_or_provider_key(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("D3 discovery must not make network requests")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert skill_capability_affinity("technical-web-researcher") == ("web_research",)
    assert inspect_skill_card("technical-web-researcher").card is not None


def test_no_permission_granting_fields_added_to_canonical_metadata():
    graph = load_skill_graph()

    forbidden = {"prerequisites", "capability_requirements", "permissions", "grants"}
    catalog_doc = yaml.safe_load(canonical_catalog_path().read_text(encoding="utf-8"))
    for raw_skill in catalog_doc["skills"]:
        assert forbidden.isdisjoint(raw_skill)
        assert "capability_affinity" in raw_skill

    # Legacy fields remain part of SkillRecord for Change Set B compatibility,
    # but D0 metadata never populates them or treats them as grants.
    for skill in graph.all_skills():
        assert skill.capabilities == []
        assert skill.prerequisites == []


def test_affinity_helper_returns_immutable_copy():
    affinity = skill_capability_affinity("technical-web-researcher")

    assert isinstance(affinity, tuple)
    with pytest.raises(TypeError):
        affinity[0] = "granted"  # type: ignore


def test_skill_record_remains_single_identity_type():
    skill = load_skill_graph().require_skill("technical-web-researcher")

    assert isinstance(skill, SkillRecord)
    assert not type(skill).__name__.lower().endswith("capability")
