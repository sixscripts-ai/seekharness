import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from .config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password using NIST-approved Scrypt with 16-byte random salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        maxmem=32 * 1024 * 1024,
    )
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored scrypt hash in constant time."""
    if not password or not hashed:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3 or parts[0] != "scrypt":
            return False
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
        key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            maxmem=32 * 1024 * 1024,
        )
        return secrets.compare_digest(key, expected)
    except Exception:
        return False


def _get_signing_secret() -> bytes:
    s = settings()
    secret = (
        os.environ.get("JWT_SECRET")
        or s.get("INTERNAL_API_KEY")
        or s.get("FERNET_KEY")
        or "seekharness-default-native-secret-32b-key!"
    )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def create_access_token(
    user_id: str,
    email: str,
    name: str | None = None,
    expires_minutes: int = 60 * 24 * 7,  # 7 days default
) -> str:
    """Issue a standard RFC 7519 HS256 JWT access token."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "name": name or "",
        "iat": now,
        "exp": now + (expires_minutes * 60),
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    secret = _get_signing_secret()
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify an HS256 JWT access token."""
    if not token or not isinstance(token, str):
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    secret = _get_signing_secret()
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    try:
        provided_sig = _b64url_decode(sig_b64)
        if not secrets.compare_digest(expected_sig, provided_sig):
            return None
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        if not isinstance(payload, dict):
            return None

        # Check expiration
        exp = payload.get("exp")
        if exp is not None and int(exp) < time.time():
            return None

        return payload
    except Exception:
        return None
