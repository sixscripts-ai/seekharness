"""D0 catalog metadata on the Change Set B SkillRecord identity (hermetic)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from agent_arena.skills import (
    CATALOG_VERSION,
    CanonicalSkillResolver,
    CatalogValidationError,
    SkillRecord,
    load_canonical_catalog,
    parse_skill_text,
    validate_catalog_documents,
)
from agent_arena.sandbox.executors.skill_pool import BATTLE_SKILL_NAMES, load_skill


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / ".agents" / "skills"

_EXISTING_VERSIONS = {
    "secure-code-execution": "2.0.0",
    "sandbox-runtime-engineer": "2.0.0",
    "artifact-workspace-versioning": "2.0.0",
    "realtime-execution-streaming": "2.0.0",
    "battle-runtime-observability": "2.0.0",
    "terminal-sandbox-ui": "2.0.0",
    "python-kata-fixer": "0.1.0",
}


def _raw_docs():
    package = ROOT / "backend" / "agent_arena" / "skills"
    catalog = yaml.safe_load((package / "catalog.v0.3.yaml").read_text())
    graph = yaml.safe_load((package / "graph.v0.3.yaml").read_text())
    return catalog, graph


def test_frozen_catalog_loads_63_unique_skill_records_and_valid_indexes():
    catalog = load_canonical_catalog()
    assert catalog.version == CATALOG_VERSION
    assert len(catalog.skills) == 63
    assert len(catalog.by_id) == 63
    assert len({skill.id for skill in catalog.skills}) == 63
    assert all(isinstance(skill, SkillRecord) for skill in catalog.skills)
    assert len(catalog.graph_indexes) == 65
    assert validate_catalog_documents(*_raw_docs()) == ()
    for skill in catalog.skills:
        assert skill.indexes
        assert set(skill.indexes).issubset(catalog.graph_indexes)
        for related in skill.related_skills:
            assert catalog.get(related) is not None
        for foundation in skill.suggested_foundations:
            assert catalog.get(foundation) is not None
        assert set(skill.discovery) == {"strong", "normal", "weak"}
        assert all(skill.discovery[bucket] for bucket in ("strong", "normal", "weak"))


def test_existing_fighter_versions_are_unchanged():
    catalog = load_canonical_catalog()
    assert {skill_id: catalog.require(skill_id).version for skill_id in _EXISTING_VERSIONS} == (
        _EXISTING_VERSIONS
    )
    for skill_id, version in _EXISTING_VERSIONS.items():
        loaded = load_skill(skill_id, SKILLS_ROOT)
        assert loaded["version"] == version
        record = SkillRecord.from_dict(loaded)
        assert record.id == skill_id
        assert record.version == version


def test_existing_seven_resolve_through_change_set_b_apis():
    catalog = load_canonical_catalog()
    loaded = [load_skill(skill_id, SKILLS_ROOT) for skill_id in BATTLE_SKILL_NAMES]
    resolver = CanonicalSkillResolver([SkillRecord.from_dict(item) for item in loaded])
    for skill_id in BATTLE_SKILL_NAMES:
        body_path = SKILLS_ROOT / skill_id / "SKILL.md"
        parsed = parse_skill_text(body_path.read_text(encoding="utf-8"), name=skill_id)
        assert parsed.id == skill_id
        resolved = resolver.resolve(skill_id)
        assert resolved is not None
        assert resolved.id == skill_id
        assert resolved.version == _EXISTING_VERSIONS[skill_id]
        assert resolved.summary == catalog.require(skill_id).summary
        assert resolved.schema_version == 2


def test_overlay_attaches_v03_fields_without_dropping_legacy_keys():
    loaded = load_skill("secure-code-execution", SKILLS_ROOT)
    assert loaded["id"] == "secure-code-execution"
    assert loaded["schema_version"] == 2
    assert loaded["version"] == "2.0.0"
    assert loaded["summary"]
    assert loaded["indexes"][0] == "runtime/execution"
    assert loaded["roles"]
    assert loaded["runtimes"]
    assert loaded["domains"]
    assert set(loaded["discovery"]) == {"strong", "normal", "weak"}
    assert loaded["discovery"]["strong"]
    assert loaded["visibility"] == "public"
    assert isinstance(loaded["benchmark_safe"], bool)
    assert "tier" in loaded
    assert "category" in loaded
    assert "tags" in loaded
    assert "prerequisites" in loaded
    assert "capabilities" in loaded
    assert loaded["body"]


def test_affinity_does_not_grant_legacy_capabilities():
    skill = load_canonical_catalog().require("technical-web-researcher")
    assert isinstance(skill, SkillRecord)
    assert skill.capability_affinity == ["web_research"]
    assert skill.capabilities == []
    assert skill.prerequisites == []
    payload = skill.to_dict()
    assert "capability_requirements" not in payload


def test_validator_rejects_duplicate_ids_and_dangling_relationships():
    catalog, graph = _raw_docs()
    broken = deepcopy(catalog)
    duplicate = deepcopy(broken["skills"][0])
    broken["skills"].append(duplicate)
    broken["canonical_skill_count"] += 1
    broken["skills"][1]["related_skills"].append("not-a-real-skill")
    errors = validate_catalog_documents(broken, graph)
    assert any("duplicate canonical skill ids" in e for e in errors)
    assert any("dangling related skill" in e for e in errors)


def test_validator_rejects_unknown_index_and_permission_like_fields():
    catalog, graph = _raw_docs()
    broken = deepcopy(catalog)
    skill = broken["skills"][0]
    skill["indexes"].append("private/hidden-answer")
    skill["prerequisites"] = ["evidence-before-editing"]
    skill["capability_requirements"] = ["web_research"]
    errors = validate_catalog_documents(broken, graph)
    assert any("unknown graph index" in e for e in errors)
    assert any("forbidden canonical field 'prerequisites'" in e for e in errors)
    assert any("forbidden canonical field 'capability_requirements'" in e for e in errors)


def test_validator_rejects_empty_or_cross_bucket_duplicate_discovery_signals():
    catalog, graph = _raw_docs()
    broken = deepcopy(catalog)
    discovery = broken["skills"][0]["discovery"]
    discovery["weak"] = []
    discovery["normal"].append(discovery["strong"][0])
    errors = validate_catalog_documents(broken, graph)
    assert any("discovery.weak must not be empty" in e for e in errors)
    assert any("discovery signals repeated across buckets" in e for e in errors)


def test_explicit_invalid_catalog_raises_structured_validation_error(tmp_path):
    catalog, graph = _raw_docs()
    catalog = deepcopy(catalog)
    catalog["skills"][0]["visibility"] = "hidden"
    cpath = tmp_path / "catalog.yaml"
    gpath = tmp_path / "graph.yaml"
    cpath.write_text(yaml.safe_dump(catalog, sort_keys=False))
    gpath.write_text(yaml.safe_dump(graph, sort_keys=False))
    try:
        load_canonical_catalog(cpath, gpath)
    except CatalogValidationError as exc:
        assert any("invalid visibility" in e for e in exc.errors)
    else:  # pragma: no cover
        raise AssertionError("expected CatalogValidationError")
