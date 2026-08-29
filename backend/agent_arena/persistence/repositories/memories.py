"""Memory repository (plain rows; no vector search)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Memory


def memory_create(
    session: Session,
    *,
    user_id: str,
    insight: str,
    tokens: list[str] | None = None,
    battle_id: str | None = None,
    model_id: str | None = None,
    format: str | None = None,
    chosen_skills: list[str] | None = None,
    theory: str | None = None,
    outcome: str | None = None,
) -> Memory:
    memory = Memory(
        user_id=user_id,
        insight=insight,
        tokens=tokens or [],
        battle_id=battle_id,
        model_id=model_id,
        format=format,
        chosen_skills=chosen_skills or [],
        theory=theory,
        outcome=outcome,
    )
    session.add(memory)
    session.flush()
    return memory


def memory_list(
    session: Session,
    user_id: str | None = None,
    *,
    limit: int = 100,
) -> list[Memory]:
    stmt = select(Memory).order_by(Memory.created_at.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(Memory.user_id == user_id)
    return list(session.scalars(stmt))
