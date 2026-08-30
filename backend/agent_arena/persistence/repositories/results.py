"""BattleResult repository with atomic idempotency on composite identity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import BattleResult


def result_upsert(
    session: Session,
    *,
    battle_id: str,
    phase: str = "main",
    role: str = "fighter",
    model_id: str,
    status: str = "completed",
    passed: bool = False,
    score: float = 0.0,
    verification_status: str = "unverified",
    termination_reason: str | None = None,
    artifact_refs: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    result_version: int = 1,
    finalized_at: datetime | None = None,
) -> BattleResult:
    """Insert or update an authoritative result row on composite identity (battle_id, phase, role, model_id)."""
    values: dict[str, Any] = {
        "battle_id": battle_id,
        "phase": phase,
        "role": role,
        "model_id": model_id,
        "status": status,
        "passed": passed,
        "score": score,
        "verification_status": verification_status,
        "termination_reason": termination_reason,
        "artifact_refs": list(artifact_refs or []),
        "metrics": dict(metrics or {}),
        "result_version": result_version,
        "finalized_at": finalized_at or datetime.now(timezone.utc),
    }

    insert_stmt = pg_insert(BattleResult).values(**values)
    stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_battle_results_identity",
        set_={
            "status": insert_stmt.excluded.status,
            "passed": insert_stmt.excluded.passed,
            "score": insert_stmt.excluded.score,
            "verification_status": insert_stmt.excluded.verification_status,
            "termination_reason": insert_stmt.excluded.termination_reason,
            "artifact_refs": insert_stmt.excluded.artifact_refs,
            "metrics": insert_stmt.excluded.metrics,
            "result_version": insert_stmt.excluded.result_version,
            "finalized_at": insert_stmt.excluded.finalized_at,
        },
    ).returning(BattleResult.id)

    result_id = session.execute(stmt).scalar_one()
    session.expire_all()
    return session.get(BattleResult, result_id)  # type: ignore[return-value]


def results_list_by_battle(session: Session, battle_id: str) -> list[BattleResult]:
    """List all authoritative results for a given battle ordered by phase, role, model_id."""
    stmt = (
        select(BattleResult)
        .where(BattleResult.battle_id == battle_id)
        .order_by(BattleResult.phase, BattleResult.role, BattleResult.model_id)
    )
    return list(session.scalars(stmt))


def result_get(
    session: Session,
    battle_id: str,
    phase: str,
    role: str,
    model_id: str,
) -> BattleResult | None:
    stmt = select(BattleResult).where(
        BattleResult.battle_id == battle_id,
        BattleResult.phase == phase,
        BattleResult.role == role,
        BattleResult.model_id == model_id,
    )
    return session.scalars(stmt).first()
