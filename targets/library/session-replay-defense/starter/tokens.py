import base64, hashlib, hmac, json, secrets
KEY = b"arena-local-test-key"
SEEN = set()

def issue(user: str, now: int, ttl: int = 30) -> str:
    payload = {"u": user, "exp": now + ttl, "n": secrets.token_hex(8)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    # TODO: authenticate payload.
    return base64.urlsafe_b64encode(raw).decode()

def verify(token: str, now: int) -> str:
    # TODO: authenticate, enforce expiry, and prevent replay.
    raw = base64.urlsafe_b64decode(token.encode())
    payload = json.loads(raw)
    return payload["u"]
