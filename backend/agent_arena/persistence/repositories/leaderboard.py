"""Leaderboard repository keyed by (model_id, scope)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import LeaderboardEntry


def leaderboard_get(session: Session, model_id: str, scope: str) -> LeaderboardEntry | None:
    return session.get(LeaderboardEntry, (model_id, scope))


def leaderboard_upsert(
    session: Session,
    model_id: str,
    scope: str,
    *,
    elo: float | None = None,
    games_played: int | None = None,
) -> LeaderboardEntry:
    """Insert or update a ranking row atomically on the composite key."""
    values: dict[str, Any] = {"model_id": model_id, "scope": scope}
    if elo is not None:
        values["elo"] = elo
    if games_played is not None:
        values["games_played"] = games_played
    update_set = {
        key: value for key, value in values.items() if key not in ("model_id", "scope")
    }
    stmt = (
        pg_insert(LeaderboardEntry)
        .values(**values)
        .on_conflict_do_update(
            constraint="leaderboard_pkey",
            set_=update_set or {"updated_at": LeaderboardEntry.updated_at},
        )
        .returning(LeaderboardEntry)
    )
    return session.scalars(stmt).one()


def leaderboard_list(
    session: Session,
    scope: str,
    *,
    limit: int = 100,
) -> list[LeaderboardEntry]:
    stmt = (
        select(LeaderboardEntry)
        .where(LeaderboardEntry.scope == scope)
        .order_by(LeaderboardEntry.elo.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
