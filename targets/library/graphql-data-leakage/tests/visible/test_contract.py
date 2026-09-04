from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_contract():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_graphql_public_catalog_query():
    query = "{ publicCatalog { id name price } }"
    res = client.post("/graphql", json={"query": query})
    assert res.status_code == 200
    data = res.json()
    assert "data" in data
    assert "publicCatalog" in data["data"]
    assert len(data["data"]["publicCatalog"]) > 0


def test_graphql_me_query_authorized():
    query = "{ me { id name email } }"
    res = client.post("/graphql", json={"query": query})
    assert res.status_code == 200
    data = res.json()
    assert "data" in data
    assert "me" in data["data"]
    assert data["data"]["me"]["name"] == "Alice Developer"
