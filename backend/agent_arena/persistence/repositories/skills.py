"""Skill record repository. Scoring/decay algorithms are not changed."""

from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import SkillRecord


def skill_lock_for_update(session: Session, skill: str) -> SkillRecord:
    """Race-safe skill row: insert if missing, then SELECT ... FOR UPDATE."""
    from agent_arena import elo as elo_mod

    session.execute(
        pg_insert(SkillRecord)
        .values(
            skill=skill,
            elo=elo_mod.INITIAL_RATING,
            wins=0,
            losses=0,
            draws=0,
            uses=0,
            success_rate=0.0,
            tags=[],
        )
        .on_conflict_do_nothing(index_elements=["skill"])
    )
    return session.scalars(
        select(SkillRecord).where(SkillRecord.skill == skill).with_for_update()
    ).one()


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
        .returning(SkillRecord.skill)
    )
    skill_key = session.execute(stmt).scalar_one()
    session.expire_all()
    return session.get(SkillRecord, skill_key)  # type: ignore[return-value]



def skill_get(session: Session, skill: str) -> SkillRecord | None:
    return session.get(SkillRecord, skill)


def skill_list(session: Session) -> list[SkillRecord]:
    stmt = select(SkillRecord).order_by(SkillRecord.skill)
    return list(session.scalars(stmt))
