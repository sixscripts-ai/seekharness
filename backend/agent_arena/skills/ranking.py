"""Context-aware skill ranking and shortlist curation.

Supports two explicit execution policies:
- Strict Benchmark Mode: 100% neutral public context relevance. Historical Elo,
  model ID, and provider identity are completely excluded.
- Adaptive Mode: Bounded historical performance influence added to semantic relevance.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .canonical import SkillRecord, slugify



def compute_semantic_relevance(
    skill: SkillRecord,
    target_context: dict[str, Any],
) -> tuple[float, list[str]]:
    """Compute neutral semantic relevance score between target context and skill metadata.

    Returns:
        (relevance_score, matched_reasons)
    """
    reasons: list[str] = []
    score = 0.0

    target_name = str(target_context.get("name") or target_context.get("target_id") or "")
    category = str(target_context.get("category") or "")
    runtime = str(target_context.get("runtime") or "")
    objectives = target_context.get("objectives") or []
    tags = target_context.get("tags") or []
    recommended = set(target_context.get("recommended_skills") or [])

    context_str = f"{target_name} {category} {runtime} {' '.join(objectives)} {' '.join(tags)}".lower()
    tokens = set(re.findall(r"[a-z0-9_-]{3,}", context_str))

    skill_name = skill.name.lower()
    skill_slug = skill.slug.lower()
    skill_desc = skill.description.lower()
    skill_tags = [t.lower() for t in skill.tags]
    skill_cat = skill.category.lower()

    # Public target recommendation
    if skill.name in recommended or skill.slug in recommended or skill.id in recommended:
        score += 50.0
        reasons.append("target_recommended")

    # Token overlap
    matched_tokens = []
    for tok in tokens:
        if tok in skill_name or tok in skill_slug:
            score += 5.0
            matched_tokens.append(tok)
        elif tok in skill_tags:
            score += 4.0
            matched_tokens.append(tok)
        elif tok in skill_cat:
            score += 3.0
            matched_tokens.append(tok)
        elif tok in skill_desc:
            score += 1.0
            matched_tokens.append(tok)

    if matched_tokens:
        reasons.append(f"matched_tokens:{','.join(matched_tokens[:4])}")

    # Runtime and category matches
    if runtime and (runtime.lower() in skill_name or runtime.lower() in skill_desc or runtime.lower() in skill_tags):
        score += 4.0
        reasons.append(f"runtime:{runtime}")
    if category and category.lower() in skill_cat:
        score += 3.0
        reasons.append(f"category:{category}")

    return score, reasons


@dataclass
class RankedSkillScore:
    skill: SkillRecord
    semantic_score: float
    historical_adjustment: float
    final_score: float
    reason: str


def rank_skills_detailed(
    pool: list[SkillRecord],
    target_context: dict[str, Any] | None = None,
    *,
    context_mode: str = "strict",
    skill_elos: dict[str, float] | None = None,
    limit: int = 5,
) -> list[RankedSkillScore]:
    """Rank skills and return explicit component breakdowns: semantic, historical, final."""
    ctx = target_context or {}
    mode = str(context_mode or "strict").lower().strip()
    is_adaptive = mode in ("adaptive", "assisted")
    elos = skill_elos or {}

    scored: list[RankedSkillScore] = []

    for skill in pool:
        sem_score, reasons = compute_semantic_relevance(skill, ctx)
        hist_adj = 0.0
        reason_parts = list(reasons)

        if is_adaptive:
            current_elo = float(elos.get(skill.id) or elos.get(skill.name) or elos.get(skill.slug) or skill.elo or 1200)
            elo_delta = (current_elo - 1200.0) / 100.0
            hist_adj = max(-5.0, min(5.0, elo_delta))
            if abs(hist_adj) > 0.01:
                reason_parts.append(f"adaptive_elo_nudge:{hist_adj:+.2f}")
        else:
            hist_adj = 0.0

        final_score = round(sem_score + hist_adj, 3)
        reason_str = "; ".join(reason_parts) if reason_parts else "base_catalog"
        scored.append(
            RankedSkillScore(
                skill=skill,
                semantic_score=round(sem_score, 3),
                historical_adjustment=round(hist_adj, 3),
                final_score=final_score,
                reason=reason_str,
            )
        )

    # Stable deterministic sort: score descending, then canonical ID ascending
    scored.sort(key=lambda item: (item.final_score, -len(item.skill.name), item.skill.id), reverse=True)
    return scored[:limit]


def rank_skills(
    pool: list[SkillRecord],
    target_context: dict[str, Any] | None = None,
    *,
    context_mode: str = "strict",
    skill_elos: dict[str, float] | None = None,
    limit: int = 5,
) -> list[tuple[SkillRecord, float, str]]:
    """Rank skills using mode-gated relevance scoring.

    Returns:
        List of (SkillRecord, final_score, reason_summary) sorted descending by score.
    """
    detailed = rank_skills_detailed(
        pool,
        target_context,
        context_mode=context_mode,
        skill_elos=skill_elos,
        limit=limit,
    )
    return [(d.skill, d.final_score, d.reason) for d in detailed]



def curate_shortlist(
    pool: list[SkillRecord],
    target_context: dict[str, Any] | None = None,
    *,
    context_mode: str = "strict",
    skill_elos: dict[str, float] | None = None,
    max_shortlist: int = 5,
) -> list[tuple[SkillRecord, str]]:
    """Select the candidate shortlist including prerequisite resolution.

    Returns:
        List of (SkillRecord, reason_added) where reason is 'ranked_directly'
        or 'prerequisite_of:<parent_id>'.
    """
    ranked = rank_skills(
        pool,
        target_context,
        context_mode=context_mode,
        skill_elos=skill_elos,
        limit=max_shortlist,
    )

    shortlist: list[tuple[SkillRecord, str]] = []
    seen: set[str] = set()

    for skill, score, reason in ranked:
        if skill.id not in seen:
            seen.add(skill.id)
            shortlist.append((skill, "ranked_directly"))

    # Resolve prerequisites deterministically
    by_id = {s.id: s for s in pool}
    by_slug = {s.slug: s for s in pool}
    by_name = {s.name.lower(): s for s in pool}

    for skill, _ in list(shortlist):
        for prereq_ref in skill.prerequisites:
            norm = slugify(prereq_ref)
            prereq_skill = by_id.get(norm) or by_slug.get(norm) or by_name.get(norm)
            if prereq_skill and prereq_skill.id not in seen:
                seen.add(prereq_skill.id)
                shortlist.append((prereq_skill, f"prerequisite_of:{skill.id}"))

    return shortlist
