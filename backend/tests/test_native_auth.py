import pytest
from fastapi.testclient import TestClient

from agent_arena.main import app
from agent_arena.native_auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from agent_arena.persistence.session import session_scope
from agent_arena.persistence.models import User

from agent_arena.hermetic import hermetic_mode

client = TestClient(app)


def test_password_hashing():
    raw = "super_secret_123"
    h = hash_password(raw)
    assert h.startswith("scrypt$")
    assert verify_password(raw, h) is True
    assert verify_password("wrong_password", h) is False
    assert verify_password("", h) is False


def test_jwt_token_cycle():
    token = create_access_token(
        user_id="usr_test_1",
        email="test@example.com",
        name="Tester",
        expires_minutes=60,
    )
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "usr_test_1"
    assert payload["email"] == "test@example.com"
    assert payload["name"] == "Tester"

    # Tampered signature
    assert decode_access_token(token + "x") is None
    # Empty token
    assert decode_access_token("") is None


def test_expired_token():
    token = create_access_token(
        user_id="usr_expired",
        email="expired@example.com",
        expires_minutes=-5,  # already expired
    )
    assert decode_access_token(token) is None


@pytest.mark.skipif(
    hermetic_mode(),
    reason="Requires live PostgreSQL (set ARENA_INTEGRATION_TESTS=1)",
)
def test_auth_signup_and_login():
    email = "native_user_test@example.com"
    password = "valid_password_456"

    # Cleanup if previously exists from a previous test run
    with session_scope() as session:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            session.delete(existing)
            session.commit()

    # 1. Signup
    res = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "name": "Native Tester"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == email
    assert data["user"]["name"] == "Native Tester"
    assert data["user"]["id"] == data["user"]["$id"]
    token = data["token"]

    # 2. Duplicate signup fails with 409
    dup = client.post(
        "/auth/signup",
        json={"email": email, "password": "anypassword"},
    )
    assert dup.status_code == 409

    # 3. /auth/me with valid Bearer token
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 4. Login with valid credentials
    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    assert "token" in login_res.json()

    # 5. Login with invalid password fails with 401
    bad_login = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong_password"},
    )
    assert bad_login.status_code == 401

    # Clean up test user
    with session_scope() as session:
        u = session.query(User).filter(User.email == email).first()
        if u:
            session.delete(u)
            session.commit()
