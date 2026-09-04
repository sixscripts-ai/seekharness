from fastapi.testclient import TestClient

from agent_arena.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["project"]
    # Hermetic pytest forces Appwrite-primary so tests never open Neon.
    assert body["persistence_backend"] == "appwrite"
    assert body["appwrite_dual_write"] is False
    assert body["appwrite_read_fallback"] is False
