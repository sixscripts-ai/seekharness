from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_contract():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "ok"


def test_vault_unauthorized():
    res = client.get("/api/vault")
    assert res.status_code == 401
