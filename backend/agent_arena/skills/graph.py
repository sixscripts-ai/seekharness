"""Skill Graph v0.3 deterministic, read-only graph and catalog access layer.

D1 only: provides read-only programmatic access over the validated Skill Graph
and canonical SkillRecord catalog. No search, relevance ranking, recommendations,
fighter-facing tools, telemetry, adaptive learning, or progressive disclosure.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import SkillRecord, slugify
from .canonical_metadata import (
    CanonicalSkillCatalog,
    _load_yaml,
    canonical_catalog_path,
    canonical_graph_manifest_path,
    load_canonical_catalog,
)


class UnknownSkillError(KeyError):
    """Raised when a canonical skill is not found in the graph/catalog."""


class UnknownIndexError(KeyError):
    """Raised when an index path is not found in the graph."""


def _normalize_index_path(path: str) -> str:
    return str(path or "").strip().strip("/").lower()


def _normalize_skill_id(skill_id: str) -> str:
    key = str(skill_id or "").strip()
    return slugify(key)


@dataclass(frozen=True, slots=True)
class SkillGraphIndex:
    """An immutable node in the skill graph taxonomy."""

    id: str
    name: str
    path: str
    parent: str | None = None
    description: str = ""
    is_root: bool = False
    children: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "parent": self.parent,
            "description": self.description,
            "is_root": self.is_root,
            "children": list(self.children),
            "skills": list(self.skills),
        }


@dataclass(frozen=True, slots=True)
class SkillGraph:
    """Deterministic, read-only graph access layer over canonical SkillRecords."""

    catalog: CanonicalSkillCatalog
    roots: Mapping[str, str]
    indexes: Mapping[str, SkillGraphIndex]
    _root_order: tuple[str, ...]
    _index_order: tuple[str, ...]
    _skills_by_id: Mapping[str, SkillRecord]
    _skills_by_index: Mapping[str, tuple[SkillRecord, ...]]
    _indexes_by_skill: Mapping[str, tuple[str, ...]]
    _related_by_skill: Mapping[str, tuple[SkillRecord, ...]]
    _foundations_by_skill: Mapping[str, tuple[SkillRecord, ...]]

    @property
    def skills(self) -> tuple[SkillRecord, ...]:
        return self.catalog.skills

    def all_skills(self) -> tuple[SkillRecord, ...]:
        return self.catalog.skills

    def all_indexes(self) -> tuple[str, ...]:
        return self._index_order

    def root_indexes(self) -> tuple[str, ...]:
        return self._root_order

    def get_skill(self, skill_id: str) -> SkillRecord | None:
        key = str(skill_id or "").strip()
        if not key:
            return None
        return self._skills_by_id.get(key) or self._skills_by_id.get(slugify(key))

    def require_skill(self, skill_id: str) -> SkillRecord:
        skill = self.get_skill(skill_id)
        if skill is None:
            raise UnknownSkillError(f"unknown canonical skill: {skill_id}")
        return skill

    def get_index(self, index_path: str) -> SkillGraphIndex | None:
        norm = _normalize_index_path(index_path)
        if not norm:
            return None
        return self.indexes.get(norm)

    def require_index(self, index_path: str) -> SkillGraphIndex:
        idx = self.get_index(index_path)
        if idx is None:
            raise UnknownIndexError(f"unknown graph index: {index_path}")
        return idx

    def child_indexes(self, index_path: str) -> tuple[str, ...]:
        idx = self.require_index(index_path)
        return idx.children

    def skills_in_index(self, index_path: str) -> tuple[SkillRecord, ...]:
        idx = self.require_index(index_path)
        return self._skills_by_index.get(idx.id, ())

    def indexes_for_skill(self, skill_id: str) -> tuple[str, ...]:
        skill = self.require_skill(skill_id)
        return self._indexes_by_skill.get(skill.id, ())

    def related_skills(self, skill_id: str) -> tuple[SkillRecord, ...]:
        skill = self.require_skill(skill_id)
        return self._related_by_skill.get(skill.id, ())

    def suggested_foundations(self, skill_id: str) -> tuple[SkillRecord, ...]:
        skill = self.require_skill(skill_id)
        return self._foundations_by_skill.get(skill.id, ())


def _build_skill_graph(
    catalog: CanonicalSkillCatalog,
    graph_doc: Mapping[str, Any],
) -> SkillGraph:
    raw_roots = graph_doc.get("roots", {})
    raw_indexes = graph_doc.get("indexes", {})

    # 1. Roots in manifest order
    root_order = tuple(str(r) for r in raw_roots)
    roots_map: dict[str, str] = {str(r): str(desc) for r, desc in raw_roots.items()}

    # 2. Indexes in manifest order
    index_order = tuple(str(i) for i in raw_indexes)

    # 3. Skills by ID mapping
    skills_by_id: dict[str, SkillRecord] = {skill.id: skill for skill in catalog.skills}

    # 4. Map skills to indexes and indexes to skills
    skills_by_index: dict[str, list[SkillRecord]] = {}
    indexes_by_skill: dict[str, list[str]] = {skill.id: [] for skill in catalog.skills}

    # For each index from manifest
    all_index_nodes: dict[str, SkillGraphIndex] = {}

    for idx_path in index_order:
        entry = raw_indexes[idx_path]
        member_skill_ids = tuple(str(s) for s in entry.get("skills", []))
        # Build SkillRecord list for this index
        member_records = [
            skills_by_id[sid] for sid in member_skill_ids if sid in skills_by_id
        ]
        skills_by_index[idx_path] = member_records

        # Parent is root prefix
        parent = idx_path.split("/", 1)[0]
        name = idx_path.rsplit("/", 1)[-1]

        all_index_nodes[idx_path] = SkillGraphIndex(
            id=idx_path,
            name=name,
            path=idx_path,
            parent=parent,
            description="",
            is_root=False,
            children=(),
            skills=member_skill_ids,
        )

    # For each skill, use canonical skill.indexes
    for skill in catalog.skills:
        indexes_by_skill[skill.id] = list(skill.indexes)

    # 5. Build Root Nodes
    for root_name in root_order:
        # Find all direct child index paths for this root
        children = tuple(
            idx_path
            for idx_path in index_order
            if idx_path.split("/", 1)[0] == root_name
        )
        # Aggregate unique skills under this root in deterministic manifest order
        root_skill_ids: list[str] = []
        seen_sids: set[str] = set()
        for child_path in children:
            for sid in raw_indexes.get(child_path, {}).get("skills", []):
                if sid not in seen_sids and sid in skills_by_id:
                    seen_sids.add(sid)
                    root_skill_ids.append(sid)

        root_records = [skills_by_id[sid] for sid in root_skill_ids]
        skills_by_index[root_name] = root_records

        all_index_nodes[root_name] = SkillGraphIndex(
            id=root_name,
            name=root_name,
            path=root_name,
            parent=None,
            description=roots_map.get(root_name, ""),
            is_root=True,
            children=children,
            skills=tuple(root_skill_ids),
        )

    # 6. Precompute related and foundations
    related_by_skill: dict[str, tuple[SkillRecord, ...]] = {}
    foundations_by_skill: dict[str, tuple[SkillRecord, ...]] = {}

    for skill in catalog.skills:
        related_records = tuple(
            skills_by_id[r] for r in skill.related_skills if r in skills_by_id
        )
        foundation_records = tuple(
            skills_by_id[f] for f in skill.suggested_foundations if f in skills_by_id
        )
        related_by_skill[skill.id] = related_records
        foundations_by_skill[skill.id] = foundation_records

    # 7. Convert all collections to immutable MappingProxyType and tuples
    frozen_skills_by_index = MappingProxyType(
        {k: tuple(v) for k, v in skills_by_index.items()}
    )
    frozen_indexes_by_skill = MappingProxyType(
        {k: tuple(v) for k, v in indexes_by_skill.items()}
    )

    return SkillGraph(
        catalog=catalog,
        roots=MappingProxyType(roots_map),
        indexes=MappingProxyType(all_index_nodes),
        _root_order=root_order,
        _index_order=index_order,
        _skills_by_id=MappingProxyType(skills_by_id),
        _skills_by_index=frozen_skills_by_index,
        _indexes_by_skill=frozen_indexes_by_skill,
        _related_by_skill=MappingProxyType(related_by_skill),
        _foundations_by_skill=MappingProxyType(foundations_by_skill),
    )


@lru_cache(maxsize=1)
def _load_default_skill_graph_cached() -> SkillGraph:
    catalog = load_canonical_catalog()
    graph_doc = _load_yaml(canonical_graph_manifest_path())
    return _build_skill_graph(catalog, graph_doc)


def load_skill_graph(
    catalog_path: Path | str | None = None,
    graph_path: Path | str | None = None,
) -> SkillGraph:
    """Load and return the validated SkillGraph.

    Default bundled loads are cached. Explicit paths are intentionally uncached so
    tests/tools can validate edited fixtures deterministically.
    """
    if catalog_path is None and graph_path is None:
        return _load_default_skill_graph_cached()
    catalog = load_canonical_catalog(catalog_path, graph_path)
    gpath = (
        Path(graph_path) if graph_path is not None else canonical_graph_manifest_path()
    )
    graph_doc = _load_yaml(gpath)
    return _build_skill_graph(catalog, graph_doc)


def get_skill(skill_id: str) -> SkillRecord | None:
    """Return canonical SkillRecord by ID, slug, or None if unknown."""
    return load_skill_graph().get_skill(skill_id)


def require_skill(skill_id: str) -> SkillRecord:
    """Return canonical SkillRecord by ID, raising UnknownSkillError if absent."""
    return load_skill_graph().require_skill(skill_id)


def root_indexes() -> tuple[str, ...]:
    """Return all root index names in deterministic manifest order."""
    return load_skill_graph().root_indexes()


def get_index(index_path: str) -> SkillGraphIndex | None:
    """Return SkillGraphIndex by path (e.g. 'security' or 'security/authentication') or None."""
    return load_skill_graph().get_index(index_path)


def require_index(index_path: str) -> SkillGraphIndex:
    """Return SkillGraphIndex by path, raising UnknownIndexError if absent."""
    return load_skill_graph().require_index(index_path)


def child_indexes(index_path: str) -> tuple[str, ...]:
    """Return immediate direct child index paths for the given index path."""
    return load_skill_graph().child_indexes(index_path)


def skills_in_index(index_path: str) -> tuple[SkillRecord, ...]:
    """Return all canonical SkillRecords belonging to the given index path."""
    return load_skill_graph().skills_in_index(index_path)


def indexes_for_skill(skill_id: str) -> tuple[str, ...]:
    """Return all canonical index paths for the given skill ID."""
    return load_skill_graph().indexes_for_skill(skill_id)


def related_skills(skill_id: str) -> tuple[SkillRecord, ...]:
    """Return resolved related SkillRecords for the given skill ID."""
    return load_skill_graph().related_skills(skill_id)


def suggested_foundations(skill_id: str) -> tuple[SkillRecord, ...]:
    """Return resolved advisory suggested foundation SkillRecords for the given skill ID."""
    return load_skill_graph().suggested_foundations(skill_id)


def all_skills() -> tuple[SkillRecord, ...]:
    """Return all canonical SkillRecords in catalog order."""
    return load_skill_graph().all_skills()


def all_indexes() -> tuple[str, ...]:
    """Return all graph index paths in manifest order."""
    return load_skill_graph().all_indexes()
