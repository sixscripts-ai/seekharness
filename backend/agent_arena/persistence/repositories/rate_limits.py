"""Atomic per-battle sliding-window admission for internal callbacks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..models import BattleRateLimit

DEFAULT_LIMIT = 120
DEFAULT_WINDOW_SECONDS = 60.0


def decide_admission(
    timestamps: list[float],
    now: float,
    *,
    limit: int = DEFAULT_LIMIT,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> tuple[bool, list[float]]:
    """Prune expired calls and decide whether `now` may be recorded.

    Rejected calls are not appended. Expired timestamps are dropped from the
    returned window so a reject can persist cleanup without recording admission.
    """
    pruned = [float(t) for t in timestamps if now - float(t) < window_seconds]
    if len(pruned) >= limit:
        return False, pruned
    return True, pruned + [now]


def rate_limit_lock_or_create(session: Session, battle_id: str) -> BattleRateLimit:
    """Insert an empty window row if needed, then lock it for this transaction."""
    session.execute(
        pg_insert(BattleRateLimit)
        .values(battle_id=battle_id, window_ts=[])
        .on_conflict_do_nothing(index_elements=["battle_id"])
    )
    session.flush()
    return session.scalars(
        select(BattleRateLimit)
        .where(BattleRateLimit.battle_id == battle_id)
        .with_for_update()
    ).one()


def rate_limit_admit(
    session: Session,
    battle_id: str,
    *,
    now: float,
    limit: int = DEFAULT_LIMIT,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> bool:
    """Admit one call under a row lock. False means reject with no new timestamp."""
    row = rate_limit_lock_or_create(session, battle_id)
    current = list(row.window_ts or [])
    admitted, updated = decide_admission(
        [float(t) for t in current],
        now,
        limit=limit,
        window_seconds=window_seconds,
    )
    if admitted or updated != current:
        row.window_ts = updated
        flag_modified(row, "window_ts")
    return admitted


def rate_limit_window(session: Session, battle_id: str) -> list[Any]:
    row = session.get(BattleRateLimit, battle_id)
    if row is None:
        return []
    return list(row.window_ts or [])
