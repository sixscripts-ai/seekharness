"""Skill Graph v0.3 fighter discovery service and deterministic search engine.

D2 only: provides read-only navigation, hierarchy browsing, compact card inspection,
and deterministic lexical search over public canonical skill metadata.

Core Principle: CURATION IS NAVIGATION, NOT PERMISSION.
- Browsing/searching does not gate, load, or restrict skill usage.
- Does not expose full SKILL.md bodies (full bodies stay behind use_skill).
- Lexical search ordering: strong > normal > weak.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .canonical import SkillRecord
from .graph import (
    SkillGraph,
    SkillGraphIndex,
    UnknownIndexError,
    UnknownSkillError,
    load_skill_graph,
)

# Lexical search scoring weights
WEIGHT_EXACT_ID = 100.0  # query == skill.id
WEIGHT_ID_TOKEN = 25.0  # query term in skill.id
WEIGHT_DISCOVERY_STRONG = 40.0  # query term in discovery.strong
WEIGHT_DISCOVERY_NORMAL = 20.0  # query term in discovery.normal
WEIGHT_SUMMARY = 8.0  # query term in summary
WEIGHT_DISCOVERY_WEAK = 5.0  # query term in discovery.weak
WEIGHT_DOMAIN = 3.0  # query term in domains
WEIGHT_INDEX = 2.0  # query term in indexes
WEIGHT_ROLE = 1.0  # query term in roles
WEIGHT_RUNTIME = 0.5  # query term in runtimes (low weight to avoid runtime bias)


@dataclass(frozen=True, slots=True)
class CompactSkillCard:
    """Compact public representation of a skill for fighter navigation."""

    id: str
    summary: str
    indexes: tuple[str, ...]
    roles: tuple[str, ...]
    runtimes: tuple[str, ...]
    domains: tuple[str, ...]
    context_cost_class: str
    related_skills: tuple[str, ...]
    suggested_foundations: tuple[str, ...]
    capability_affinity: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "indexes": list(self.indexes),
            "roles": list(self.roles),
            "runtimes": list(self.runtimes),
            "domains": list(self.domains),
            "context_cost_class": self.context_cost_class,
            "related_skills": list(self.related_skills),
            "suggested_foundations": list(self.suggested_foundations),
            "capability_affinity": list(self.capability_affinity),
        }


def skill_to_compact_card(skill: SkillRecord) -> CompactSkillCard:
    """Extract public compact navigation card from SkillRecord without full body."""
    return CompactSkillCard(
        id=skill.id,
        summary=skill.summary or skill.desc or skill.description,
        indexes=tuple(skill.indexes),
        roles=tuple(skill.roles),
        runtimes=tuple(skill.runtimes),
        domains=tuple(skill.domains),
        context_cost_class=skill.context_cost_class or "small",
        related_skills=tuple(skill.related_skills),
        suggested_foundations=tuple(skill.suggested_foundations),
        capability_affinity=tuple(skill.capability_affinity),
    )


@dataclass(frozen=True, slots=True)
class RootIndexCard:
    path: str
    name: str
    description: str
    child_count: int
    skill_count: int


@dataclass(frozen=True, slots=True)
class RootDiscoveryView:
    view_type: str = "roots"
    roots: tuple[RootIndexCard, ...] = ()
    total_skills: int = 63
    total_indexes: int = 65

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_type": "roots",
            "roots": [
                {
                    "path": r.path,
                    "name": r.name,
                    "description": r.description,
                    "child_count": r.child_count,
                    "skill_count": r.skill_count,
                }
                for r in self.roots
            ],
            "total_skills": self.total_skills,
            "total_indexes": self.total_indexes,
        }


@dataclass(frozen=True, slots=True)
class IndexDiscoveryView:
    view_type: str = "index"
    index_path: str = ""
    name: str = ""
    description: str = ""
    is_root: bool = False
    parent: str | None = None
    direct_children: tuple[str, ...] = ()
    skills: tuple[CompactSkillCard, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_type": "index",
            "index_path": self.index_path,
            "name": self.name,
            "description": self.description,
            "is_root": self.is_root,
            "parent": self.parent,
            "direct_children": list(self.direct_children),
            "skills": [s.to_dict() for s in self.skills],
        }


@dataclass(frozen=True, slots=True)
class SkillDiscoveryView:
    view_type: str = "skill"
    card: CompactSkillCard | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_type": "skill",
            "card": self.card.to_dict() if self.card else None,
        }


@dataclass(frozen=True, slots=True)
class SearchDiscoveryView:
    view_type: str = "search"
    query: str = ""
    results: tuple[CompactSkillCard, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_type": "search",
            "query": self.query,
            "results": [s.to_dict() for s in self.results],
        }


@dataclass(frozen=True, slots=True)
class DiscoveryErrorView:
    view_type: str = "error"
    error: str = ""
    error_type: str = ""
    requested: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_type": "error",
            "error": self.error,
            "error_type": self.error_type,
            "requested": self.requested,
        }


class DiscoveryRequestError(ValueError):
    """Raised when a discovery request contains conflicting selectors."""


def browse_roots(graph: SkillGraph | None = None) -> RootDiscoveryView:
    """Return top-level discovery view of all 13 root indexes in manifest order."""
    g = graph or load_skill_graph()
    root_cards: list[RootIndexCard] = []
    for root_name in g.root_indexes():
        idx = g.get_index(root_name)
        if idx is not None:
            root_cards.append(
                RootIndexCard(
                    path=idx.path,
                    name=idx.name,
                    description=idx.description,
                    child_count=len(idx.children),
                    skill_count=len(idx.skills),
                )
            )
    return RootDiscoveryView(
        roots=tuple(root_cards),
        total_skills=len(g.all_skills()),
        total_indexes=len(g.all_indexes()),
    )


def browse_index(
    index_path: str, graph: SkillGraph | None = None
) -> IndexDiscoveryView:
    """Return discovery view of an index, its immediate children, and associated skills."""
    g = graph or load_skill_graph()
    idx = g.require_index(index_path)
    skill_records = g.skills_in_index(idx.path)
    cards = tuple(skill_to_compact_card(s) for s in skill_records if is_public_skill(s))
    return IndexDiscoveryView(
        index_path=idx.path,
        name=idx.name,
        description=idx.description,
        is_root=idx.is_root,
        parent=idx.parent,
        direct_children=idx.children,
        skills=cards,
    )


def inspect_skill_card(
    skill_id: str, graph: SkillGraph | None = None
) -> SkillDiscoveryView:
    """Return compact skill card for a canonical skill ID without full body."""
    g = graph or load_skill_graph()
    skill = g.require_skill(skill_id)
    if not is_public_skill(skill):
        raise UnknownSkillError(f"skill '{skill_id}' is not public")
    return SkillDiscoveryView(card=skill_to_compact_card(skill))


def is_public_skill(skill: SkillRecord) -> bool:
    """Return True if skill has public visibility."""
    return skill.visibility == "public"


def score_skill_for_query(query: str, skill: SkillRecord) -> float:
    """Deterministic lexical scoring of a skill against query terms."""
    if not is_public_skill(skill):
        return 0.0

    q = str(query or "").strip().lower()
    if not q:
        return 0.0

    tokens = [t for t in re.split(r"[^a-z0-9_.-]+", q) if t]
    if not tokens:
        return 0.0

    score = 0.0

    # 1. Exact ID match (highest priority)
    if q == skill.id.lower():
        score += WEIGHT_EXACT_ID

    # 2. Token-level matches
    for t in tokens:
        # ID token match
        id_tokens = set(skill.id.lower().replace("_", "-").split("-"))
        if t == skill.id.lower() or t in id_tokens:
            score += WEIGHT_ID_TOKEN

        # discovery.strong
        disc = skill.discovery or {}
        for sig in disc.get("strong", []):
            sig_toks = set(re.split(r"[^a-z0-9_.-]+", sig.lower()))
            if t == sig.lower() or t in sig_toks:
                score += WEIGHT_DISCOVERY_STRONG
                break

        # discovery.normal
        for sig in disc.get("normal", []):
            sig_toks = set(re.split(r"[^a-z0-9_.-]+", sig.lower()))
            if t == sig.lower() or t in sig_toks:
                score += WEIGHT_DISCOVERY_NORMAL
                break

        # summary token match
        summary_toks = set(re.split(r"[^a-z0-9_.-]+", skill.summary.lower()))
        if t in summary_toks:
            score += WEIGHT_SUMMARY

        # discovery.weak
        for sig in disc.get("weak", []):
            sig_toks = set(re.split(r"[^a-z0-9_.-]+", sig.lower()))
            if t == sig.lower() or t in sig_toks:
                score += WEIGHT_DISCOVERY_WEAK
                break

        # domains
        if any(t == d.lower() or t in d.lower().split("-") for d in skill.domains):
            score += WEIGHT_DOMAIN

        # indexes
        if any(
            t in idx.lower().replace("/", " ").replace("-", " ").split()
            for idx in skill.indexes
        ):
            score += WEIGHT_INDEX

        # roles
        if any(t == r.lower() for r in skill.roles):
            score += WEIGHT_ROLE

        # runtimes
        if any(t == rt.lower() for rt in skill.runtimes if rt != "*"):
            score += WEIGHT_RUNTIME

    # 3. Full phrase bonus
    if len(tokens) > 1:
        disc = skill.discovery or {}
        if any(q == s.lower() for s in disc.get("strong", [])):
            score += WEIGHT_DISCOVERY_STRONG * 2
        elif any(q == s.lower() for s in disc.get("normal", [])):
            score += WEIGHT_DISCOVERY_NORMAL * 2
        if q in skill.summary.lower():
            score += WEIGHT_SUMMARY * 2

    return score


def search_skills(
    query: str,
    limit: int = 15,
    graph: SkillGraph | None = None,
) -> SearchDiscoveryView:
    """Deterministic lexical search across public skills in Skill Graph."""
    g = graph or load_skill_graph()
    q = str(query or "").strip()
    if not q:
        return SearchDiscoveryView(query="", results=())

    scored: list[tuple[float, SkillRecord]] = []
    for skill in g.all_skills():
        score = score_skill_for_query(q, skill)
        if score > 0.0:
            scored.append((score, skill))

    # Sort deterministically: score descending, tie-break by canonical skill ID ascending
    scored.sort(key=lambda item: (-item[0], item[1].id))

    capped = scored[:limit] if limit > 0 else scored
    cards = tuple(skill_to_compact_card(s) for _, s in capped)
    return SearchDiscoveryView(query=q, results=cards)


def discover_skills(
    *,
    index: str | None = None,
    search: str | None = None,
    skill: str | None = None,
    graph: SkillGraph | None = None,
) -> RootDiscoveryView | IndexDiscoveryView | SkillDiscoveryView | SearchDiscoveryView:
    """Unified entrypoint for skill graph discovery.

    Priority:
    1. skill -> inspect specific compact card
    2. index -> browse specific index node
    3. search -> search catalog with query
    4. none -> browse root indexes
    """
    g = graph or load_skill_graph()
    selectors = [value is not None for value in (index, search, skill)]
    if sum(selectors) > 1:
        raise DiscoveryRequestError(
            "provide only one discovery selector: index, search, or skill"
        )
    if skill is not None:
        if not str(skill).strip():
            raise DiscoveryRequestError("skill selector must not be empty")
        return inspect_skill_card(skill, graph=g)
    if index is not None:
        if not str(index).strip():
            raise DiscoveryRequestError("index selector must not be empty")
        return browse_index(index, graph=g)
    if search is not None:
        return search_skills(search, graph=g)
    return browse_roots(graph=g)


def format_discovery_text(
    view: RootDiscoveryView
    | IndexDiscoveryView
    | SkillDiscoveryView
    | SearchDiscoveryView
    | DiscoveryErrorView,
) -> str:
    """Format discovery views into clean, deterministic text for LLM/terminal output."""
    if isinstance(view, RootDiscoveryView):
        lines = [
            f"SKILL GRAPH ROOT INDEXES ({len(view.roots)} roots, {view.total_indexes} sub-indexes, {view.total_skills} skills)",
            'Browse: skills(index="<root>") | Search: skills(search="<query>") | Card: skills(skill="<id>")',
            "",
        ]
        for r in view.roots:
            lines.append(f"- {r.name}: {r.description} ({r.child_count} sub-indexes)")
        return "\n".join(lines)

    if isinstance(view, IndexDiscoveryView):
        lines = [f"INDEX: {view.index_path}"]
        if view.description:
            lines.append(view.description)
        if view.parent:
            lines.append(f"Parent: {view.parent}")
        lines.append("")

        if view.direct_children:
            lines.append(f"DIRECT CHILD INDEXES ({len(view.direct_children)}):")
            for c in view.direct_children:
                lines.append(f"- {c}")
            lines.append("")
        else:
            lines.append("DIRECT CHILD INDEXES: (none)")
            lines.append("")

        if view.skills:
            header = "DIRECT SKILLS" if not view.is_root else "SKILLS IN HIERARCHY"
            lines.append(f"{header} ({len(view.skills)}):")
            for s in view.skills:
                lines.append(f"- {s.id}: {s.summary}")
        else:
            lines.append("DIRECT SKILLS: (none)")
        return "\n".join(lines)

    if isinstance(view, SkillDiscoveryView):
        card = view.card
        if not card:
            return "ERROR: skill card empty"
        lines = [
            f"SKILL CARD: {card.id}",
            f"Summary: {card.summary}",
            f"Context Cost: {card.context_cost_class}",
            f"Indexes: {', '.join(card.indexes) if card.indexes else '(none)'}",
            f"Roles: {', '.join(card.roles) if card.roles else '(none)'}",
            f"Runtimes: {', '.join(card.runtimes) if card.runtimes else '(none)'}",
            f"Domains: {', '.join(card.domains) if card.domains else '(none)'}",
            f"Related Skills: {', '.join(card.related_skills) if card.related_skills else '(none)'}",
            f"Suggested Foundations: {', '.join(card.suggested_foundations) if card.suggested_foundations else '(none)'}",
            f"Capability Affinity: {', '.join(card.capability_affinity) if card.capability_affinity else '(none)'}",
            "",
            f'To load this skill into active context: use_skill("{card.id}")',
        ]
        return "\n".join(lines)

    if isinstance(view, SearchDiscoveryView):
        if not view.query:
            return 'SEARCH RESULTS: (empty query, 0 matches)\nUse skills() to browse roots or skills(search="<terms>") to search.'
        if not view.results:
            return f'SEARCH RESULTS for "{view.query}": (0 matches)\nUse skills() to browse roots or try broader search terms.'
        lines = [f'SEARCH RESULTS for "{view.query}" ({len(view.results)} matches):']
        for i, card in enumerate(view.results, 1):
            lines.append(f"{i}. {card.id}")
            lines.append(f"   Summary: {card.summary}")
            lines.append(f"   Indexes: {', '.join(card.indexes)}")
            lines.append(
                f"   Cost: {card.context_cost_class} | Runtimes: {', '.join(card.runtimes)}"
            )
        lines.append("")
        lines.append(
            'To inspect a card: skills(skill="<id>") | To load: use_skill("<id>")'
        )
        return "\n".join(lines)

    if isinstance(view, DiscoveryErrorView):
        requested = f" ({view.requested})" if view.requested else ""
        return f"ERROR [{view.error_type}]{requested}: {view.error}"

    return str(view)
