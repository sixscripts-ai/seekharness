import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from agent_arena.auth import get_current_user

app = FastAPI()


@app.get("/me")
def me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}


class _ChainClient:
    def __init__(self):
        self.jwt = None

    def set_endpoint(self, value):
        return self

    def set_project(self, value):
        return self

    def set_jwt(self, token):
        self.jwt = token
        return self


def test_missing_header_rejected():
    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 401


def test_non_bearer_rejected():
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401


def test_returns_native_jwt_user_id():
    from agent_arena.native_auth import create_access_token
    token = create_access_token(user_id="user-native-999", email="native@test.com")
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "user-native-999"}


def test_returns_appwrite_user_id(monkeypatch):
    class FakeAccount:
        def __init__(self, client):
            assert client.jwt == "real.jwt.token"

        def get(self):
            return {"$id": "user-abc"}

    monkeypatch.setattr("agent_arena.auth.Client", _ChainClient)
    monkeypatch.setattr("agent_arena.auth.Account", FakeAccount)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer real.jwt.token"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "user-abc"}


def test_returns_appwrite_user_model_id(monkeypatch):
    class FakeAccount:
        def __init__(self, client):
            assert client.jwt == "real.jwt.token"

        def get(self):
            return SimpleNamespace(id="user-xyz")

    monkeypatch.setattr("agent_arena.auth.Client", _ChainClient)
    monkeypatch.setattr("agent_arena.auth.Account", FakeAccount)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer real.jwt.token"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "user-xyz"}


def test_invalid_jwt_rejected(monkeypatch):
    class Boom(Exception):
        pass

    class FakeAccount:
        def __init__(self, client):
            pass

        def get(self):
            raise Boom()

    monkeypatch.setattr("agent_arena.auth.Client", _ChainClient)
    monkeypatch.setattr("agent_arena.auth.Account", FakeAccount)
    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer bad.jwt.token"})
    assert resp.status_code == 401


def test_optional_user_allows_unauthenticated(monkeypatch):
    from agent_arena.auth import get_optional_user

    opt_app = FastAPI()

    @opt_app.get("/public")
    def pub(user_id: str | None = Depends(get_optional_user)):
        return {"user_id": user_id}

    client = TestClient(opt_app)
    # No header -> user_id is None
    resp = client.get("/public")
    assert resp.status_code == 200
    assert resp.json() == {"user_id": None}

    # Invalid header -> user_id is None (fails open for public spectator)
    resp = client.get("/public", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": None}


def test_optional_user_resolves_valid_jwt(monkeypatch):
    from agent_arena.auth import get_optional_user

    opt_app = FastAPI()

    @opt_app.get("/public")
    def pub(user_id: str | None = Depends(get_optional_user)):
        return {"user_id": user_id}

    class FakeAccount:
        def __init__(self, client):
            assert client.jwt == "good.jwt"

        def get(self):
            return {"$id": "user-spectator-1"}

    monkeypatch.setattr("agent_arena.auth.Client", _ChainClient)
    monkeypatch.setattr("agent_arena.auth.Account", FakeAccount)

    client = TestClient(opt_app)
    resp = client.get("/public", headers={"Authorization": "Bearer good.jwt"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "user-spectator-1"}

