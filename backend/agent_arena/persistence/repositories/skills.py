"""Skill record repository. Scoring/decay algorithms are not changed."""

from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import SkillRecord


def skill_upsert(
    session: Session,
    skill: str,
    *,
    elo: float | None = None,
    wins: int | None = None,
    losses: int | None = None,
    draws: int | None = None,
    uses: int | None = None,
    success_rate: float | None = None,
    tier: str | None = None,
    tags: list[str] | None = None,
    last_used: datetime | None = None,
) -> SkillRecord:
    values: dict[str, Any] = {"skill": skill}
    for key, value in (
        ("elo", elo),
        ("wins", wins),
        ("losses", losses),
        ("draws", draws),
        ("uses", uses),
        ("success_rate", success_rate),
        ("tier", tier),
        ("tags", tags),
        ("last_used", last_used),
    ):
        if value is not None:
            values[key] = value
    update_set = {
        key: value for key, value in values.items() if key != "skill"
    }
    stmt = (
        pg_insert(SkillRecord)
        .values(**values)
        .on_conflict_do_update(
            constraint="skills_pkey",
            set_=update_set or {"updated_at": SkillRecord.updated_at},
        )
        .returning(SkillRecord)
    )
    return session.scalars(stmt).one()


def skill_get(session: Session, skill: str) -> SkillRecord | None:
    return session.get(SkillRecord, skill)


def skill_list(session: Session) -> list[SkillRecord]:
    stmt = select(SkillRecord).order_by(SkillRecord.skill)
    return list(session.scalars(stmt))
