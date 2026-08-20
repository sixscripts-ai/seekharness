from agent_arena import db
from agent_arena.schema import COLLECTIONS, ensure_schema
from tests.conftest import requires_appwrite


def test_collection_spec_has_expected_battles_fields():
    battle_fields = {a[0] for a in COLLECTIONS["battles"]}
    assert {"user_id", "format_id", "model_ids", "status", "saved", "difficulty", "draft_id", "battle_config", "spec_hash", "ranked"} <= battle_fields
    assert "battle_drafts" in COLLECTIONS


@requires_appwrite
def test_ensure_schema_creates_collections():
    ensure_schema()
    databases = db.get_databases()
    res = databases.list_collections(db.get_database_id())
    ids = {c.id for c in res.collections}
    assert set(COLLECTIONS) <= ids
