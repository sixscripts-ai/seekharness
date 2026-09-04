from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_contract():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_logs_endpoint_available():
    res = client.get("/api/webhooks/logs")
    assert res.status_code == 200
    assert "logs" in res.json()


def test_loopback_ip_rejected():
    res = client.post("/api/webhooks/test", json={"url": "http://127.0.0.1:8000/internal/secrets/canary"})
    assert res.status_code == 400
    assert "Disallowed" in res.json().get("detail", "")
