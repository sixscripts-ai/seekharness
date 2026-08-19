"""Per-battle, expiring internal tokens for sandbox → backend callbacks.

Before this module, every spawned sandbox received the *global*
``INTERNAL_API_KEY`` and used it on every ``/internal/*`` call. That means a
single compromised sandbox could read the shared key and use it to (1) drive
*any* battle's model calls and (2) reach other users' decrypted provider keys
via ``/internal/model``.

This module replaces that with **scoped, short-lived tokens**:

* A token is signed with the global ``INTERNAL_API_KEY`` (which stays on the
  backend only) and binds ``battle_id`` + an expiry timestamp.
* The sandbox receives only this derived token, never the global key.
* Verification re-checks the signature, the battle scope, and the expiry, so a
  leaked token is useless for any other battle and dies shortly after the
  battle window anyway.

No database schema change is required: the token is self-contained (HMAC over
``battle_id|expiry``). This keeps the existing ``INTERNAL_API_KEY`` env as the
signing secret, so current configs keep working unchanged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

TOKEN_TTL_SECONDS = 3600  # 1 hour; comfortably longer than max battle (3600s)


def _signing_secret() -> str:
    from .config import settings

    # Lazy import to avoid pulling config at module import time in tests.
    return settings().get("INTERNAL_API_KEY") or ""


def _digest(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def issue_battle_token(battle_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Return a signed, battle-scoped token for a sandbox to call back with."""
    secret = _signing_secret()
    if not secret:
        raise RuntimeError("INTERNAL_API_KEY not configured")
    expires = int(time.time()) + ttl
    payload = f"{battle_id}|{expires}"
    sig = _digest(secret, payload)
    raw = f"{battle_id}|{expires}|{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_battle_token(token: str, battle_id: str) -> bool:
    """Return True if ``token`` is valid for ``battle_id`` and unexpired."""
    if not token:
        return False
    secret = _signing_secret()
    if not secret:
        return False
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    except Exception:
        return False
    parts = raw.split("|")
    if len(parts) != 3:
        return False
    tok_battle, expires_s, sig = parts
    if tok_battle != battle_id:
        return False
    try:
        expires = int(expires_s)
    except ValueError:
        return False
    if time.time() > expires:
        return False
    expected = _digest(secret, f"{tok_battle}|{expires_s}")
    return hmac.compare_digest(sig, expected)
