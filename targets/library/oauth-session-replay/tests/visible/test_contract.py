from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_contract():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_oauth_flow_authorized():
    # 1. Authorize
    auth_res = client.post("/oauth/authorize", json={
        "client_id": "client_1",
        "code_challenge": "E9Melhoa2OwvFrGMTJguCH5rtx6441C8E_08C61mqAw",
        "code_challenge_method": "S256"
    })
    assert auth_res.status_code == 200
    code = auth_res.json()["authorization_code"]

    # 2. Token exchange
    tok_res = client.post("/oauth/token", json={
        "client_id": "client_1",
        "code": code,
        "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    })
    assert tok_res.status_code == 200
    token = tok_res.json()["access_token"]

    # 3. Profile
    prof_res = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
    assert prof_res.status_code == 200
    assert prof_res.json()["role"] == "user"
