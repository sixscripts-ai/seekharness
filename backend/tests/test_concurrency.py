from agent_arena import db
from agent_arena.battles import MAX_ACTIVE_BATTLES, active_battle_count
from tests.conftest import make_user_id, playable_format_id, requires_appwrite


@requires_appwrite
def test_cap_is_five():
    assert MAX_ACTIVE_BATTLES == 5


@requires_appwrite
def test_active_count_and_cap_rejection(client):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app
    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id

    databases = db.get_databases()
    database_id = db.get_database_id()
    created = []
    for _ in range(MAX_ACTIVE_BATTLES):
        doc = databases.create_document(database_id, "battles", "unique()", {
            "user_id": user_id, "format_id": "code-review-duel", "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2, "status": "running", "timeout_seconds": 600,
            "round_visibility": "isolated", "saved": False,
        })
        created.append(doc.id)

    try:
        assert active_battle_count(databases, database_id, user_id) == MAX_ACTIVE_BATTLES
        format_id = playable_format_id()
        resp = client.post("/battles", json={
            "format_id": format_id,
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        })
        assert resp.status_code == 429, resp.text
    finally:
        for battle_id in created:
            databases.delete_document(database_id, "battles", battle_id)
        app.dependency_overrides.clear()
