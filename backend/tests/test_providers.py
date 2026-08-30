from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_arena.config import settings
from agent_arena.crypto import decrypt_key
from tests.conftest import make_user_id, requires_appwrite

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS_PAGE = REPO_ROOT / "frontend" / "src" / "pages" / "Providers.tsx"

FROZEN_HOST_UPSTREAM = {
    "host:openrouter-free": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "host:or-nemotron-lightning": "nvidia/nemotron-3.5-lightning:free",
    "host:or-laguna-s": "poolside/laguna-s-2.1:free",
    "host:or-laguna-xs": "poolside/laguna-xs-2.1:free",
    "host:or-minimax-m3": "minimax/minimax-m3:free",
    "host:or-minimax-m27": "minimax/minimax-m2.7:free",
    "host:or-router-free": "openrouter/free",
    "host:deepseek-chat": "deepseek-v4-flash",
    "host:groq-qwen": "qwen/qwen3.6-27b",
    "host:groq-compound": "groq/compound",
    "host:opencode-go": "deepseek-v4-flash",
    "host:or-nemotron-super": "nvidia/nemotron-3-super-120b-a12b:free",
    "host:or-gemma-31b": "google/gemma-4-31b-it:free",
    "host:groq-llama": "llama-3.3-70b-versatile",
    "host:merge-gateway": "openai/gpt-4o-mini",
    "host:tokenrouter": "moonshotai/kimi-k3",
    "host:xai-grok": "grok-4-1-fast-non-reasoning",
    "host:openai-gpt4o-mini": "gpt-4o-mini",
    "host:meta-muse": "muse-spark-1.1",
}

NEW_OPENROUTER_UPSTREAM = {
    "host:or-glm52": "z-ai/glm-5.2",
    "host:or-glm52-free": "z-ai/glm-5.2:free",
    "host:or-deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "host:or-deepseek-v4-pro-0813": "deepseek/deepseek-v4-pro-0813",
    "host:or-gemini-37-flash": "google/gemini-3.7-flash",
    "host:or-qwen3-coder": "qwen/qwen3-coder",
    "host:or-qwen3-coder-flash": "qwen/qwen3-coder-flash",
    "host:or-gpt5-nano": "openai/gpt-5-nano",
    "host:or-nex-n2-mini": "nex-agi/nex-n2-mini",
    "host:or-hy4": "tencent/hy4-preview",
}

OPENROUTER_FLEET_IDS = (
    "host:openrouter-free",
    "host:or-nemotron-lightning",
    "host:or-laguna-s",
    "host:or-laguna-xs",
    "host:or-minimax-m3",
    "host:or-minimax-m27",
    "host:or-router-free",
    *NEW_OPENROUTER_UPSTREAM,
)


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

    again = client.post("/providers", json=body)
    assert again.json()["id"] == pid
    listed2 = client.get("/providers").json()
    assert sum(1 for p in listed2 if p["id"] == pid) == 1

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


def test_stable_arena_ids_resolve_to_upstream_slugs():
    from agent_arena import providers

    for arena_id, slug in {**FROZEN_HOST_UPSTREAM, **NEW_OPENROUTER_UPSTREAM}.items():
        spec = providers.get_model_spec(arena_id)
        assert spec.upstream_model == slug
        assert providers.HOST_BY_ID[arena_id]["model_name"] == slug


def test_existing_arena_ids_do_not_change_meaning():
    from agent_arena import providers

    for arena_id, slug in FROZEN_HOST_UPSTREAM.items():
        assert providers.MODEL_BY_ID[arena_id].upstream_model == slug
    assert providers.MODEL_BY_ID["host:modal-kimi"].upstream_model == providers.MODAL_KIMI_MODEL
    for arena_id in NEW_OPENROUTER_UPSTREAM:
        assert arena_id not in FROZEN_HOST_UPSTREAM


def test_openrouter_models_share_one_provider_credential(monkeypatch):
    from agent_arena import providers

    settings.cache_clear()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("HOST_OPENROUTER_KEY", "sk-or-shared-key")
    settings.cache_clear()
    try:
        openrouter = providers.get_provider_spec("openrouter")
        assert openrouter.id == "openrouter"
        assert openrouter.base_url == providers.OPENROUTER_BASE
        assert openrouter.credential_env == "OPENROUTER_API_KEY"
        assert openrouter.protocol == "openai-compatible"

        keys = set()
        bases = set()
        for arena_id in OPENROUTER_FLEET_IDS:
            spec = providers.get_model_spec(arena_id)
            assert spec.provider_id == "openrouter"
            resolved = providers.resolve_model_call(arena_id, "any-user")
            assert resolved.provider_id == "openrouter"
            assert resolved.protocol == "openai-compatible"
            assert resolved.base_url == providers.OPENROUTER_BASE
            assert resolved.auth_style == "bearer"
            assert resolved.api_key == "sk-or-shared-key"
            assert resolved.upstream_model == spec.upstream_model
            keys.add(resolved.api_key)
            bases.add(resolved.base_url)
        assert keys == {"sk-or-shared-key"}
        assert bases == {providers.OPENROUTER_BASE}
    finally:
        settings.cache_clear()


def test_openrouter_accepts_canonical_credential_env(monkeypatch):
    from agent_arena import providers

    settings.cache_clear()
    monkeypatch.delenv("HOST_OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-canonical")
    settings.cache_clear()
    try:
        _, _, key, model = providers.get_model_call_spec("host:or-glm52", "any-user")
        assert key == "sk-or-canonical"
        assert model == "z-ai/glm-5.2"
    finally:
        settings.cache_clear()


def test_unknown_model_ids_fail_predictably():
    from agent_arena import providers

    with pytest.raises(HTTPException) as spec_exc:
        providers.get_model_spec("host:does-not-exist")
    assert spec_exc.value.status_code == 404
    assert spec_exc.value.detail == "Unknown model_id"

    with pytest.raises(HTTPException) as provider_exc:
        providers.get_provider_spec("not-a-provider")
    assert provider_exc.value.status_code == 404

    with pytest.raises(HTTPException) as effort_exc:
        providers.validate_reasoning_effort("host:missing", "high")
    assert effort_exc.value.status_code == 404


def test_model_capabilities_are_model_specific():
    from agent_arena import providers

    glm = providers.get_model_spec("host:or-glm52")
    glm_free = providers.get_model_spec("host:or-glm52-free")
    flash = providers.get_model_spec("host:or-qwen3-coder-flash")
    nano = providers.get_model_spec("host:or-gpt5-nano")
    grok = providers.get_model_spec("host:xai-grok")

    assert glm.reasoning_support is True
    assert glm.tier == "premium"
    assert glm.reasoning_efforts == ("off", "high", "max")
    assert glm_free.tier == "free"
    assert glm_free.upstream_model == "z-ai/glm-5.2:free"
    assert glm_free.reasoning_efforts == ("off", "high", "max")
    assert flash.reasoning_support is False
    assert flash.roles == ("fighter",)
    assert "judge" not in flash.roles
    assert nano.structured_output_support is True
    assert nano.tool_support is True
    assert grok.reasoning_support is False
    assert grok.reasoning_efforts == ("off",)


def test_reasoning_effort_validated_per_model():
    from agent_arena import providers

    assert providers.validate_reasoning_effort("host:or-glm52", None) is None
    assert providers.validate_reasoning_effort("host:or-glm52", "off") == "off"
    assert providers.validate_reasoning_effort("host:or-glm52", "high") == "high"
    assert providers.validate_reasoning_effort("host:or-glm52", "max") == "max"
    assert providers.validate_reasoning_effort("host:or-glm52", "xhigh") == "max"
    assert providers.validate_reasoning_effort("host:or-glm52-free", "off") == "off"
    assert providers.validate_reasoning_effort("host:or-glm52-free", "high") == "high"
    assert providers.validate_reasoning_effort("host:or-glm52-free", "max") == "max"
    assert providers.validate_reasoning_effort("host:or-glm52-free", "xhigh") == "max"
    assert providers.reasoning_request_fields("host:or-glm52-free", "xhigh") == {
        "reasoning": {"effort": "xhigh"}
    }

    with pytest.raises(HTTPException) as flash_exc:
        providers.validate_reasoning_effort("host:or-qwen3-coder-flash", "high")
    assert flash_exc.value.status_code == 400

    with pytest.raises(HTTPException) as grok_exc:
        providers.validate_reasoning_effort("host:xai-grok", "max")
    assert grok_exc.value.status_code == 400

    with pytest.raises(HTTPException) as unknown_exc:
        providers.normalize_reasoning_effort("ludicrous")
    assert unknown_exc.value.status_code == 400

    assert providers.validate_reasoning_effort("host:or-qwen3-coder-flash", "off") == "off"
    fields = providers.reasoning_request_fields("host:or-glm52", "xhigh")
    assert fields == {"reasoning": {"effort": "xhigh"}}
    assert providers.reasoning_request_fields("host:or-glm52", "off") == {}
    assert providers.reasoning_request_fields("host:or-gemini-37-flash", "high") == {
        "reasoning": {"effort": "high"}
    }


def test_free_and_paid_glm_ids_remain_distinct():
    from agent_arena import providers

    paid = providers.get_model_spec("host:or-glm52")
    free = providers.get_model_spec("host:or-glm52-free")
    assert paid.arena_model_id != free.arena_model_id
    assert paid.upstream_model == "z-ai/glm-5.2"
    assert free.upstream_model == "z-ai/glm-5.2:free"
    assert paid.upstream_model != free.upstream_model
    assert paid.tier != free.tier


def test_deepseek_v4_pro_revisions_remain_distinct():
    from agent_arena import providers

    current = providers.get_model_spec("host:or-deepseek-v4-pro")
    dated = providers.get_model_spec("host:or-deepseek-v4-pro-0813")
    assert current.arena_model_id != dated.arena_model_id
    assert current.upstream_model == "deepseek/deepseek-v4-pro"
    assert dated.upstream_model == "deepseek/deepseek-v4-pro-0813"
    assert current.upstream_model != dated.upstream_model
    assert providers.HOST_FREE["model_name"] != current.upstream_model


def test_catalog_is_authoritative_and_has_no_secrets(client, authed_user, monkeypatch):
    from agent_arena import providers

    settings.cache_clear()
    monkeypatch.setenv("HOST_OPENROUTER_KEY", "sk-or-secret-must-not-leak")
    settings.cache_clear()
    try:
        resp = client.get("/providers/catalog")
        assert resp.status_code == 200
        payload = resp.json()
        assert set(payload) == {"providers", "models"}
        provider_ids = {p["id"] for p in payload["providers"]}
        assert "openrouter" in provider_ids
        openrouter = next(p for p in payload["providers"] if p["id"] == "openrouter")
        assert openrouter["base_url"] == providers.OPENROUTER_BASE
        assert openrouter["credential_env"] == "OPENROUTER_API_KEY"
        assert openrouter["protocol"] == "openai-compatible"
        assert "api_key" not in openrouter
        assert "sk-or-secret-must-not-leak" not in resp.text

        models = {m["arena_model_id"]: m for m in payload["models"]}
        for arena_id, slug in NEW_OPENROUTER_UPSTREAM.items():
            assert models[arena_id]["upstream_model"] == slug
            assert models[arena_id]["provider_id"] == "openrouter"
        assert models["host:or-glm52"]["available"] is True
        assert models["host:or-gemma-31b"]["available"] is False
        assert models["host:or-gemma-31b"]["status"] == "retired"
        assert "fighter" in models["host:or-glm52"]["roles"]
        assert models["host:or-glm52"]["reasoning_support"] is True
    finally:
        settings.cache_clear()


def test_providers_page_consumes_backend_catalog():
    text = PROVIDERS_PAGE.read_text()
    assert "/providers/catalog" in text
    assert "loadModelCatalog" in text
    forbidden = [
        "host:or-glm52",
        "host:or-deepseek-v4-pro",
        "z-ai/glm-5.2",
        "deepseek/deepseek-v4-pro",
        "google/gemini-3.7-flash",
        "qwen/qwen3-coder",
        "openai/gpt-5-nano",
        "nex-agi/nex-n2-mini",
        "tencent/hy4-preview",
        "Fighter ✓ · Judge ✓",
    ]
    for token in forbidden:
        assert token not in text, f"Providers page hardcodes catalog token {token!r}"


@requires_appwrite
def test_get_model_call_spec_user_provider(client, authed_user, monkeypatch):
    from agent_arena import providers
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

    host_del = client.delete("/providers/host:openrouter-free")
    assert host_del.status_code == 400

    deleted = client.delete(f"/providers/{pid}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["id"] == pid

    listed = client.get("/providers").json()
    assert not any(p["id"] == pid for p in listed)

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
        resp = client.post(f"/providers/{pid}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("HEALTHY", "ERROR")
        assert data["ok"] in (True, False)
        assert "latency_ms" in data
    finally:
        client.delete(f"/providers/{pid}")
