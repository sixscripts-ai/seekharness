"""Skill Graph v0.3 catalog loader and validator.

D0 only: validate frozen YAML and overlay metadata onto Change Set B
``SkillRecord`` identity. No graph traversal, search, recommendations,
progressive disclosure, or web research.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping
import os
import re

import yaml

from .canonical import SkillRecord, slugify

SCHEMA_VERSION = 2
CATALOG_VERSION = "0.3.0"
_ALLOWED_ROLES = frozenset({"general", "builder", "breaker"})
_ALLOWED_COSTS = frozenset({"small", "medium", "large"})
_ALLOWED_VISIBILITY = frozenset({"public"})
_DISCOVERY_BUCKETS = ("strong", "normal", "weak")
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:+/*-]+$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class CatalogValidationError(ValueError):
    """Raised when the frozen canonical catalog violates the D0 contract."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("invalid canonical skill catalog:\n- " + "\n- ".join(self.errors))


@dataclass(frozen=True, slots=True)
class CanonicalSkillCatalog:
    """Validated v0.3 catalog whose entries are Change Set B SkillRecords."""

    version: str
    skills: tuple[SkillRecord, ...]
    by_id: Mapping[str, SkillRecord]
    graph_indexes: frozenset[str]

    def get(self, skill_id: str) -> SkillRecord | None:
        key = str(skill_id or "").strip()
        return self.by_id.get(key) or self.by_id.get(slugify(key))

    def require(self, skill_id: str) -> SkillRecord:
        skill = self.get(skill_id)
        if skill is None:
            raise KeyError(f"unknown canonical skill: {skill_id}")
        return skill


def _bundled_path(filename: str) -> Path:
    return Path(resources.files(__package__).joinpath(filename))


def canonical_catalog_path() -> Path:
    configured = os.environ.get("ARENA_CANONICAL_SKILL_CATALOG", "").strip()
    return Path(configured) if configured else _bundled_path("catalog.v0.3.yaml")


def canonical_graph_manifest_path() -> Path:
    configured = os.environ.get("ARENA_CANONICAL_SKILL_GRAPH", "").strip()
    return Path(configured) if configured else _bundled_path("graph.v0.3.yaml")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:  # pragma: no cover - parser supplies useful context
        raise CatalogValidationError([f"{path}: invalid YAML: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise CatalogValidationError([f"{path}: root must be a mapping"])
    return raw


def _strings(value: Any, field: str, skill_id: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        errors.append(f"{skill_id}: {field} must be a list")
        return ()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{skill_id}: {field} contains a non-string/empty value")
            continue
        out.append(item.strip())
    if len(out) != len(set(out)):
        errors.append(f"{skill_id}: {field} contains duplicates")
    return tuple(out)


def validate_catalog_documents(
    catalog_doc: Mapping[str, Any],
    graph_doc: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return all D0 validation errors without mutating either document."""
    errors: list[str] = []

    if str(catalog_doc.get("catalog_version") or "") != CATALOG_VERSION:
        errors.append(f"catalog_version must be {CATALOG_VERSION}")
    graph_version = str(graph_doc.get("version") or "")
    if graph_version != CATALOG_VERSION:
        errors.append(f"graph version must be {CATALOG_VERSION}")

    raw_skills = catalog_doc.get("skills")
    if not isinstance(raw_skills, list):
        return tuple(errors + ["catalog skills must be a list"])

    declared_count = catalog_doc.get("canonical_skill_count")
    if declared_count != len(raw_skills):
        errors.append(
            f"canonical_skill_count={declared_count!r} does not match {len(raw_skills)} records"
        )

    graph_indexes_raw = graph_doc.get("indexes")
    if not isinstance(graph_indexes_raw, dict):
        errors.append("graph indexes must be a mapping")
        graph_indexes_raw = {}
    graph_indexes = set(str(k) for k in graph_indexes_raw)

    ids: list[str] = []
    normalized: dict[str, dict[str, tuple[str, ...]]] = {}

    for pos, raw in enumerate(raw_skills):
        if not isinstance(raw, dict):
            errors.append(f"skill[{pos}] must be a mapping")
            continue
        skill_id = str(raw.get("id") or f"<skill-{pos}>")
        ids.append(skill_id)

        if raw.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{skill_id}: schema_version must be {SCHEMA_VERSION}")
        if not _ID_RE.fullmatch(skill_id):
            errors.append(f"{skill_id}: id must be canonical kebab-case")
        if raw.get("name") != skill_id:
            errors.append(f"{skill_id}: name must equal canonical id")
        if not _SEMVER_RE.fullmatch(str(raw.get("version") or "")):
            errors.append(f"{skill_id}: version must be semantic x.y.z")
        if not str(raw.get("summary") or "").strip():
            errors.append(f"{skill_id}: summary is required")

        indexes = _strings(raw.get("indexes"), "indexes", skill_id, errors)
        roles = _strings(raw.get("roles"), "roles", skill_id, errors)
        runtimes = _strings(raw.get("runtimes"), "runtimes", skill_id, errors)
        domains = _strings(raw.get("domains"), "domains", skill_id, errors)
        related = _strings(raw.get("related_skills"), "related_skills", skill_id, errors)
        foundations = _strings(
            raw.get("suggested_foundations"), "suggested_foundations", skill_id, errors
        )
        affinity = _strings(
            raw.get("capability_affinity"), "capability_affinity", skill_id, errors
        )

        if not indexes:
            errors.append(f"{skill_id}: indexes must contain a primary index")
        for index in indexes:
            if index not in graph_indexes:
                errors.append(f"{skill_id}: unknown graph index {index!r}")
        if not roles or not set(roles).issubset(_ALLOWED_ROLES):
            errors.append(f"{skill_id}: roles must be drawn from {sorted(_ALLOWED_ROLES)}")
        if not runtimes:
            errors.append(f"{skill_id}: runtimes must not be empty")
        if not domains:
            errors.append(f"{skill_id}: domains must not be empty")
        for token in (*runtimes, *domains, *affinity):
            if not _TOKEN_RE.fullmatch(token):
                errors.append(f"{skill_id}: invalid metadata token {token!r}")
        if skill_id in related:
            errors.append(f"{skill_id}: related_skills cannot contain itself")
        if skill_id in foundations:
            errors.append(f"{skill_id}: suggested_foundations cannot contain itself")

        cost = str(raw.get("context_cost_class") or "")
        if cost not in _ALLOWED_COSTS:
            errors.append(f"{skill_id}: invalid context_cost_class {cost!r}")
        visibility = str(raw.get("visibility") or "")
        if visibility not in _ALLOWED_VISIBILITY:
            errors.append(f"{skill_id}: invalid visibility {visibility!r}")
        if not isinstance(raw.get("benchmark_safe"), bool):
            errors.append(f"{skill_id}: benchmark_safe must be boolean")

        # Permission-like legacy fields are forbidden in the frozen canonical schema.
        for forbidden in ("prerequisites", "capability_requirements", "capabilities"):
            if forbidden in raw:
                errors.append(f"{skill_id}: forbidden canonical field {forbidden!r}")

        discovery = raw.get("discovery")
        discovery_values: dict[str, tuple[str, ...]] = {}
        if not isinstance(discovery, dict):
            errors.append(f"{skill_id}: discovery must be a mapping")
        else:
            unexpected = set(discovery) - set(_DISCOVERY_BUCKETS)
            if unexpected:
                errors.append(f"{skill_id}: unexpected discovery buckets {sorted(unexpected)}")
            seen: set[str] = set()
            for bucket in _DISCOVERY_BUCKETS:
                values = _strings(discovery.get(bucket), f"discovery.{bucket}", skill_id, errors)
                if not values:
                    errors.append(f"{skill_id}: discovery.{bucket} must not be empty")
                overlap = seen.intersection(values)
                if overlap:
                    errors.append(
                        f"{skill_id}: discovery signals repeated across buckets: {sorted(overlap)}"
                    )
                seen.update(values)
                discovery_values[bucket] = values

        normalized[skill_id] = {
            "indexes": indexes,
            "related": related,
            "foundations": foundations,
        }

    if len(ids) != len(set(ids)):
        duplicates = sorted({x for x in ids if ids.count(x) > 1})
        errors.append(f"duplicate canonical skill ids: {duplicates}")

    id_set = set(ids)
    for skill_id, item in normalized.items():
        for related in item["related"]:
            if related not in id_set:
                errors.append(f"{skill_id}: dangling related skill {related!r}")
        for foundation in item["foundations"]:
            if foundation not in id_set:
                errors.append(f"{skill_id}: dangling suggested foundation {foundation!r}")

    # Validate graph membership in both directions without exposing traversal APIs.
    for index, entry in graph_indexes_raw.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("skills"), list):
            errors.append(f"graph index {index!r}: skills must be a list")
            continue
        graph_skill_ids = [str(x) for x in entry["skills"]]
        if len(graph_skill_ids) != len(set(graph_skill_ids)):
            errors.append(f"graph index {index!r}: duplicate skill membership")
        for skill_id in graph_skill_ids:
            if skill_id not in id_set:
                errors.append(f"graph index {index!r}: unknown skill {skill_id!r}")
            elif index not in normalized[skill_id]["indexes"]:
                errors.append(
                    f"graph index {index!r}: membership for {skill_id!r} missing from canonical skill"
                )

    for skill_id, item in normalized.items():
        for index in item["indexes"]:
            entry = graph_indexes_raw.get(index, {})
            members = entry.get("skills", []) if isinstance(entry, dict) else []
            if skill_id not in members:
                errors.append(
                    f"{skill_id}: canonical index {index!r} missing reciprocal graph membership"
                )

    return tuple(errors)


def _skill_from_raw(raw: Mapping[str, Any]) -> SkillRecord:
    skill_id = str(raw["id"])
    summary = str(raw["summary"])
    discovery = raw["discovery"]
    return SkillRecord(
        id=skill_id,
        name=skill_id,
        slug=skill_id,
        version=str(raw["version"]),
        description=summary,
        desc=summary if len(summary) <= 240 else summary[:237] + "...",
        summary=summary,
        schema_version=int(raw["schema_version"]),
        indexes=list(raw["indexes"]),
        roles=list(raw["roles"]),
        runtimes=list(raw["runtimes"]),
        domains=list(raw["domains"]),
        related_skills=list(raw["related_skills"]),
        suggested_foundations=list(raw["suggested_foundations"]),
        capability_affinity=list(raw["capability_affinity"]),
        context_cost_class=str(raw["context_cost_class"]),
        visibility=str(raw["visibility"]),
        benchmark_safe=bool(raw["benchmark_safe"]),
        discovery={
            "strong": list(discovery["strong"]),
            "normal": list(discovery["normal"]),
            "weak": list(discovery["weak"]),
        },
    )


def _load_catalog(
    catalog_path: Path,
    graph_path: Path,
) -> CanonicalSkillCatalog:
    catalog_doc = _load_yaml(catalog_path)
    graph_doc = _load_yaml(graph_path)
    errors = validate_catalog_documents(catalog_doc, graph_doc)
    if errors:
        raise CatalogValidationError(errors)

    skills = tuple(_skill_from_raw(raw) for raw in catalog_doc["skills"])
    by_id = MappingProxyType({skill.id: skill for skill in skills})
    return CanonicalSkillCatalog(
        version=str(catalog_doc["catalog_version"]),
        skills=skills,
        by_id=by_id,
        graph_indexes=frozenset(str(k) for k in graph_doc["indexes"]),
    )


@lru_cache(maxsize=1)
def _load_default_catalog_cached() -> CanonicalSkillCatalog:
    return _load_catalog(canonical_catalog_path(), canonical_graph_manifest_path())


def load_canonical_catalog(
    catalog_path: Path | str | None = None,
    graph_path: Path | str | None = None,
) -> CanonicalSkillCatalog:
    """Load and fully validate canonical v0.3 metadata.

    Default bundled loads are cached. Explicit paths are intentionally uncached so
    tests/tools can validate edited fixtures deterministically.
    """
    if catalog_path is None and graph_path is None:
        return _load_default_catalog_cached()
    return _load_catalog(
        Path(catalog_path) if catalog_path is not None else canonical_catalog_path(),
        Path(graph_path) if graph_path is not None else canonical_graph_manifest_path(),
    )


def canonical_metadata_for(skill_id: str) -> SkillRecord | None:
    """Return the catalog SkillRecord for a frozen v0.3 id, if present."""
    return load_canonical_catalog().get(skill_id)


def apply_canonical_metadata(skill: Mapping[str, Any] | SkillRecord) -> dict[str, Any]:
    """Attach v0.3 fields onto an existing Change Set B skill dict.

    Identity, version, body, aliases, and legacy B keys stay as they were.
    Catalog fields do not grant tools or change lifecycle.
    """
    result = skill.to_dict() if isinstance(skill, SkillRecord) else dict(skill)
    skill_id = str(result.get("id") or result.get("slug") or result.get("name") or "")
    catalog_skill = canonical_metadata_for(skill_id)
    if catalog_skill is None:
        return result

    existing_version = str(result.get("version") or "").strip()
    result["schema_version"] = catalog_skill.schema_version
    result["summary"] = catalog_skill.summary
    result["indexes"] = list(catalog_skill.indexes)
    result["roles"] = list(catalog_skill.roles)
    result["runtimes"] = list(catalog_skill.runtimes)
    result["domains"] = list(catalog_skill.domains)
    result["related_skills"] = list(catalog_skill.related_skills)
    result["suggested_foundations"] = list(catalog_skill.suggested_foundations)
    result["capability_affinity"] = list(catalog_skill.capability_affinity)
    result["context_cost_class"] = catalog_skill.context_cost_class
    result["visibility"] = catalog_skill.visibility
    result["benchmark_safe"] = catalog_skill.benchmark_safe
    result["discovery"] = {
        bucket: list(values) for bucket, values in catalog_skill.discovery.items()
    }
    result["id"] = str(result.get("id") or catalog_skill.id)
    result["slug"] = str(result.get("slug") or catalog_skill.slug)
    if existing_version:
        result["version"] = existing_version
    else:
        result["version"] = catalog_skill.version
    return result
