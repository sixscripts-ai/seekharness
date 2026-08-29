"""Battle event append/list with idempotent event ids."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import BattleEvent


def event_append(
    session: Session,
    battle_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
    sequence: int | None = None,
) -> BattleEvent:
    """Append an event; a duplicate event_id is a no-op returning the existing row."""
    event = BattleEvent(
        battle_id=battle_id,
        event_id=event_id or "",
        event_type=event_type,
        sequence=sequence,
        payload=payload,
    )
    try:
        session.add(event)
        session.flush()
        return event
    except IntegrityError:
        session.rollback()
        existing = event_get_by_event_id(session, event.event_id)
        if existing is not None:
            return existing
        raise


def event_get_by_event_id(session: Session, event_id: str) -> BattleEvent | None:
    stmt = select(BattleEvent).where(BattleEvent.event_id == event_id)
    return session.scalars(stmt).first()


def event_list(
    session: Session,
    battle_id: str,
    *,
    event_type: str | None = None,
    limit: int = 500,
) -> list[BattleEvent]:
    stmt = (
        select(BattleEvent)
        .where(BattleEvent.battle_id == battle_id)
        .order_by(BattleEvent.created_at, BattleEvent.sequence)
        .limit(limit)
    )
    if event_type is not None:
        stmt = stmt.where(BattleEvent.event_type == event_type)
    return list(session.scalars(stmt))
