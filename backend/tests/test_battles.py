import importlib.util
import sys
import time
from types import ModuleType

import pytest

from tests.conftest import make_user_id, playable_format_id, requires_appwrite


@pytest.fixture(autouse=True)
def _stub_leaderboard(monkeypatch):
    try:
        spec = importlib.util.find_spec("agent_arena.leaderboard")
    except ModuleNotFoundError:
        spec = None
    if spec is not None:
        return
    stub = ModuleType("agent_arena.leaderboard")
    stub.apply_result = lambda databases, database_id, format_id, model_ids, scores: None
    monkeypatch.setitem(sys.modules, "agent_arena.leaderboard", stub)


def _login(client, user_id):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app
    app.dependency_overrides[get_current_user] = lambda: user_id


def _logout():
    from agent_arena.main import app
    app.dependency_overrides.clear()


def _real_format_id() -> str:
    return playable_format_id()


@requires_appwrite
def test_create_battle_wrong_role_count(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        resp = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free"],  # need 2 playable roles
            "arena_size": 1,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        # pydantic min_length=2 on model_ids → 422, or our 400 if that changes
        assert resp.status_code in (400, 422)
    finally:
        _logout()


@requires_appwrite
def test_create_battle_rejects_unknown_model(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        resp = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "not-a-real-provider-id"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp.status_code == 400
        assert "Unknown model_id" in resp.text or "model_id" in resp.text
    finally:
        _logout()


@requires_appwrite
def test_cancel_stops_battle(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
        cancel = client.post(f"/battles/{battle['id']}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"
    finally:
        _logout()


@requires_appwrite
def test_list_battles_saved_filter(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        unsaved = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
        saved = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
        }).json()
        all_battles = client.get("/battles")
        assert all_battles.status_code == 200
        ids = {b["id"] for b in all_battles.json()}
        assert unsaved["id"] in ids and saved["id"] in ids
        only_saved = client.get("/battles?saved=true")
        assert only_saved.status_code == 200
        saved_ids = {b["id"] for b in only_saved.json()}
        assert saved["id"] in saved_ids
        assert unsaved["id"] not in saved_ids
    finally:
        _logout()


@requires_appwrite
def test_save_persists_rounds(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
        # mock runner completes in background after create returns
        for _ in range(50):
            status = client.get(f"/battles/{battle['id']}").json()["status"]
            if status == "completed":
                break
            time.sleep(0.2)
        save = client.post(f"/battles/{battle['id']}/save")
        assert save.status_code == 200
        assert save.json()["saved"] is True
        artifacts = client.get(f"/battles/{battle['id']}/artifacts").json()
        assert len(artifacts) > 0
        assert all("artifact" in a for a in artifacts)
    finally:
        _logout()


@requires_appwrite
def test_unsaved_battle_has_no_artifacts(client):
    user_id = make_user_id()
    _login(client, user_id)
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
        for _ in range(50):
            status = client.get(f"/battles/{battle['id']}").json()["status"]
            if status == "completed":
                break
            time.sleep(0.2)
        resp = client.get(f"/battles/{battle['id']}/artifacts")
        assert resp.status_code == 404
    finally:
        _logout()


@requires_appwrite
def test_runner_failure_marks_battle_failed(client, monkeypatch):
    from agent_arena import mock_runner

    def boom(*args, **kwargs):
        raise RuntimeError("simulated runner failure")

    monkeypatch.setattr(mock_runner, "_persist_rounds", boom)
    user_id = make_user_id()
    _login(client, user_id)
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert battle.status_code == 201
        # run_battle runs as a background task; the failure path must flip the
        # battle to "failed" (not leave it stuck in queued/running forever).
        status = client.get(f"/battles/{battle.json()['id']}").json()["status"]
        assert status == "failed"
    finally:
        _logout()


@requires_appwrite
def test_other_user_cannot_act_on_battle(client):
    owner = make_user_id()
    attacker = make_user_id()
    _login(client, owner)
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
    finally:
        _logout()
    _login(client, attacker)
    try:
        assert client.get(f"/battles/{battle['id']}").status_code == 403
        assert client.post(f"/battles/{battle['id']}/cancel").status_code == 403
        assert client.post(f"/battles/{battle['id']}/save").status_code == 403
    finally:
        _logout()
