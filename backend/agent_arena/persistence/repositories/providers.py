"""Provider repository. encrypted_key stays Fernet ciphertext."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Provider


def provider_create(
    session: Session,
    *,
    user_id: str,
    name: str,
    base_url: str,
    encrypted_key: str,
    masked_key: str = "",
    auth_style: str = "bearer",
    model_name: str = "",
    id: str | None = None,
) -> Provider:
    provider = Provider(
        id=id,
        user_id=user_id,
        name=name,
        base_url=base_url,
        encrypted_key=encrypted_key,
        masked_key=masked_key,
        auth_style=auth_style,
        model_name=model_name,
    )
    session.add(provider)
    session.flush()
    return provider


def provider_get(session: Session, provider_id: str) -> Provider | None:
    return session.get(Provider, provider_id)


def provider_list(session: Session, user_id: str) -> list[Provider]:
    stmt = select(Provider).where(Provider.user_id == user_id).order_by(Provider.created_at)
    return list(session.scalars(stmt))


_PROVIDER_UPDATE_FIELDS = {
    "name", "base_url", "encrypted_key", "masked_key", "auth_style", "model_name",
}


def provider_update(session: Session, provider_id: str, **fields: Any) -> Provider | None:
    provider = session.get(Provider, provider_id)
    if provider is None:
        return None
    unknown = set(fields) - _PROVIDER_UPDATE_FIELDS
    if unknown:
        raise TypeError(f"unknown provider fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(provider, key, value)
    session.flush()
    return provider


def provider_delete(session: Session, provider_id: str) -> bool:
    provider = session.get(Provider, provider_id)
    if provider is None:
        return False
    session.delete(provider)
    session.flush()
    return True
