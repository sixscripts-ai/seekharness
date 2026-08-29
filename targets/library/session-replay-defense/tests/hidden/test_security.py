import base64, json, pytest
import tokens

def test_expired_token_rejected():
    t = tokens.issue("bob", 100, ttl=5)
    with pytest.raises(ValueError):
        tokens.verify(t, 106)

def test_tamper_rejected():
    t = tokens.issue("guest", 100)
    parts = t.split(".")
    assert len(parts) == 2
    raw = base64.urlsafe_b64decode(parts[0].encode())
    payload = json.loads(raw)
    payload["u"] = "admin"
    forged_raw = json.dumps(payload, separators=(",", ":")).encode()
    forged = base64.urlsafe_b64encode(forged_raw).decode() + "." + parts[1]
    with pytest.raises(ValueError):
        tokens.verify(forged, 101)

def test_independent_tokens_are_unique():
    a = tokens.issue("x", 100)
    b = tokens.issue("x", 100)
    assert a != b
