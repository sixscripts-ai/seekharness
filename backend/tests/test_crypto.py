import pytest

from agent_arena.crypto import decrypt_key, encrypt_key, mask_key, new_key


def test_roundtrip():
    key = new_key()
    token = encrypt_key("sk-secret-value-1234567890", key)
    assert decrypt_key(token, key) == "sk-secret-value-1234567890"


def test_rotation_old_key_still_decrypts():
    # Simulate a key rotation: data encrypted with old key must still decrypt
    # when the caller provides the old key (multi-key lookup happens upstream).
    old = new_key()
    new = new_key()
    token = encrypt_key("secret", old, version="v1")
    assert decrypt_key(token, old) == "secret"
    # New writes use the new key and carry a version marker.
    token2 = encrypt_key("secret", new, version="v2")
    assert "v2:" in token2
    assert decrypt_key(token2, new) == "secret"


def test_unknown_version_fails():
    key = new_key()
    token = "bogus-version:" + encrypt_key("secret", key)
    with pytest.raises(ValueError):
        decrypt_key(token, key)


def test_wrong_key_fails():
    key = new_key()
    token = encrypt_key("secret", key)
    with pytest.raises(ValueError):
        decrypt_key(token, new_key())


def test_tampered_token_fails():
    key = new_key()
    token = encrypt_key("secret", key)
    with pytest.raises(ValueError):
        decrypt_key(token[:-1] + ("X" if token[-1] != "X" else "Y"), key)


def test_mask():
    assert mask_key("sk-abcdefghijkl1234") == "sk-a********1234"
    assert mask_key("short") == "*****"
    assert "sk-abcdefghijkl1234" not in mask_key("sk-abcdefghijkl1234")
