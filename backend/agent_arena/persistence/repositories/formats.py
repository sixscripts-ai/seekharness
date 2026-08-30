"""Format repository: list/create/update. Loading semantics are unchanged."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Format


def format_create(
    session: Session,
    *,
    name: str,
    engine: str,
    config: dict[str, Any],
    id: str | None = None,
) -> Format:
    fmt = Format(id=id, name=name, engine=engine, config=config)
    session.add(fmt)
    session.flush()
    return fmt


def format_get(session: Session, format_id: str) -> Format | None:
    return session.get(Format, format_id)


def format_list(session: Session) -> list[Format]:
    stmt = select(Format).order_by(Format.name)
    return list(session.scalars(stmt))


_FORMAT_UPDATE_FIELDS = {"name", "engine", "config"}


def format_update(session: Session, format_id: str, **fields: Any) -> Format | None:
    fmt = session.get(Format, format_id)
    if fmt is None:
        return None
    unknown = set(fields) - _FORMAT_UPDATE_FIELDS
    if unknown:
        raise TypeError(f"unknown format fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(fmt, key, value)
    session.flush()
    return fmt
