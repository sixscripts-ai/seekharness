"""Skills module for Agent Arena.

Exposes canonical skill identity, lifecycle tracking, context ranking, and authoritative attribution.
"""

from .canonical import (
    CanonicalSkillResolver,
    SkillRecord,
    normalize_skill_ref,
    parse_skill_text,
    slugify,
)
from .lifecycle import SkillLifecycleTracker
from .ranking import (
    RankedSkillScore,
    compute_semantic_relevance,
    curate_shortlist,
    rank_skills,
    rank_skills_detailed,
)
from .attribution import (
    compute_skill_attributions,
    is_learnable_outcome,
)

__all__ = [
    "CanonicalSkillResolver",
    "SkillRecord",
    "normalize_skill_ref",
    "parse_skill_text",
    "slugify",
    "SkillLifecycleTracker",
    "RankedSkillScore",
    "compute_semantic_relevance",
    "curate_shortlist",
    "rank_skills",
    "rank_skills_detailed",
    "compute_skill_attributions",
    "is_learnable_outcome",
]
