from appwrite.client import Client
from appwrite.services.account import Account
from fastapi import Header, HTTPException

from .config import settings


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        # JWT auth must not share a client that has the server API key set —
        # Appwrite prefers the key and Account.get() then fails as a guest.
        s = settings()
        client = (
            Client()
            .set_endpoint(s["APPWRITE_ENDPOINT"])
            .set_project(s["APPWRITE_PROJECT_ID"])
            .set_jwt(token)
        )
        account = Account(client).get()
        return account["$id"] if isinstance(account, dict) else account.id
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


def require_owner(owner_id: str | None, user_id: str, resource: str = "resource") -> None:
    """Raise 403 unless ``owner_id`` matches the authenticated ``user_id``.

    Centralises the ownership assertion so user-scoped data routes can't
    accidentally drop the check during a refactor. ``owner_id`` must be the
    value stored on the document, never a client-supplied field.
    """
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail=f"Not your {resource}")
