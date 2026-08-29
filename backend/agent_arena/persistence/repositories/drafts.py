"""Battle draft repository with optimistic revision semantics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BattleDraft


def draft_create(
    session: Session,
    *,
    user_id: str,
    mode: str,
    transcript: list[Any] | None = None,
    spec: dict[str, Any] | None = None,
    id: str | None = None,
) -> BattleDraft:
    draft = BattleDraft(
        id=id,
        user_id=user_id,
        mode=mode,
        transcript=transcript or [],
        spec=spec or {},
    )
    session.add(draft)
    session.flush()
    return draft


def draft_get(session: Session, draft_id: str) -> BattleDraft | None:
    return session.get(BattleDraft, draft_id)


_DRAFT_UPDATE_FIELDS = {
    "mode", "transcript", "spec", "status", "launched_battle_id", "architect_error",
}


def draft_update(
    session: Session,
    draft_id: str,
    *,
    expected_revision: int | None = None,
    **fields: Any,
) -> tuple[BattleDraft | None, bool]:
    """Apply a draft update with optimistic concurrency.

    Returns (draft, applied). When expected_revision is given and the stored
    revision differs, the update is NOT applied and (draft, False) is
    returned so callers can surface a conflict. The revision increments by
    one on every successful update.
    """
    draft = session.get(BattleDraft, draft_id)
    if draft is None:
        return None, False
    if expected_revision is not None and draft.revision != expected_revision:
        return draft, False
    unknown = set(fields) - _DRAFT_UPDATE_FIELDS
    if unknown:
        raise TypeError(f"unknown draft fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(draft, key, value)
    draft.revision += 1
    session.flush()
    return draft, True


def draft_list(session: Session, user_id: str | None = None) -> list[BattleDraft]:
    stmt = select(BattleDraft).order_by(BattleDraft.created_at.desc())
    if user_id is not None:
        stmt = stmt.where(BattleDraft.user_id == user_id)
    return list(session.scalars(stmt))
