"""Canonical skill identity, normalization, and registry resolution.

Establishes a single authoritative resolver for skill identities across
executor, persistence, ranking, and telemetry layers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("name", "description")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LIST_RE = re.compile(r"[,\n]")


def slugify(name: str) -> str:
    """Normalize skill name to standard lowercase hyphenated slug."""
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")


def normalize_skill_ref(ref: str) -> str:
    """Normalize user/model input reference for skill lookup."""
    return slugify(str(ref or "").strip())


@dataclass
class SkillRecord:
    id: str  # Unique canonical ID (usually slugified name)
    name: str  # Display name
    slug: str  # Hyphenated slug
    aliases: list[str] = field(default_factory=list)
    tier: str = "general"  # novice, general, advanced, expert
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    allowed_environments: list[str] = field(default_factory=list)
    description: str = ""
    desc: str = ""  # Truncated description for prompts (<240 chars)
    version: str = "0.1.0"
    elo: int = 1200
    path: str = ""
    body: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "aliases": list(self.aliases),
            "tier": self.tier,
            "category": self.category,
            "tags": list(self.tags),
            "prerequisites": list(self.prerequisites),
            "capabilities": list(self.capabilities),
            "allowed_environments": list(self.allowed_environments),
            "description": self.description,
            "desc": self.desc,
            "version": self.version,
            "elo": self.elo,
            "path": self.path,
            "body": self.body,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRecord:
        name = str(data.get("name") or data.get("id") or "")
        slug = str(data.get("slug") or slugify(name))
        skill_id = str(data.get("id") or slug)
        desc = str(data.get("desc") or data.get("description") or "")
        if len(desc) > 240:
            desc = desc[:237] + "..."
        return cls(
            id=skill_id,
            name=name,
            slug=slug,
            aliases=[str(a).strip().lower() for a in data.get("aliases") or [] if str(a).strip()],
            tier=str(data.get("tier") or "general"),
            category=str(data.get("category") or "general"),
            tags=[str(t).strip() for t in data.get("tags") or [] if str(t).strip()],
            prerequisites=[str(p).strip() for p in data.get("prerequisites") or [] if str(p).strip()],
            capabilities=[str(c).strip() for c in data.get("capabilities") or [] if str(c).strip()],
            allowed_environments=[str(e).strip() for e in data.get("allowed_environments") or [] if str(e).strip()],
            description=str(data.get("description") or desc),
            desc=desc,
            version=str(data.get("version") or "0.1.0"),
            elo=int(data.get("elo") or 1200),
            path=str(data.get("path") or ""),
            body=str(data.get("body") or ""),
        )


def _parse_frontmatter(text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return meta

    lines = m.group(1).splitlines()
    current_key: str | None = None
    folded: list[str] = []
    in_metadata = False

    def flush() -> None:
        nonlocal current_key, folded
        if current_key:
            if folded:
                meta[current_key] = " ".join(folded).strip().strip("\"'")
            folded = []
        current_key = None

    for line in lines:
        if not line.strip():
            flush()
            in_metadata = False
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent > 0 and current_key:
            if ":" in stripped and indent > 0 and current_key == "metadata":
                k, v = stripped.split(":", 1)
                meta[k.strip()] = v.strip().strip("\"'")
            else:
                folded.append(stripped)
            continue
        flush()
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        key = k.strip()
        val = v.strip()
        if key == "metadata":
            in_metadata = True
            current_key = "metadata"
            folded = []
            continue
        if val in (">", ">-", "|"):
            current_key = key
            folded = []
            continue
        meta[key] = val.strip("\"'")
    flush()
    return meta


def _parse_list(meta: dict[str, Any], key: str) -> list[str]:
    raw = meta.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in _LIST_RE.split(str(raw)) if x.strip()]


def parse_skill_text(text: str, name: str = "", path: str = "") -> SkillRecord:
    meta = _parse_frontmatter(text)
    raw_name = str(meta.get("name") or name or "unnamed-skill")
    slug = slugify(raw_name)
    skill_id = str(meta.get("id") or slug)
    desc = str(meta.get("description") or meta.get("desc") or f"Skill {raw_name}").strip()
    short_desc = desc[:237] + "..." if len(desc) > 240 else desc
    return SkillRecord(
        id=skill_id,
        name=raw_name,
        slug=slug,
        aliases=[slugify(a) for a in _parse_list(meta, "aliases")],
        tier=str(meta.get("tier") or "general"),
        category=str(meta.get("category") or "general"),
        tags=_parse_list(meta, "tags"),
        prerequisites=_parse_list(meta, "prerequisites"),
        capabilities=_parse_list(meta, "capabilities"),
        allowed_environments=_parse_list(meta, "allowed_environments"),
        description=desc,
        desc=short_desc,
        version=str(meta.get("version") or "0.1.0"),
        elo=int(meta.get("elo") or 1200),
        path=path,
        body=text,
    )


class CanonicalSkillResolver:
    """Central registry & resolver ensuring unified skill identity."""

    def __init__(self, skills: list[SkillRecord] | None = None):
        self._records: dict[str, SkillRecord] = {}  # by canonical ID
        self._lookup: dict[str, str] = {}  # alias/slug/name -> canonical ID
        if skills:
            for s in skills:
                self.register(s)

    def register(self, skill: SkillRecord | dict[str, Any]) -> SkillRecord:
        record = skill if isinstance(skill, SkillRecord) else SkillRecord.from_dict(skill)
        self._records[record.id] = record

        # Register primary keys
        self._lookup[record.id.lower()] = record.id
        self._lookup[record.name.lower()] = record.id
        self._lookup[record.slug.lower()] = record.id

        # Register aliases
        for alias in record.aliases:
            norm_alias = slugify(alias)
            if norm_alias:
                self._lookup[norm_alias] = record.id
        return record

    def resolve(self, ref: str) -> SkillRecord | None:
        """Resolve a skill by ID, name, slug, or alias (case-insensitive & normalized)."""
        if not ref:
            return None
        clean = str(ref).strip().lower()
        # Direct lookup
        canonical_id = self._lookup.get(clean) or self._lookup.get(slugify(clean))
        if canonical_id and canonical_id in self._records:
            return self._records[canonical_id]
        return None

    def canonical_id(self, ref: str) -> str | None:
        record = self.resolve(ref)
        return record.id if record else None

    def all_records(self) -> list[SkillRecord]:
        return list(self._records.values())

    def get(self, skill_id: str) -> SkillRecord | None:
        return self._records.get(str(skill_id).strip().lower())
