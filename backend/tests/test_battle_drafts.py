import json

from agent_arena.schema import ensure_schema
from tests.conftest import make_user_id, requires_appwrite


def _login(client, user_id):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app

    app.dependency_overrides[get_current_user] = lambda: user_id


def _logout():
    from agent_arena.main import app

    app.dependency_overrides.clear()


@requires_appwrite
def test_custom_format_cannot_launch_via_battles(client):
    from agent_arena.seed_formats import seed_formats

    seed_formats()
    user_id = make_user_id()
    _login(client, user_id)
    try:
        formats = client.get("/formats").json()
        custom = next(f for f in formats if (f.get("config") or {}).get("custom"))
        resp = client.post(
            "/battles",
            json={
                "format_id": custom["id"],
                "model_ids": ["host:openrouter-free", "host:or-nemotron-super"],
                "arena_size": 2,
                "timeout_seconds": 600,
                "round_visibility": "isolated",
                "save": False,
            },
        )
        assert resp.status_code == 400
        assert "draft" in resp.json()["detail"].lower()
    finally:
        _logout()


@requires_appwrite
def test_draft_owner_isolation_and_launch(client):
    from agent_arena.seed_formats import seed_formats

    ensure_schema()
    seed_formats()
    owner = make_user_id()
    other = make_user_id()
    _login(client, owner)
    try:
        created = client.post("/battle-drafts", json={"mode": "quick"})
        assert created.status_code == 201
        draft_id = created.json()["id"]
        msg = client.post(
            f"/battle-drafts/{draft_id}/messages",
            json={"content": "Build a markdown README that greets the arena."},
        )
        assert msg.status_code == 200
        draft = msg.json()
        assert draft["status"] == "ready"
        assert draft["revision"] >= 1
        patched = client.patch(
            f"/battle-drafts/{draft_id}/spec",
            json={"title": "Greeting README", "brief": draft["spec"]["brief"]},
        )
        assert patched.status_code == 200
        rev = patched.json()["revision"]
        launch = client.post(
            f"/battle-drafts/{draft_id}/launch",
            json={
                "revision": rev,
                "model_ids": ["host:openrouter-free", "host:or-nemotron-super"],
                "timeout_seconds": 60,
                "save": True,
            },
        )
        assert launch.status_code == 201, launch.text
        battle_id = launch.json()["id"]
        again = client.post(
            f"/battle-drafts/{draft_id}/launch",
            json={
                "revision": rev,
                "model_ids": ["host:openrouter-free", "host:or-nemotron-super"],
                "timeout_seconds": 60,
                "save": True,
            },
        )
        assert again.status_code == 201
        assert again.json()["id"] == battle_id
        battle = client.get(f"/battles/{battle_id}").json()
        assert battle["ranked"] is False
        assert battle["spec_hash"]
        assert battle["round_visibility"] == "isolated"
        cfg = battle.get("battle_config") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        assert cfg.get("custom") is True
        assert cfg.get("evaluation_mode") == "quick"
        stream = client.get(f"/battles/{battle_id}/stream")
        assert stream.status_code == 200
    finally:
        _logout()

    _login(client, other)
    try:
        assert client.get(f"/battle-drafts/{draft_id}").status_code == 403
        assert client.post(
            f"/battle-drafts/{draft_id}/messages",
            json={"content": "hijack"},
        ).status_code == 403
    finally:
        _logout()


@requires_appwrite
def test_verified_draft_patch_and_unique_models(client):
    from agent_arena.seed_formats import seed_formats

    ensure_schema()
    seed_formats()
    user_id = make_user_id()
    _login(client, user_id)
    try:
        created = client.post("/battle-drafts", json={"mode": "verified"})
        draft_id = created.json()["id"]
        spec = {
            "title": "Add",
            "brief": "Implement add(a, b).",
            "required_artifacts": ["solution.py"],
            "test_code": (
                "from solution import add\n"
                "def main():\n"
                "    assert add(1, 1) == 2\n"
                "    print('TEST_PASS')\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
        patched = client.patch(f"/battle-drafts/{draft_id}/spec", json=spec)
        assert patched.status_code == 200, patched.text
        bad = client.post(
            f"/battle-drafts/{draft_id}/launch",
            json={
                "revision": patched.json()["revision"],
                "model_ids": ["host:openrouter-free", "host:openrouter-free"],
                "timeout_seconds": 60,
                "save": False,
            },
        )
        assert bad.status_code == 400
    finally:
        _logout()
