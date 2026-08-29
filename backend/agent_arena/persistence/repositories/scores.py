"""Score repository with database-level idempotency."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Score


def score_insert(
    session: Session,
    *,
    battle_id: str,
    model_id: str,
    score: float,
    judge_model: str | None = None,
    justification: str | None = None,
) -> Score:
    """Insert a score; re-inserting the same (battle_id, model_id) returns the
    existing row instead of duplicating (ON CONFLICT DO NOTHING)."""
    stmt = (
        pg_insert(Score)
        .values(
            battle_id=battle_id,
            model_id=model_id,
            score=score,
            judge_model=judge_model,
            justification=justification,
        )
        .on_conflict_do_nothing(constraint="uq_scores_battle_model")
        .returning(Score)
    )
    row = session.scalars(stmt).first()
    if row is None:
        row = session.scalars(
            select(Score).where(Score.battle_id == battle_id, Score.model_id == model_id)
        ).one()
    return row


def score_list(session: Session, battle_id: str) -> list[Score]:
    stmt = select(Score).where(Score.battle_id == battle_id).order_by(Score.model_id)
    return list(session.scalars(stmt))
