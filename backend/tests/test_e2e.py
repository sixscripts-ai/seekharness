import time
import uuid

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

        # Round-trip check: a standard format id must be launchable with host models.
        assert client.post("/battles", json={
            "format_id": fmt,
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
        }).status_code == 201, "GET /formats id must round-trip into POST /battles"

        # Own all state: unique per-run provider/model pair so the leaderboard
        # assertion never depends on preexisting rows (e.g. m-alpha / m-beta).
        suffix = uuid.uuid4().hex[:8]
        names = (f"m-alpha-{suffix}", f"m-beta-{suffix}")
        model_ids: list[str] = []
        for name in names:
            resp = client.post("/providers", json={
                "name": name,
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-1234567890",
                "auth_style": "bearer",
                "model_name": "gpt-4o-mini",
            })
            assert resp.status_code == 200, resp.text
            model_ids.append(resp.json()["id"])
        alpha, beta = model_ids

        battle = client.post("/battles", json={
            "format_id": fmt,
            "model_ids": [alpha, beta],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
        })
        assert battle.status_code == 201
        battle_id = battle.json()["id"]

        status = "queued"
        for _ in range(100):
            status = client.get(f"/battles/{battle_id}").json()["status"]
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.2)
        assert status == "completed", f"battle ended with {status}"

        rounds = client.get(f"/battles/{battle_id}/artifacts").json()
        assert len(rounds) > 0

        leaderboard = client.get("/leaderboard?format=overall").json()
        assert any(e["model_id"] == alpha for e in leaderboard)
        assert any(e["model_id"] == beta for e in leaderboard)

        # Clean up the owned providers; the battle and leaderboard rows carry
        # unique suffixes so they cannot collide with other runs.
        for mid in model_ids:
            assert client.delete(f"/providers/{mid}").status_code == 200
    finally:
        app.dependency_overrides.clear()
