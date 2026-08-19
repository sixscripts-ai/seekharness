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




def _cleanup_battle(databases, database_id, bid):
    from appwrite.query import Query

    for coll in ("scores", "battle_events", "memories"):
        try:
            docs = databases.list_documents(
                database_id, coll, queries=[Query.equal("battle_id", bid), Query.limit(100)]
            )
            for d in docs.documents:
                databases.delete_document(database_id, coll, d.id)
        except Exception:
            pass
    for mid in ("m-a", "m-b"):
        try:
            docs = databases.list_documents(
                database_id, "leaderboard",
                queries=[Query.equal("model_id", mid), Query.limit(100)],
            )
            for d in docs.documents:
                databases.delete_document(database_id, "leaderboard", d.id)
        except Exception:
            pass
    try:
        databases.delete_document(database_id, "battles", bid)
    except Exception:
        pass


@requires_appwrite
def test_finalize_deterministic_without_judge_scores(client, internal_key, monkeypatch):
    """EXECUTOR_RESULT + empty judge scores -> deterministic execution path."""
    import json
    import uuid

    from appwrite.query import Query

    from agent_arena import db
    from agent_arena.auth import get_current_user
    from agent_arena.battle_token import issue_battle_token
    from agent_arena.internal_router import FinalizeBody, internal_finalize
    from agent_arena.main import app
    from tests.conftest import make_user_id

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    databases = db.get_databases()
    database_id = db.get_database_id()
    bid = f"slice-a1-{uuid.uuid4().hex[:10]}"
    try:
        formats = client.get("/formats").json()
        fmt = next(f for f in formats if (f.get("config") or {}).get("universal"))
        databases.create_document(database_id, "battles", bid, {
            "user_id": user_id, "format_id": fmt["id"], "model_ids": ["m-a", "m-b"],
            "arena_size": 2, "status": "running", "timeout_seconds": 600,
            "round_visibility": "isolated", "saved": False,
        })
        for mid, outcome in (("m-a", "TEST_PASS"), ("m-b", "TEST_FAIL")):
            result = json.dumps({
                "executor_version": 1, "model_id": mid, "role": "player_a",
                "phase": "race", "outcome": outcome, "passed": outcome == "TEST_PASS",
                "steps": 4, "tool_errors": 0, "parse_errors": 0,
                "artifact_checks": {"present": ["solution.py"], "missing": []},
            })
            databases.create_document(database_id, "battle_events", "unique()", {
                "battle_id": bid, "event_id": uuid.uuid4().hex,
                "payload": json.dumps(
                    {"type": "result", "data": {"artifact": "EXECUTOR_RESULT: " + result}}
                ),
                "created_at": 0.0,
            })
        token = issue_battle_token(bid)
        resp = internal_finalize(
            FinalizeBody(battle_id=bid, status="completed", scores={}),
            x_sandbox_token=token,
        )
        assert resp["status"] == "completed"
        score_docs = databases.list_documents(
            database_id, "scores", queries=[Query.equal("battle_id", bid)]
        ).documents
        assert score_docs, "deterministic scores must persist without judge scores"
        assert all(d.data["judge_model"] == "arena-deterministic" for d in score_docs)
        by_mid = {d.data["model_id"]: d.data["score"] for d in score_docs}
        assert by_mid["m-a"] > by_mid["m-b"]
        import time

        found = False
        for _ in range(20):
            evs = databases.list_documents(
                database_id, "battle_events",
                queries=[Query.equal("battle_id", bid), Query.limit(500)],
            ).documents
            if any('"evidence_summary"' in (d.data.get("payload") or "") for d in evs):
                found = True
                break
            time.sleep(0.25)
        assert found, "evidence_summary event must be durably persisted"
    finally:
        app.dependency_overrides.clear()
        _cleanup_battle(databases, database_id, bid)


@requires_appwrite
def test_finalize_judge_path_without_results_stays_compatible(client, internal_key, monkeypatch):
    """No EXECUTOR_RESULT (prose battle) + judge scores -> judge path unchanged."""
    import uuid

    from appwrite.query import Query

    from agent_arena import db
    from agent_arena.auth import get_current_user
    from agent_arena.battle_token import issue_battle_token
    from agent_arena.internal_router import FinalizeBody, internal_finalize
    from agent_arena.main import app
    from tests.conftest import make_user_id

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    databases = db.get_databases()
    database_id = db.get_database_id()
    bid = f"slice-a1b-{uuid.uuid4().hex[:10]}"
    try:
        formats = client.get("/formats").json()
        fmt = formats[0]
        databases.create_document(database_id, "battles", bid, {
            "user_id": user_id, "format_id": fmt["id"], "model_ids": ["m-a", "m-b"],
            "arena_size": 2, "status": "running", "timeout_seconds": 600,
            "round_visibility": "isolated", "saved": False,
        })
        token = issue_battle_token(bid)
        resp = internal_finalize(
            FinalizeBody(battle_id=bid, status="completed", scores={"m-a": 9.0, "m-b": 8.0}),
            x_sandbox_token=token,
        )
        assert resp["status"] == "completed"
        score_docs = databases.list_documents(
            database_id, "scores", queries=[Query.equal("battle_id", bid)]
        ).documents
        assert score_docs
        assert all(d.data["judge_model"] == "host-judge" for d in score_docs)
        by_mid = {d.data["model_id"]: d.data["score"] for d in score_docs}
        assert by_mid == {"m-a": 9.0, "m-b": 8.0}
    finally:
        app.dependency_overrides.clear()
        _cleanup_battle(databases, database_id, bid)



@requires_appwrite
def test_finalize_failed_with_full_evidence_completes_deterministically(client, internal_key, monkeypatch):
    """status=failed + empty judge scores + both EXECUTOR_RESULTs -> deterministic
    path activates and the executable evidence completes the battle."""
    import json
    import uuid

    from appwrite.query import Query

    from agent_arena import db
    from agent_arena.auth import get_current_user
    from agent_arena.battle_token import issue_battle_token
    from agent_arena.internal_router import FinalizeBody, internal_finalize
    from agent_arena.main import app
    from tests.conftest import make_user_id

    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    databases = db.get_databases()
    database_id = db.get_database_id()
    bid = f"slice-a1c-{uuid.uuid4().hex[:10]}"
    try:
        formats = client.get("/formats").json()
        fmt = next(f for f in formats if (f.get("config") or {}).get("universal"))
        databases.create_document(database_id, "battles", bid, {
            "user_id": user_id, "format_id": fmt["id"], "model_ids": ["m-a", "m-b"],
            "arena_size": 2, "status": "running", "timeout_seconds": 600,
            "round_visibility": "isolated", "saved": False,
        })
        for mid, outcome in (("m-a", "TEST_PASS"), ("m-b", "TEST_FAIL")):
            result = json.dumps({
                "executor_version": 1, "model_id": mid, "role": "player_a",
                "phase": "race", "outcome": outcome, "passed": outcome == "TEST_PASS",
                "steps": 4, "tool_errors": 0, "parse_errors": 0,
                "artifact_checks": {"present": ["solution.py"], "missing": []},
            })
            databases.create_document(database_id, "battle_events", "unique()", {
                "battle_id": bid, "event_id": uuid.uuid4().hex,
                "payload": json.dumps(
                    {"type": "result", "data": {"artifact": "EXECUTOR_RESULT: " + result}}
                ),
                "created_at": 0.0,
            })
        token = issue_battle_token(bid)
        resp = internal_finalize(
            FinalizeBody(battle_id=bid, status="failed", scores={}),
            x_sandbox_token=token,
        )
        assert resp["status"] == "completed"  # evidence completes the battle
        score_docs = databases.list_documents(
            database_id, "scores", queries=[Query.equal("battle_id", bid)]
        ).documents
        assert score_docs
        assert all(d.data["judge_model"] == "arena-deterministic" for d in score_docs)
        by_mid = {d.data["model_id"]: d.data["score"] for d in score_docs}
        assert by_mid["m-a"] > by_mid["m-b"]
    finally:
        app.dependency_overrides.clear()
        _cleanup_battle(databases, database_id, bid)


def test_event_bus_uuid_and_dedupe():
    from agent_arena import event_bus

    e1 = event_bus.publish("b-test", {"type": "phase_start", "data": {"phase": "a"}})
    e2 = event_bus.publish("b-test", {"type": "phase_start", "data": {"phase": "b"}})
    assert e1["event_id"] != e2["event_id"]
    assert "created_at" in e1
    events = event_bus.subscribe("b-test")
    ids = [e["event_id"] for e in events if e.get("event_id") in (e1["event_id"], e2["event_id"])]
    assert len(ids) == 2
