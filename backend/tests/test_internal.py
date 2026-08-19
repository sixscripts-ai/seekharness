import pytest

from agent_arena.config import settings
from tests.conftest import make_user_id, requires_appwrite


@pytest.fixture
def internal_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    settings.cache_clear()
    yield "test-internal-key"
    settings.cache_clear()


def test_internal_requires_key(client, internal_key):
    resp = client.post("/internal/model", json={
        "battle_id": "x", "model_id": "y", "messages": [],
    })
    assert resp.status_code == 401


def test_internal_rejects_legacy_global_key_for_battle(client, internal_key):
    # Strict mode: the global key is no longer a valid credential for
    # battle-scoped endpoints — only the per-battle token works.
    from agent_arena.battle_token import issue_battle_token

    token = issue_battle_token("x")
    ok_resp = client.post(
        "/internal/status",
        headers={"X-Sandbox-Token": token},
        json={"battle_id": "x"},
    )
    # 404 (battle not found) means auth passed; 401 would mean token rejected.
    assert ok_resp.status_code in (404, 200)

    legacy_resp = client.post(
        "/internal/status",
        headers={"X-Internal-Key": internal_key},
        json={"battle_id": "x"},
    )
    assert legacy_resp.status_code == 401


def test_internal_hidden_from_openapi(client, internal_key):
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert not any(p.startswith("/internal") for p in paths)


@requires_appwrite
def test_internal_model_validates_battle(client, internal_key, monkeypatch):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app
    from agent_arena import llm_client
    from appwrite.query import Query
    from agent_arena import db
    from agent_arena.battle_token import issue_battle_token

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    monkeypatch.setattr(llm_client, "chat_completion", lambda **kw: "hello from model")
    try:
        formats = client.get("/formats").json()
        fmt_id = formats[0]["id"]
        battle = client.post("/battles", json={
            "format_id": fmt_id,
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert battle.status_code == 201, battle.text
        bid = battle.json()["id"]
        token = issue_battle_token(bid)
        # cancel immediately so mock runner doesn't race forever; status cancelled
        # won't accept internal model — use while still queued by setting running
        databases = db.get_databases()
        databases.update_document(db.get_database_id(), "battles", bid, {"status": "running"})

        bad = client.post(
            "/internal/model",
            headers={"X-Sandbox-Token": token},
            json={"battle_id": bid, "model_id": "not-in-battle", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert bad.status_code == 400

        ok = client.post(
            "/internal/model",
            headers={"X-Sandbox-Token": token},
            json={
                "battle_id": bid,
                "model_id": "host:openrouter-free",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        # may 500 if HOST_OPENROUTER_KEY missing — set it
        if ok.status_code == 500:
            monkeypatch.setenv("HOST_OPENROUTER_KEY", "sk-or-test")
            settings.cache_clear()
            ok = client.post(
                "/internal/model",
                headers={"X-Sandbox-Token": token},
                json={
                    "battle_id": bid,
                    "model_id": "host:openrouter-free",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        assert ok.status_code == 200, ok.text
        assert ok.json()["content"] == "hello from model"
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()


def test_event_bus_uuid_and_dedupe():
    from agent_arena import event_bus

    e1 = event_bus.publish("b-test", {"type": "phase_start", "data": {"phase": "a"}})
    e2 = event_bus.publish("b-test", {"type": "phase_start", "data": {"phase": "b"}})
    assert e1["event_id"] != e2["event_id"]
    assert "created_at" in e1
    events = event_bus.subscribe("b-test")
    ids = [e["event_id"] for e in events if e.get("event_id") in (e1["event_id"], e2["event_id"])]
    assert len(ids) == 2
