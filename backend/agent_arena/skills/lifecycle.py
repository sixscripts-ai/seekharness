"""Skill lifecycle state tracking.

Maintains strict separation between the distinct stages of a skill during a battle:
eligible -> ranked -> offered -> selected -> loaded -> used -> attributed.
Prohibits inferring one state from another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillLifecycleTracker:
    role: str = ""
    model_id: str = ""
    eligible_skill_ids: list[str] = field(default_factory=list)
    ranked_skill_ids: list[str] = field(default_factory=list)
    ranking_scores: dict[str, float] = field(default_factory=dict)
    semantic_scores: dict[str, float] = field(default_factory=dict)
    historical_adjustments: dict[str, float] = field(default_factory=dict)
    ranking_reasons: dict[str, str] = field(default_factory=dict)
    offered_skill_ids: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    loaded_skill_ids: list[str] = field(default_factory=list)
    load_failures: dict[str, str] = field(default_factory=dict)
    used_skill_ids: list[str] = field(default_factory=list)
    attributed_skill_ids: list[str] = field(default_factory=list)
    attribution_outcome: str = "none"

    def record_eligible(self, skill_id: str) -> None:
        if skill_id and skill_id not in self.eligible_skill_ids:
            self.eligible_skill_ids.append(skill_id)

    def record_ranked(
        self,
        skill_id: str,
        score: float,
        reason: str = "",
        semantic_score: float | None = None,
        historical_adjustment: float = 0.0,
    ) -> None:
        if skill_id not in self.ranked_skill_ids:
            self.ranked_skill_ids.append(skill_id)
        self.ranking_scores[skill_id] = round(float(score), 3)
        self.semantic_scores[skill_id] = round(float(semantic_score if semantic_score is not None else score), 3)
        self.historical_adjustments[skill_id] = round(float(historical_adjustment), 3)
        if reason:
            self.ranking_reasons[skill_id] = reason

    def record_offered(self, skill_id: str) -> None:
        if skill_id and skill_id not in self.offered_skill_ids:
            self.offered_skill_ids.append(skill_id)

    def record_selected(self, skill_id: str) -> None:
        """Record explicit fighter selection of a skill."""
        if skill_id and skill_id not in self.selected_skill_ids:
            self.selected_skill_ids.append(skill_id)

    def record_loaded(self, skill_id: str) -> None:
        """Record successful mounting/loading of a skill into workspace."""
        if skill_id and skill_id not in self.loaded_skill_ids:
            self.loaded_skill_ids.append(skill_id)

    def record_load_failed(self, skill_id: str, error: str) -> None:
        self.load_failures[skill_id] = error

    def record_used(self, skill_id: str) -> None:
        """Record observable fighter usage (reading instruction or calling skill tool)."""
        if skill_id and skill_id not in self.used_skill_ids:
            self.used_skill_ids.append(skill_id)

    def record_attributed(self, skill_id: str, outcome: str) -> None:
        """Record authoritative post-battle outcome attribution."""
        if skill_id and skill_id not in self.attributed_skill_ids:
            self.attributed_skill_ids.append(skill_id)
        self.attribution_outcome = outcome

    def to_telemetry(self) -> dict[str, Any]:
        return {
            "eligible_skill_ids": list(self.eligible_skill_ids),
            "ranked_skill_ids": list(self.ranked_skill_ids),
            "ranking_scores": dict(self.ranking_scores),
            "semantic_scores": dict(self.semantic_scores),
            "historical_adjustments": dict(self.historical_adjustments),
            "ranking_reasons": dict(self.ranking_reasons),
            "offered_skill_ids": list(self.offered_skill_ids),
            "selected_skill_ids": list(self.selected_skill_ids),
            "loaded_skill_ids": list(self.loaded_skill_ids),
            "load_failures": dict(self.load_failures),
            "used_skill_ids": list(self.used_skill_ids),
            "attributed_skill_ids": list(self.attributed_skill_ids),
            "attribution_outcome": self.attribution_outcome,
        }
