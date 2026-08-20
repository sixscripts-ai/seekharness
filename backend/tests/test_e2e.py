import time

from agent_arena.seed_formats import seed_formats
from tests.conftest import make_user_id, requires_appwrite


@requires_appwrite
def test_full_battle_lifecycle(client):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app
    seed_formats()
    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    try:
        formats = client.get("/formats")
        assert formats.status_code == 200
        body = formats.json()
        assert len(body) == 8
        fmt = next(f["id"] for f in body if not (f.get("config") or {}).get("custom"))
        assert fmt, "GET /formats must return a usable format id"
        assert client.post("/battles", json={
            "format_id": fmt,
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
        }).status_code == 201, "GET /formats id must round-trip into POST /battles"

        battle = client.post("/battles", json={
            "format_id": fmt,
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
        })
        assert battle.status_code == 201
        battle_id = battle.json()["id"]

        for _ in range(100):
            status = client.get(f"/battles/{battle_id}").json()["status"]
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.2)
        assert status == "completed", f"battle ended with {status}"

        rounds = client.get(f"/battles/{battle_id}/artifacts").json()
        assert len(rounds) > 0

        leaderboard = client.get("/leaderboard?format=overall").json()
        assert any(e["model_id"] in ("m-alpha", "m-beta") for e in leaderboard)
    finally:
        app.dependency_overrides.clear()
