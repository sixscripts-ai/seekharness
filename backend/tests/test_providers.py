import pytest

from agent_arena.config import settings
from agent_arena.crypto import decrypt_key
from tests.conftest import make_user_id, requires_appwrite


@pytest.fixture
def authed_user():
    from agent_arena.auth import get_current_user
    from agent_arena.main import app

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    yield user_id
    app.dependency_overrides.clear()


@requires_appwrite
def test_provider_crud_and_encryption(client, authed_user):
    user_id = authed_user
    key = settings()["FERNET_KEY"].encode()
    name = f"test-{user_id[:12]}"
    body = {
        "name": name,
        "base_url": "https://example.invalid/v1",
        "api_key": "sk-secret-value-1234567890",
        "auth_style": "bearer",
        "model_name": "gpt-4o-mini",
    }
    created = client.post("/providers", json=body)
    assert created.status_code == 200, created.text
    pid = created.json()["id"]
    assert created.json()["masked_key"].startswith("sk-s")
    assert "sk-secret-value-1234567890" not in created.text

    # encryption at rest: the stored value must decrypt with the app's key
    # and must not be stored as plaintext
    from appwrite.query import Query

    from agent_arena import db

    databases = db.get_databases()
    res = databases.list_documents(
        db.get_database_id(),
        "providers",
        queries=[Query.equal("user_id", user_id), Query.limit(100)],
    )
    doc = next(d for d in res.documents if d.id == pid)
    assert decrypt_key(doc.data["encrypted_key"], key) == body["api_key"]
    assert doc.data["encrypted_key"] != body["api_key"]

    listed = client.get("/providers")
    assert listed.status_code == 200
    assert any(p["id"] == pid and p["name"] == name for p in listed.json())
    assert all("encrypted_key" not in p for p in listed.json())

    # same name upserts (update) rather than duplicate
    again = client.post("/providers", json=body)
    assert again.json()["id"] == pid
    listed2 = client.get("/providers").json()
    assert sum(1 for p in listed2 if p["id"] == pid) == 1

    # cleanup: delete provider documents for this user
    res = databases.list_documents(
        db.get_database_id(),
        "providers",
        queries=[Query.equal("user_id", user_id), Query.limit(100)],
    )
    for doc in res.documents:
        databases.delete_document(db.get_database_id(), "providers", doc.id)


@requires_appwrite
def test_provider_health_bad_endpoint(client, authed_user):
    resp = client.post(
        "/providers/health",
        json={
            "base_url": "https://example.invalid/v1",
            "api_key": "sk-bad",
            "auth_style": "bearer",
        },
    )
    assert resp.status_code in (400, 502)


def test_get_model_call_spec_host_free(monkeypatch):
    from agent_arena import providers
    from agent_arena.config import settings

    settings.cache_clear()
    monkeypatch.setenv("HOST_OPENROUTER_KEY", "sk-or-test-key")
    monkeypatch.setenv("JUDGE_MODAL_KEY", "ak-test")
    monkeypatch.setenv("JUDGE_MODAL_SECRET", "as-test")
    monkeypatch.delenv("HOST_XAI_KEY", raising=False)
    monkeypatch.delenv("HOST_DEEPSEEK_KEY", raising=False)
    monkeypatch.delenv("HOST_OPENAI_KEY", raising=False)
    settings.cache_clear()
    try:
        base, style, key, model = providers.get_model_call_spec(
            "host:openrouter-free", "any-user"
        )
        assert base == "https://openrouter.ai/api/v1"
        assert style == "bearer"
        assert key == "sk-or-test-key"
        assert model == "nvidia/nemotron-3-ultra-550b-a55b:free"
        base2, _, key2, model2 = providers.get_model_call_spec(
            "host:or-laguna-s", "any-user"
        )
        assert base2 == base and key2 == key
        assert model2 == "poolside/laguna-s-2.1:free"
        mbase, mstyle, mkey, mmodel = providers.get_model_call_spec(
            "host:modal-kimi", "any-user"
        )
        assert "modal.direct" in mbase
        assert mstyle == "modal_proxy"
        assert mkey == "ak-test:as-test"
        assert mmodel == providers.MODAL_KIMI_MODEL
        listed = providers.configured_host_providers()
        ids = {p["id"] for p in listed}
        assert "host:modal-kimi" in ids and "host:openrouter-free" in ids
        assert "host:xai-grok" not in ids
        assert providers.is_host_model("host:or-gemma-31b")
        assert not providers.is_host_model("user-doc-id")
    finally:
        settings.cache_clear()


@requires_appwrite
def test_get_model_call_spec_user_provider(client, authed_user, monkeypatch):
    from agent_arena import providers
    from agent_arena.config import settings
    from appwrite.query import Query
    from agent_arena import db

    user_id = authed_user
    body = {
        "name": f"spec-{user_id[:8]}",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-user-secret-abcdef",
        "auth_style": "bearer",
        "model_name": "my-model-v1",
    }
    created = client.post("/providers", json=body)
    assert created.status_code == 200, created.text
    pid = created.json()["id"]
    try:
        base, style, key, model = providers.get_model_call_spec(pid, user_id)
        assert base == body["base_url"]
        assert style == "bearer"
        assert key == body["api_key"]
        assert model == "my-model-v1"
    finally:
        databases = db.get_databases()
        res = databases.list_documents(
            db.get_database_id(),
            "providers",
            queries=[Query.equal("user_id", user_id), Query.limit(100)],
        )
        for doc in res.documents:
            databases.delete_document(db.get_database_id(), "providers", doc.id)


@requires_appwrite
def test_delete_provider(client, authed_user):
    user_id = authed_user
    body = {
        "name": f"to-delete-{user_id[:8]}",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-delete-me-123456",
        "auth_style": "bearer",
        "model_name": "gpt-4o",
    }
    created = client.post("/providers", json=body)
    assert created.status_code == 200
    pid = created.json()["id"]

    # Trying to delete a host provider must return 400
    host_del = client.delete("/providers/host:openrouter-free")
    assert host_del.status_code == 400

    # Successful delete of own custom provider
    deleted = client.delete(f"/providers/{pid}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["id"] == pid

    # Listing must no longer include the deleted provider
    listed = client.get("/providers").json()
    assert not any(p["id"] == pid for p in listed)

    # Deleting already deleted or nonexistent returns 404
    retry = client.delete(f"/providers/{pid}")
    assert retry.status_code == 404


@requires_appwrite
def test_provider_id_health_endpoint(client, authed_user):
    user_id = authed_user
    body = {
        "name": f"health-test-{user_id[:8]}",
        "base_url": "https://example.invalid/v1",
        "api_key": "sk-real-test-secret-123456",
        "auth_style": "bearer",
        "model_name": "gpt-4o",
    }
    created = client.post("/providers", json=body)
    assert created.status_code == 200
    pid = created.json()["id"]

    try:
        # Testing stored provider health executes real backend check (which gets ERROR on example.invalid)
        resp = client.post(f"/providers/{pid}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("HEALTHY", "ERROR")
        assert data["ok"] in (True, False)
        assert "latency_ms" in data
    finally:
        client.delete(f"/providers/{pid}")

