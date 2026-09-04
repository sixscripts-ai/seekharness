"""Battle repository: battle lifecycle plus ordered model slots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Battle, BattleParticipant

_ACTIVE_STATUSES = ("queued", "running")
_STALE_SCAN_LIMIT = 2000


def battle_create(
    session: Session,
    *,
    user_id: str,
    format_id: str,
    arena_size: int,
    timeout_seconds: int,
    round_visibility: str,
    model_ids: Sequence[str] = (),
    roles: Sequence[str | None] | None = None,
    id: str | None = None,
    status: str = "queued",
    saved: bool = False,
    sandbox_id: str | None = None,
    judge_provider_id: str | None = None,
    preview_urls: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    started_at=None,
    completed_at=None,
    difficulty: str | None = None,
    draft_id: str | None = None,
    battle_config: dict[str, Any] | None = None,
    spec_hash: str | None = None,
    custom_title: str | None = None,
    ranked: bool | None = None,
    target_id: str | None = None,
    target_version: str | None = None,
    target_manifest_hash: str | None = None,
) -> Battle:
    """Create a battle and its ordered participant slots in one transaction."""
    battle = Battle(
        id=id,
        user_id=user_id,
        format_id=format_id,
        arena_size=arena_size or len(model_ids),
        status=status,
        timeout_seconds=timeout_seconds,
        round_visibility=round_visibility,
        saved=saved,
        sandbox_id=sandbox_id,
        judge_provider_id=judge_provider_id,
        preview_urls=preview_urls,
        failure_reason=failure_reason,
        started_at=started_at,
        completed_at=completed_at,
        difficulty=difficulty,
        draft_id=draft_id,
        battle_config=battle_config,
        spec_hash=spec_hash,
        custom_title=custom_title,
        ranked=ranked,
        target_id=target_id,
        target_version=target_version,
        target_manifest_hash=target_manifest_hash,
    )
    session.add(battle)
    session.flush()  # assign battle.id so participants can reference it
    for position, model_id in enumerate(model_ids):
        role = None
        if roles and position < len(roles):
            role = roles[position]
        session.add(
            BattleParticipant(
                battle_id=battle.id,
                position=position,
                model_id=model_id,
                role=role,
            )
        )
    return battle


def battle_get(session: Session, battle_id: str) -> Battle | None:
    return session.get(Battle, battle_id)


_BATTLE_UPDATE_FIELDS = {
    "status", "timeout_seconds", "round_visibility", "saved",
    "sandbox_id", "judge_provider_id", "preview_urls",
    "failure_reason", "started_at", "completed_at", "difficulty",
    "draft_id", "battle_config", "spec_hash", "custom_title",
    "ranked", "target_id", "target_version", "target_manifest_hash",
    "arena_size", "user_id", "format_id",
}


def battle_update(session: Session, battle_id: str, **fields: Any) -> Battle | None:
    """Update whitelisted scalar fields; unknown keys raise TypeError."""
    battle = session.get(Battle, battle_id)
    if battle is None:
        return None
    unknown = set(fields) - _BATTLE_UPDATE_FIELDS
    if unknown:
        raise TypeError(f"unknown battle fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(battle, key, value)
    session.flush()
    return battle


def battle_list(
    session: Session,
    *,
    user_id: str | None = None,
    status: str | None = None,
    saved: bool | None = None,
    limit: int = 100,
) -> list[Battle]:
    """List battles, newest first."""
    stmt = select(Battle).order_by(Battle.created_at.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(Battle.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Battle.status == status)
    if saved is not None:
        stmt = stmt.where(Battle.saved == saved)
    return list(session.scalars(stmt))


def battle_list_active(
    session: Session,
    *,
    limit: int = _STALE_SCAN_LIMIT,
) -> list[Battle]:
    """Queued/running battles, oldest first. Used by the reaper."""
    stmt = (
        select(Battle)
        .where(Battle.status.in_(_ACTIVE_STATUSES))
        .order_by(Battle.created_at.asc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def battle_fail_if_active(
    session: Session,
    battle_id: str,
    *,
    reason: str,
    completed_at: datetime,
) -> Battle | None:
    """Fail a battle only if it is still queued/running. Idempotent for terminals."""
    battle = session.scalar(
        select(Battle).where(Battle.id == battle_id).with_for_update()
    )
    if battle is None or battle.status not in _ACTIVE_STATUSES:
        return None
    battle.status = "failed"
    battle.failure_reason = reason
    battle.completed_at = completed_at
    session.flush()
    return battle


def battle_model_ids(session: Session, battle_id: str) -> list[str]:
    """Reconstruct the API representation: model_ids ordered by position."""
    stmt = (
        select(BattleParticipant.model_id)
        .where(BattleParticipant.battle_id == battle_id)
        .order_by(BattleParticipant.position)
    )
    return list(session.scalars(stmt))
