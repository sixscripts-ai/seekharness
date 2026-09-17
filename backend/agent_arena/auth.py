from fastapi import Header, HTTPException

from .config import settings
from .native_auth import decode_access_token

try:
    from appwrite.client import Client
    from appwrite.services.account import Account
except ImportError:
    Client = None
    Account = None


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    # 1. Native JWT validation (primary)
    payload = decode_access_token(token)
    if payload and payload.get("sub"):
        return str(payload["sub"])

    # 2. Legacy Appwrite fallback (for in-flight transitions)
    if Client is not None and Account is not None:
        try:
            s = settings()
            endpoint = s.get("APPWRITE_ENDPOINT")
            project_id = s.get("APPWRITE_PROJECT_ID")
            if endpoint and project_id:
                client = (
                    Client()
                    .set_endpoint(endpoint)
                    .set_project(project_id)
                    .set_jwt(token)
                )
                account = Account(client).get()
                return account["$id"] if isinstance(account, dict) else account.id
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid or expired session")


def get_optional_user(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None



def require_owner(owner_id: str | None, user_id: str, resource: str = "resource") -> None:
    """Raise 403 unless ``owner_id`` matches the authenticated ``user_id``.

    Centralises the ownership assertion so user-scoped data routes can't
    accidentally drop the check during a refactor. ``owner_id`` must be the
    value stored on the document, never a client-supplied field.
    """
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail=f"Not your {resource}")
