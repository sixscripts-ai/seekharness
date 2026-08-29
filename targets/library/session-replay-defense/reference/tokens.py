import base64, hashlib, hmac, json, secrets
KEY = b"arena-local-test-key"
SEEN = set()

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()

def issue(user: str, now: int, ttl: int = 30) -> str:
    payload = {"u": user, "exp": now + ttl, "n": secrets.token_hex(16)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(KEY, raw, hashlib.sha256).digest()
    return _b64(raw) + "." + _b64(sig)

def verify(token: str, now: int) -> str:
    try:
        raw_s, sig_s = token.split(".", 1)
        raw = base64.urlsafe_b64decode(raw_s.encode())
        sig = base64.urlsafe_b64decode(sig_s.encode())
        expected = hmac.new(KEY, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        payload = json.loads(raw)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("malformed token") from exc
    if now > int(payload["exp"]):
        raise ValueError("expired")
    nonce = payload["n"]
    if nonce in SEEN:
        raise ValueError("replay")
    SEEN.add(nonce)
    return str(payload["u"])
