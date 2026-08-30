"""Memory repository (plain rows; provenance columns match Change Set B)."""

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
    target_id: str | None = None,
    role: str | None = None,
    visibility_class: str | None = None,
    authoritative_status: str | None = None,
    context_mode: str | None = None,
    source_result_id: str | None = None,
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
        target_id=target_id,
        role=role,
        visibility_class=visibility_class,
        authoritative_status=authoritative_status,
        context_mode=context_mode,
        source_result_id=source_result_id,
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


def memory_list_all(session: Session, *, limit: int = 200) -> list[Memory]:
    stmt = select(Memory).order_by(Memory.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def memory_to_dict(row: Memory) -> dict:
    created = row.created_at.timestamp() if row.created_at is not None else 0.0
    return {
        "id": row.id,
        "user_id": row.user_id,
        "insight": row.insight,
        "tokens": row.tokens or [],
        "battle_id": row.battle_id,
        "model_id": row.model_id,
        "format": row.format,
        "chosen_skills": row.chosen_skills or [],
        "theory": row.theory,
        "outcome": row.outcome,
        "target_id": row.target_id,
        "role": row.role,
        "visibility_class": row.visibility_class,
        "authoritative_status": row.authoritative_status,
        "context_mode": row.context_mode,
        "source_result_id": row.source_result_id,
        "created_at": created,
    }
